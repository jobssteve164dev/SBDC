import io
import hashlib
import math
import re
from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher
from html import escape, unescape
from pathlib import Path
from typing import Any

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


METHOD_VERSION = "pdf-evidence-rules/1.3.0"
MAX_IMAGE_PIXELS = 4_000_000
MAX_IMAGE_TILES = 2_500
MAX_TASK_IMAGE_DECODED_PIXELS = 40_000_000
MAX_TASK_IMAGE_TILES = 25_000
FONT_PATHS = (
    (Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"), 0),
    (Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"), 0),
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _location(document_id: str, page: int, bbox: list[float]) -> dict[str, Any]:
    return {"document_id": document_id, "page": page, "bbox": bbox, "char_start": None, "char_end": None}


def _excerpt_around(text: str, marker: str, *, radius: int = 260) -> str:
    index = text.lower().find(marker.lower())
    if index < 0 or len(text) <= radius * 2:
        return text
    start = max(0, index - radius)
    end = min(len(text), index + len(marker) + radius)
    return f"{'…' if start else ''}{text[start:end].strip()}{'…' if end < len(text) else ''}"


def _cross_condition_subject_evidence(
    blocks: list[dict[str, Any]], document_id: str
) -> list[dict[str, Any]]:
    condition_terms = re.compile(
        r"\b(temperatures?|conditions?|groups?|cohorts?|samples?|specimens?|participants?|patients?|animals?|"
        r"emitters?|quantum dots?|QDs?|measurements?|experiments?|timepoints?|visits?)\b",
        re.IGNORECASE,
    )
    mismatch = re.compile(
        r"\bnot\s+(?:obtained|recorded|measured|collected|derived)\s+from\s+(?:the\s+)?same\s+"
        r"(?:samples?|specimens?|subjects?|participants?|patients?|animals?|emitters?|quantum dots?|QDs?|cohorts?|groups?)\b|"
        r"\bdifferent\s+(?:samples?|specimens?|subjects?|participants?|patients?|"
        r"animals?|emitters?|quantum dots?|QDs?|cohorts?|groups?)\b",
        re.IGNORECASE,
    )
    evidence = []
    for block in blocks:
        match = mismatch.search(block["text"])
        if match and condition_terms.search(block["text"]):
            evidence.append(_evidence(
                code="cross_condition_subject_mismatch",
                category="evidence_limitation",
                severity="medium",
                confidence=0.94,
                document_id=document_id,
                page=block["page"],
                bbox=block["bbox"],
                excerpt=_excerpt_around(block["text"], match.group(0)),
                explanation="论文说明不同条件下的结果并非来自同一研究对象；跨条件比较必须保留这一限制，不能自动解释为同一对象的变化。",
                limitations=["该发现只核对实验对象是否一致，不评价测量数据真实性或研究设计是否适当。"],
            ))
    return evidence


def _measurement_context_evidence(
    blocks: list[dict[str, Any]], document_id: str
) -> list[dict[str, Any]]:
    unit_pattern = r"ns|ms|ps|s|meV|eV|nm|μm|µm|mm|cm|Hz|kHz|MHz|GHz|%"
    condition_pattern = r"\d+(?:[.]\d+)?\s*(?:K|°C|°F)|room temperature|RT"
    measurement = re.compile(
        rf"(?P<value>\d+(?:[.]\d+)?)\s*(?P<unit>{unit_pattern})(?![A-Za-z])",
        re.IGNORECASE,
    )
    condition = re.compile(condition_pattern, re.IGNORECASE)
    parallel = re.compile(
        rf"(?P<value_a>\d+(?:[.]\d+)?)\s+(?:and|,)\s+(?P<value_b>\d+(?:[.]\d+)?)\s*"
        rf"(?P<unit>{unit_pattern})\s+at\s+(?P<condition_a>{condition_pattern})\s+and\s+"
        rf"(?P<condition_b>{condition_pattern})\s*,?\s*respectively",
        re.IGNORECASE,
    )
    seen: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
        left_boundary = text.rfind(". ", 0, start)
        right_boundary = text.find(". ", end)
        return (left_boundary + 2 if left_boundary >= 0 else 0, right_boundary + 1 if right_boundary >= 0 else len(text))

    def context_terms(text: str, start: int, end: int) -> set[str]:
        sentence_start, sentence_end = sentence_span(text, start, end)
        stopwords = {
            "about", "after", "before", "condition", "conditions", "data", "from", "into", "measured",
            "measurement", "measurements", "obtained", "reported", "result", "results", "same", "than",
            "that", "their", "these", "this", "under", "value", "values", "were", "with",
        }
        terms = set()
        for word in re.findall(r"[A-Za-z]{4,}", text[sentence_start:sentence_end].lower()):
            normalized = word[:-1] if word.endswith("s") and len(word) > 5 else word
            if normalized not in stopwords:
                terms.add(normalized)
        return terms

    for block in blocks:
        text = block["text"]
        parallel_spans: list[tuple[int, int]] = []
        for pair in parallel.finditer(text):
            parallel_spans.append(pair.span())
            unit = pair.group("unit")
            for value_name, condition_name in (("value_a", "condition_a"), ("value_b", "condition_b")):
                value = pair.group(value_name)
                seen.setdefault((value, unit.lower()), []).append(
                    {
                        **block,
                        "measurement": f"{value} {unit}",
                        "condition": pair.group(condition_name),
                        "marker": pair.group(0),
                        "context_terms": context_terms(text, pair.start(), pair.end()),
                    }
                )
        for found in measurement.finditer(text):
            if any(start <= found.start() < end for start, end in parallel_spans):
                continue
            left = max(0, found.start() - 90)
            right = min(len(text), found.end() + 90)
            candidates = list(condition.finditer(text, left, right))
            if not candidates:
                continue
            center = (found.start() + found.end()) / 2
            context_match = min(
                candidates,
                key=lambda candidate: abs(((candidate.start() + candidate.end()) / 2) - center),
            )
            key = (found.group("value"), found.group("unit").lower())
            seen.setdefault(key, []).append(
                {
                    **block,
                    "measurement": found.group(0),
                    "condition": context_match.group(0),
                    "marker": found.group(0),
                    "context_terms": context_terms(text, found.start(), found.end()),
                }
            )
    evidence_items = []
    for values in seen.values():
        condition_counts = Counter(item["condition"].lower() for item in values)
        distinct_conditions = set(condition_counts)
        if len(distinct_conditions) < 2:
            continue
        comparable_pairs = [
            (left, right)
            for index, left in enumerate(values)
            for right in values[index + 1 :]
            if left["condition"].lower() != right["condition"].lower()
            and left["context_terms"] & right["context_terms"]
        ]
        if not comparable_pairs:
            continue
        pair = max(
            comparable_pairs,
            key=lambda candidates: len(candidates[0]["context_terms"] & candidates[1]["context_terms"]),
        )
        baseline_condition = max(condition_counts, key=condition_counts.get)
        source = next((candidate for candidate in pair if candidate["condition"].lower() == baseline_condition), pair[0])
        item = pair[1] if source is pair[0] else pair[0]
        evidence = _evidence(
            code="measurement_condition_inconsistency",
            category="internal_consistency",
            severity="medium",
            confidence=0.86,
            document_id=document_id,
            page=item["page"],
            bbox=item["bbox"],
            excerpt=_excerpt_around(item["text"], item["marker"]),
            explanation=(
                f"同一数值结果 {item['measurement']} 与多个条件标签关联（{', '.join(sorted(distinct_conditions))}），"
                "需要结合图注、正文和原始记录确认标签或结果归属。"
            ),
            limitations=["不同条件得到相同数值可能合理；本项只提示标签归属需要人工复核。"],
        )
        evidence["source_location"] = _location(document_id, source["page"], source["bbox"])
        evidence["source_excerpt"] = _excerpt_around(source["text"], source["marker"])
        evidence_items.append(evidence)
    return evidence_items


def _evidence(
    *,
    code: str,
    category: str,
    severity: str,
    confidence: float,
    document_id: str,
    page: int,
    bbox: list[float],
    excerpt: str,
    explanation: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "status": "needs_review",
        "severity": severity,
        "confidence": confidence,
        "subject_location": _location(document_id, page, bbox),
        "source_location": None,
        "subject_excerpt": excerpt,
        "source_excerpt": None,
        "explanation": explanation,
        "method": {"detector": "document-evidence-rules", "version": METHOD_VERSION, "parameters": {}},
        "limitations": limitations,
        "artifacts": [],
        "created_at": datetime.now(UTC).isoformat(),
    }


def _statistical_review(
    blocks: list[dict[str, Any]], document_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    measurement_pattern = re.compile(
        r"(?P<value>\d+(?:\.\d+)?)\s*(?:±|\+\s*/\s*-)\s*(?P<uncertainty>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    threshold_marker = re.compile(r"\(\s*<\s*(?P<threshold>\d+(?:\.\d+)?)\s*\)")
    average_claim = re.compile(
        r"average\s+(?P<label>[A-Za-z()\- ]{0,32}?)\s*(?:of|=)\s*(?:approximately|≈|~)?\s*"
        r"(?P<average>\d+(?:\.\d+)?)\s*(?P<unit>meV|eV|nm|ns|ms|ps|%)(?![A-Za-z])",
        re.IGNORECASE,
    )
    value_list = re.compile(
        r"(?P<values>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?){2,}\s*,?\s*(?:and\s*)?\d+(?:\.\d+)?)"
        r"\s*(?P<unit>meV|eV|nm|ns|ms|ps|%)(?![A-Za-z])",
        re.IGNORECASE,
    )
    average_claims_examined = 0
    value_list_comparisons = 0
    threshold_claims_examined = 0
    threshold_claim_budget = 1_000
    average_claim_budget = 500
    value_list_comparison_budget = 5_000
    threshold_budget_exhausted = False
    average_budget_exhausted = False
    for block in blocks:
        normalized_text = re.sub(r"(?<=\d)\s+\.\s*(?=\d)", ".", block["text"])
        for marker in threshold_marker.finditer(normalized_text):
            if threshold_claims_examined >= threshold_claim_budget:
                threshold_budget_exhausted = True
                break
            threshold_claims_examined += 1
            prefix_start = max(0, marker.start() - 120)
            measurements = list(measurement_pattern.finditer(normalized_text, prefix_start, marker.start()))
            if not measurements:
                continue
            match = measurements[-1]
            value = float(match.group("value"))
            uncertainty = float(match.group("uncertainty"))
            threshold = float(marker.group("threshold"))
            upper = value + uncertainty
            consistent = upper < threshold
            relation = "<" if consistent else "≥"
            calculation = f"{value:g} + {uncertainty:g} = {upper:g} {relation} {threshold:g}"
            checks.append({
                "kind": "threshold_with_uncertainty", "page": block["page"],
                "calculation": calculation, "consistent": consistent,
                "conclusion": (
                    "阈值关系在所报告不确定度范围内成立。" if consistent
                    else "点估计虽低于阈值，但加上所报告不确定度后跨越阈值，需要核对判定口径。"
                ),
            })
            if not consistent:
                item = _evidence(
                    code="statistical_threshold_uncertainty",
                    category="statistical_consistency",
                    severity="medium",
                    confidence=0.99,
                    document_id=document_id,
                    page=block["page"],
                    bbox=block["bbox"],
                    excerpt=_excerpt_around(block["text"], normalized_text[match.start():marker.end()]),
                    explanation=f"按论文报告的不确定度复算得到 {calculation}；区间上界跨越文中采用的阈值。",
                    limitations=["该复算只使用论文报告的点估计和不确定度；缺少原始计数时不能重建估计方法或误差分布。"],
                )
                item["method"]["parameters"] = {"calculation": calculation}
                evidence.append(item)
        if threshold_budget_exhausted:
            break

    for block in blocks:
        normalized_text = re.sub(r"(?<=\d)\s+\.\s*(?=\d)", ".", block["text"])
        for claim in average_claim.finditer(normalized_text):
            if average_claims_examined >= average_claim_budget:
                average_budget_exhausted = True
                break
            average_claims_examined += 1
            unit = claim.group("unit").lower()
            reported = float(claim.group("average"))
            candidates = []
            for listed in value_list.finditer(normalized_text):
                if value_list_comparisons >= value_list_comparison_budget:
                    average_budget_exhausted = True
                    break
                value_list_comparisons += 1
                if listed.group("unit").lower() != unit:
                    continue
                if listed.end() > claim.start():
                    continue
                values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", listed.group("values"))]
                if len(values) < 3:
                    continue
                computed = sum(values) / len(values)
                candidates.append((claim.start() - listed.end(), values, computed))
            if not candidates:
                continue
            _distance, values, computed = min(candidates, key=lambda item: item[0])
            tolerance = max(0.05, 0.05 * abs(reported))
            consistent = abs(computed - reported) <= tolerance
            calculation = f"mean({', '.join(f'{value:g}' for value in values)}) = {computed:g}; reported ≈ {reported:g} {unit}"
            checks.append({
                "kind": "reported_average", "page": block["page"],
                "calculation": calculation,
                "consistent": consistent,
                "conclusion": "所列数值的算术平均与报告值在舍入容差内一致。" if consistent else "所列数值的算术平均与报告值不一致。",
            })
            if not consistent:
                evidence.append(_evidence(
                    code="statistical_average_inconsistency",
                    category="statistical_consistency",
                    severity="medium",
                    confidence=0.99,
                    document_id=document_id,
                    page=block["page"],
                    bbox=block["bbox"],
                    excerpt=_excerpt_around(block["text"], claim.group(0)),
                    explanation=f"按同一文本区域列出的数值复算得到 {calculation}，与报告平均值不一致。",
                    limitations=["该复算只核对明确列出的数值及算术平均；不判断这些数值是否应使用加权平均或其他预先规定的方法。"],
                ))
        if average_budget_exhausted:
            break
    unique_checks = []
    seen_checks = set()
    for item in checks:
        key = (item["kind"], item["calculation"])
        if key not in seen_checks:
            unique_checks.append(item)
            seen_checks.add(key)
    return unique_checks, evidence, {
        "statistical_average_claims_examined": average_claims_examined,
        "statistical_average_claim_budget": average_claim_budget,
        "statistical_value_list_comparisons": value_list_comparisons,
        "statistical_value_list_comparison_budget": value_list_comparison_budget,
        "statistical_threshold_claims_examined": threshold_claims_examined,
        "statistical_threshold_claim_budget": threshold_claim_budget,
        "statistical_review_budget_exhausted": int(threshold_budget_exhausted or average_budget_exhausted),
    }


def _tile_signature(
    samples: bytes, width: int, height: int, stride: int, x: int, y: int, size: int
) -> tuple[bytes, int, float]:
    points = []
    signature_size = 16
    for row in range(signature_size):
        sample_y = min(height - 1, y + round((row + 0.5) * size / signature_size))
        for column in range(signature_size):
            sample_x = min(width - 1, x + round((column + 0.5) * size / signature_size))
            points.append(samples[sample_y * stride + sample_x])
    mean = sum(points) / len(points)
    signature = bytes(1 if value >= mean else 0 for value in points)
    variance = round(sum((value - mean) ** 2 for value in points) / len(points))
    light = sum(signature)
    minority_fraction = min(light, len(signature) - light) / len(signature)
    return signature, variance, minority_fraction


def _advanced_image_review(
    pdf_bytes: bytes, document_id: str, image_resources: dict[str, int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    evidence: list[dict[str, Any]] = []
    comparisons = 0
    comparison_budget = 50_000
    budget_exhausted = False
    images_screened = 0
    images_skipped_resource_limit = 0
    tile_sampling_adjusted = 0
    tiles_generated = 0
    resource_budget_exhausted = bool(image_resources["resource_budget_exhausted"])
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        eligible_images: list[tuple[int, int, fitz.Rect, int, int]] = []
        seen_xrefs: set[int] = set()
        for page_number, page in enumerate(pdf, start=1):
            for image in page.get_images(full=True):
                if image[0] in seen_xrefs:
                    continue
                seen_xrefs.add(image[0])
                rects = page.get_image_rects(image[0])
                if not rects:
                    continue
                rect = rects[0]
                if rect.get_area() / page.rect.get_area() < 0.01:
                    continue
                width, height = int(image[2]), int(image[3])
                if width < 160 or height < 100:
                    continue
                if width * height > MAX_IMAGE_PIXELS:
                    images_skipped_resource_limit += 1
                    continue
                if image_resources["decoded_pixels"] + width * height > MAX_TASK_IMAGE_DECODED_PIXELS:
                    images_skipped_resource_limit += 1
                    resource_budget_exhausted = True
                    image_resources["resource_budget_exhausted"] = 1
                    continue
                eligible_images.append((page_number, image[0], rect, width, height))

        for image_index, (page_number, xref, rect, width, height) in enumerate(eligible_images):
            if image_resources["decoded_pixels"] + width * height > MAX_TASK_IMAGE_DECODED_PIXELS:
                images_skipped_resource_limit += 1
                resource_budget_exhausted = True
                image_resources["resource_budget_exhausted"] = 1
                continue
            pixmap = fitz.Pixmap(fitz.csGRAY, fitz.Pixmap(pdf, xref))
            image_resources["decoded_pixels"] += pixmap.width * pixmap.height
            images_screened += 1
            tile_size = min(80, pixmap.width // 2, pixmap.height // 2)
            step = max(16, tile_size // 4)
            grid_columns = (pixmap.width - tile_size) // step + 1
            grid_rows = (pixmap.height - tile_size) // step + 1
            if grid_columns * grid_rows > MAX_IMAGE_TILES:
                step *= math.ceil(math.sqrt(grid_columns * grid_rows / MAX_IMAGE_TILES))
                tile_sampling_adjusted += 1
            tiles: list[dict[str, Any]] = []
            for y in range(0, pixmap.height - tile_size + 1, step):
                for x in range(0, pixmap.width - tile_size + 1, step):
                    if image_resources["tiles_generated"] >= MAX_TASK_IMAGE_TILES:
                        resource_budget_exhausted = True
                        image_resources["resource_budget_exhausted"] = 1
                        break
                    image_resources["tiles_generated"] += 1
                    tiles_generated += 1
                    signature, variance, minority_fraction = _tile_signature(
                        pixmap.samples, pixmap.width, pixmap.height, pixmap.stride, x, y, tile_size
                    )
                    if variance >= 350 and minority_fraction >= 0.12:
                        tiles.append({"x": x, "y": y, "signature": signature})
                if resource_budget_exhausted:
                    break
            found = False
            images_remaining = len(eligible_images) - image_index
            image_budget = (comparison_budget - comparisons) // images_remaining
            image_comparisons = 0
            image_truncated = False
            for left_index, left in enumerate(tiles):
                for right in tiles[left_index + 1:]:
                    # Vertically aligned regions are dominated by repeated axes, ticks, and panel furniture.
                    # Excluding them keeps this PDF-only screen high-precision; original-image review remains
                    # necessary for aligned copy-move cases.
                    if abs(left["x"] - right["x"]) < tile_size or abs(left["y"] - right["y"]) < tile_size:
                        continue
                    if image_comparisons >= image_budget:
                        image_truncated = True
                        break
                    comparisons += 1
                    image_comparisons += 1
                    hamming = sum(a != b for a, b in zip(left["signature"], right["signature"], strict=True))
                    if hamming > 2:
                        continue

                    def page_bbox(tile):
                        return [
                            rect.x0 + rect.width * tile["x"] / pixmap.width,
                            rect.y0 + rect.height * tile["y"] / pixmap.height,
                            rect.x0 + rect.width * (tile["x"] + tile_size) / pixmap.width,
                            rect.y0 + rect.height * (tile["y"] + tile_size) / pixmap.height,
                        ]

                    item = _evidence(
                        code="image_region_reuse_candidate",
                        category="image_forensics",
                        severity="medium",
                        confidence=round(1 - hamming / len(left["signature"]), 3),
                        document_id=document_id,
                        page=page_number,
                        bbox=page_bbox(right),
                        excerpt=f"第 {page_number} 页的一幅 PDF 内嵌图中存在两个高度近似且相互分离的局部区域。",
                        explanation="局部感知指纹发现非相邻区域高度近似，需要结合原图、图注和实验对象判断是否为合理重复结构。",
                        limitations=["PDF 局部相似只能生成复核候选；为减少坐标轴和多面板误报，本筛查不比较水平或垂直对齐区域，也不能据此判断图像操纵。"],
                    )
                    item["source_location"] = _location(document_id, page_number, page_bbox(left))
                    item["method"]["detector"] = "image-region-perceptual-hash"
                    item["method"]["parameters"] = {"tile_pixels": tile_size, "hamming_distance": hamming}
                    evidence.append(item)
                    found = True
                    break
                if image_truncated or found:
                    break
            budget_exhausted = budget_exhausted or image_truncated
    return evidence, {
        "advanced_images_screened": images_screened,
        "advanced_images_skipped_resource_limit": images_skipped_resource_limit,
        "image_tile_sampling_adjusted": tile_sampling_adjusted,
        "image_tiles_generated": tiles_generated,
        "image_task_tile_budget": MAX_TASK_IMAGE_TILES,
        "image_task_decoded_pixels": image_resources["decoded_pixels"],
        "image_task_decoded_pixel_budget": MAX_TASK_IMAGE_DECODED_PIXELS,
        "image_resource_budget_exhausted": int(resource_budget_exhausted),
        "image_regions_compared": comparisons,
        "image_region_comparison_budget": comparison_budget,
        "image_region_budget_exhausted": int(budget_exhausted),
        "image_region_reuse_candidates": len(evidence),
    }


def analyze_pdf(pdf_bytes: bytes, *, document_id: str) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    embedded_images_skipped_resource_limit = 0
    image_resources = {"decoded_pixels": 0, "tiles_generated": 0, "resource_budget_exhausted": 0}
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        metadata = pdf.metadata or {}
        title = unescape(_compact(metadata.get("title") or "")) or None
        digest_by_xref: dict[int, str] = {}
        for page_index, page in enumerate(pdf):
            for image in page.get_images(full=True):
                xref = image[0]
                rects = page.get_image_rects(xref)
                rect = rects[0] if rects else page.rect
                if rect.get_area() / page.rect.get_area() < 0.01:
                    continue
                if int(image[2]) * int(image[3]) > MAX_IMAGE_PIXELS:
                    embedded_images_skipped_resource_limit += 1
                    continue
                digest = digest_by_xref.get(xref)
                if digest is None:
                    pixels = int(image[2]) * int(image[3])
                    if image_resources["decoded_pixels"] + pixels > MAX_TASK_IMAGE_DECODED_PIXELS:
                        embedded_images_skipped_resource_limit += 1
                        image_resources["resource_budget_exhausted"] = 1
                        continue
                    pixmap = fitz.Pixmap(pdf, xref)
                    image_resources["decoded_pixels"] += pixmap.width * pixmap.height
                    digest = hashlib.sha256(pixmap.samples).hexdigest()
                    digest_by_xref[xref] = digest
                images.append(
                    {
                        "page": page_index + 1,
                        "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                        "digest": digest,
                    }
                )
            for raw in page.get_text("blocks"):
                text = _compact(raw[4])
                if text:
                    blocks.append(
                        {
                            "page": page_index + 1,
                            "bbox": [float(value) for value in raw[:4]],
                            "text": text,
                        }
                    )
        page_count = pdf.page_count

    all_text = "\n".join(block["text"] for block in blocks)
    evidence: list[dict[str, Any]] = []

    first_image_by_digest: dict[str, dict[str, Any]] = {}
    for image in images:
        previous = first_image_by_digest.get(image["digest"])
        if previous is None:
            first_image_by_digest[image["digest"]] = image
            continue
        item = _evidence(
            code="embedded_image_reuse_candidate",
            category="image_similarity",
            severity="medium",
            confidence=1.0,
            document_id=document_id,
            page=image["page"],
            bbox=image["bbox"],
            excerpt=f"第 {image['page']} 页的 PDF 内嵌位图与第 {previous['page']} 页位图像素相同。",
            explanation="PDF 内出现像素相同的非小型位图，需要结合图号、版式用途和原图判断是否为合理复用。",
            limitations=["仅凭 PDF 内嵌图片不能认证原始图像真实性，也不能据此判断存在图像操纵。"],
        )
        item["source_location"] = _location(document_id, previous["page"], previous["bbox"])
        evidence.append(item)

    evidence.extend(_cross_condition_subject_evidence(blocks, document_id))
    evidence.extend(_measurement_context_evidence(blocks, document_id))
    statistical_checks, statistical_evidence, statistical_coverage = _statistical_review(blocks, document_id)
    image_evidence, image_coverage = _advanced_image_review(pdf_bytes, document_id, image_resources)
    evidence.extend(statistical_evidence)
    evidence.extend(image_evidence)

    for block in blocks:
        lower = block["text"].lower()
        if "available" in lower and "reasonable request" in lower:
            evidence.append(
                _evidence(
                    code="data_not_directly_available",
                    category="reproducibility",
                    severity="medium",
                    confidence=0.99,
                    document_id=document_id,
                    page=block["page"],
                    bbox=block["bbox"],
                    excerpt=block["text"],
                    explanation="论文未给出可直接核验的数据仓库，只声明可向作者索取；依赖原始数据的结果目前不能独立复算。",
                    limitations=["未向作者发起数据请求，也未取得补充信息。"],
                )
            )

    statistical_mentions = max(
        len(statistical_checks),
        len(re.findall(r"(?:±|p\s*[<=>]|g\s*\(\s*2\s*\)|FWHM|lifetime|\baverage\b)", all_text, re.IGNORECASE)),
    )
    citation_markers = {int(value) for value in re.findall(r"\[(\d+)\]", all_text)}
    statistical_consistent = sum(1 for item in statistical_checks if item["consistent"])
    statistical_inconsistent = len(statistical_checks) - statistical_consistent
    return {
        "title": title,
        "document_id": document_id,
        "method_version": METHOD_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "coverage": {
            "pages_total": page_count,
            "pages_with_text": len({block["page"] for block in blocks}),
            "text_blocks_reviewed": len(blocks),
            "embedded_images_screened": len(images),
            "embedded_images_skipped_resource_limit": embedded_images_skipped_resource_limit,
            "statistical_mentions_detected": statistical_mentions,
            "statistical_mentions_recomputed": len(statistical_checks),
            "statistical_checks_consistent": statistical_consistent,
            "statistical_checks_inconsistent": statistical_inconsistent,
            "statistical_mentions_not_recomputable": max(0, statistical_mentions - len(statistical_checks)),
            "statistical_checks": statistical_checks,
            **statistical_coverage,
            "references_total": max(citation_markers, default=0),
            "reference_full_texts_obtained": 0,
            **image_coverage,
        },
        "statistical_checks": statistical_checks,
        "evidence": evidence,
        "decisions": [],
        "limitations": [
            "本轮为 PDF-only 审核，未取得论文所依赖的原始数据、分析文件、原始图像或研究记录。",
            "引用支持与文本复用结论受已合法取得的引用全文覆盖率限制。",
            "PDF 内嵌位图仅进行了精确像素复用初筛；小型装饰图已排除，无原图时不能认证图片真实性。",
        ],
    }


def compare_texts(subject: str, source: str, *, minimum_words: int = 12) -> list[dict[str, Any]]:
    subject_words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", subject)
    source_words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", source)
    matcher = SequenceMatcher(None, [word.lower() for word in subject_words], [word.lower() for word in source_words], autojunk=False)
    matches: list[dict[str, Any]] = []
    for block in matcher.get_matching_blocks():
        if block.size < minimum_words:
            continue
        subject_excerpt = " ".join(subject_words[block.a : block.a + block.size])
        source_excerpt = " ".join(source_words[block.b : block.b + block.size])
        matches.append(
            {
                "category": "text_reuse",
                "status": "needs_review",
                "severity": "medium" if block.size < 25 else "high",
                "confidence": min(0.99, 0.65 + block.size / 100),
                "subject_excerpt": subject_excerpt,
                "source_excerpt": source_excerpt,
                "matched_words": block.size,
                "method": {"detector": "exact-word-alignment", "version": METHOD_VERSION},
                "limitations": ["连续词语重合不等于不当复用，仍需结合引文、直接引语和学科惯用表达复核。"],
            }
        )
    return sorted(matches, key=lambda item: item["matched_words"], reverse=True)


def _font_name() -> str:
    name = "SBDC-CJK"
    if name not in pdfmetrics.getRegisteredFontNames():
        font_source = next(((path, index) for path, index in FONT_PATHS if path.exists()), None)
        if font_source is None:
            fallback = "STSong-Light"
            if fallback not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(fallback))
            return fallback
        path, index = font_source
        pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=index))
    return name


def render_pdf_report(analysis: dict[str, Any]) -> bytes:
    font = _font_name()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"SBDC 深度审核报告 - {analysis.get('title') or '未识别题名'}",
        author="Source-Based Deep Check",
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle("BodyCN", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=15, textColor=colors.HexColor("#253047"), spaceAfter=7)
    title_style = ParagraphStyle("TitleCN", parent=body, fontSize=22, leading=29, textColor=colors.HexColor("#10233F"), alignment=TA_CENTER, spaceAfter=12)
    h1 = ParagraphStyle("H1CN", parent=body, fontSize=15, leading=21, textColor=colors.HexColor("#0C5C66"), spaceBefore=9, spaceAfter=8)
    h2 = ParagraphStyle("H2CN", parent=body, fontSize=11, leading=16, textColor=colors.HexColor("#10233F"), spaceBefore=6, spaceAfter=4)
    small = ParagraphStyle("SmallCN", parent=body, fontSize=8, leading=12, textColor=colors.HexColor("#5D6675"))
    story: list[Any] = [
        Paragraph("Source-Based Deep Check", h2),
        Paragraph("科研诚信证据审核报告", title_style),
        Paragraph(escape(str(analysis.get("title") or "未识别论文题名")), h2),
        Spacer(1, 4 * mm),
        Paragraph("报告定位", h1),
        Paragraph("本报告组织可复核证据和待复核结论，不构成对作者主观故意或学术不端的自动判定。", body),
    ]
    coverage = analysis.get("coverage", {})
    coverage_rows = [
        ["审核对象", "实际覆盖"],
        ["PDF 页面", f"{coverage.get('pages_with_text', 0)} / {coverage.get('pages_total', 0)} 页有可提取文本"],
        ["正文文本块", str(coverage.get("text_blocks_reviewed", 0))],
        [
            "非小型 PDF 内嵌位图初筛",
            f"检查 {coverage.get('embedded_images_screened', 0)}；资源限界跳过 {coverage.get('embedded_images_skipped_resource_limit', 0)}",
        ],
        ["参考文献全文", f"{coverage.get('reference_full_texts_obtained', 0)} / {coverage.get('references_total', 0)}"],
        ["进入文本对照", str(coverage.get("reference_full_texts_compared", 0))],
        [
            "来源候选块比较",
            f"{coverage.get('reference_candidate_comparisons', 0)} / {coverage.get('reference_candidate_budget', 0)}"
            + ("（已达任务上限）" if coverage.get("reference_candidate_budget_exhausted") else ""),
        ],
        ["识别到的统计表达", str(coverage.get("statistical_mentions_detected", 0))],
        [
            "完成统计复算",
            f"{coverage.get('statistical_mentions_recomputed', 0)}；一致 {coverage.get('statistical_checks_consistent', 0)}，待复核 {coverage.get('statistical_checks_inconsistent', 0)}",
        ],
        [
            "统计规则计算预算",
            f"阈值 {coverage.get('statistical_threshold_claims_examined', 0)} / {coverage.get('statistical_threshold_claim_budget', 0)}；"
            f"均值 {coverage.get('statistical_average_claims_examined', 0)} / {coverage.get('statistical_average_claim_budget', 0)}；"
            f"列表比较 {coverage.get('statistical_value_list_comparisons', 0)} / {coverage.get('statistical_value_list_comparison_budget', 0)}"
            + ("（已达任务上限）" if coverage.get("statistical_review_budget_exhausted") else ""),
        ],
        [
            "语义近似候选",
            f"比较 {coverage.get('semantic_candidate_comparisons', 0)} / {coverage.get('semantic_candidate_budget', 0)} 个文本块；候选 {coverage.get('semantic_similarity_candidates', 0)}"
            + ("（已达任务上限）" if coverage.get("semantic_candidate_budget_exhausted") else ""),
        ],
        [
            "引用论断支持核对",
            f"有全文 {coverage.get('citation_contexts_with_full_text', 0)} / {coverage.get('citation_contexts_detected', 0)}；文本对齐 {coverage.get('citation_support_matches', 0)}，未决 {coverage.get('citation_support_unresolved', 0)}；"
            f"比较 {coverage.get('citation_candidate_comparisons', 0)} / {coverage.get('citation_candidate_budget', 0)}"
            + ("（已达任务上限）" if coverage.get("citation_candidate_budget_exhausted") else ""),
        ],
        [
            "图片局部区域比较",
            f"{coverage.get('image_regions_compared', 0)} / {coverage.get('image_region_comparison_budget', 0)} 组；候选 {coverage.get('image_region_reuse_candidates', 0)}"
            f"；资源限界跳过 {coverage.get('advanced_images_skipped_resource_limit', 0)}；稀疏采样 {coverage.get('image_tile_sampling_adjusted', 0)} 幅"
            + ("（已达任务上限）" if coverage.get("image_region_budget_exhausted") else ""),
        ],
        [
            "图片任务资源预算",
            f"解码像素 {coverage.get('image_task_decoded_pixels', 0)} / {coverage.get('image_task_decoded_pixel_budget', 0)}；"
            f"生成图块 {coverage.get('image_tiles_generated', 0)} / {coverage.get('image_task_tile_budget', 0)}"
            + ("（已达任务上限）" if coverage.get("image_resource_budget_exhausted") else ""),
        ],
    ]
    table = Table(coverage_rows, colWidths=[45 * mm, 105 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C5C66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F4F7F8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD6DA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([Paragraph("实际审核覆盖", h1), table, Spacer(1, 4 * mm)])
    statistical_checks = analysis.get("statistical_checks") or coverage.get("statistical_checks") or []
    if statistical_checks:
        story.append(Paragraph("统计复算", h1))
        for item in statistical_checks:
            state = "一致" if item.get("consistent") else "待复核"
            story.append(Paragraph(
                f"第 {item.get('page') or '未知'} 页 · {state}：{escape(str(item.get('calculation', '')))}。{escape(str(item.get('conclusion', '')))}",
                body,
            ))
        story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("需要复核的证据", h1))

    descriptions = {
        "cross_condition_subject_mismatch": "不同条件的结果来自不同研究对象",
        "measurement_condition_inconsistency": "同一数值结果关联多个条件标签",
        "data_not_directly_available": "关键原始数据未随论文直接提供",
        "embedded_image_reuse_candidate": "PDF 内出现相同位图候选",
        "reference_text_reuse_candidate": "与引用来源存在连续文本重合",
        "reference_semantic_similarity_candidate": "与引用来源存在语义近似候选",
        "citation_numeric_mismatch_candidate": "引用论断与来源片段的数值需要核对",
        "citation_direction_conflict_candidate": "引用论断与来源片段的方向需要核对",
        "statistical_threshold_uncertainty": "统计阈值在不确定度范围内需要复核",
        "statistical_average_inconsistency": "报告平均值与同一区域所列数值不一致",
        "image_region_reuse_candidate": "图片内存在局部区域复用候选",
    }
    decisions_by_id = {item.get("evidence_id"): item for item in analysis.get("decisions", []) if item.get("evidence_id")}
    decisions_by_code = {item.get("evidence_code"): item for item in analysis.get("decisions", [])}
    decision_labels = {
        "confirmed": "确认存在差异",
        "needs_material": "需要补充材料",
        "insufficient": "证据不足",
        "reasonable": "合理或可接受",
    }
    for index, item in enumerate(analysis.get("evidence", []), start=1):
        code = item.get("code", "evidence")
        location = item.get("subject_location", {})
        evidence_block: list[Any] = [
            Paragraph(f"{index}. {escape(descriptions.get(code, code))}", h2),
            Paragraph(f"位置：第 {location.get('page', '未知')} 页　识别置信度：{item.get('confidence', 0):.2f}", small),
            Paragraph(escape(str(item.get("explanation", ""))), body),
            Paragraph(f"原文：{escape(str(item.get('subject_excerpt', '')))}", small),
        ]
        source_location = item.get("source_location") or {}
        if source_location.get("page"):
            evidence_block.append(
                Paragraph(f"对照位置：第 {source_location['page']} 页", small)
            )
        source = (item.get("method") or {}).get("source") or {}
        if source:
            source_identity = "　".join(
                value for value in (
                    str(source.get("title") or ""),
                    f"DOI {source['doi']}" if source.get("doi") else "",
                    f"文件 SHA-256 {source['sha256']}" if source.get("sha256") else "",
                ) if value
            )
            if source_identity:
                evidence_block.append(Paragraph(f"对照来源：{escape(source_identity)}", small))
        if item.get("source_excerpt"):
            evidence_block.append(Paragraph(f"来源原文：{escape(str(item['source_excerpt']))}", small))
        for limitation in item.get("limitations", []):
            evidence_block.append(Paragraph(f"方法限制：{escape(str(limitation))}", small))
        if code == "cross_condition_subject_mismatch":
            evidence_block.append(Paragraph("复核含义：不同条件下的观察可以分别成立，但不能据此证明同一研究对象发生了对应变化。", body))
        decision = decisions_by_id.get(item.get("id")) or decisions_by_code.get(code)
        if decision:
            label = decision_labels.get(str(decision.get("decision")), str(decision.get("decision")))
            evidence_block.append(Paragraph(f"人工裁决：{escape(label)}；理由：{escape(str(decision.get('reason')))}", body))
        story.append(CondPageBreak(55 * mm))
        story.extend(evidence_block)

    story.extend([Spacer(1, 4 * mm), Paragraph("能力边界与下一步证据", h1)])
    for item in analysis.get("limitations", []):
        story.extend([Paragraph(f"• {escape(str(item))}", body), Spacer(1, 1 * mm)])
    decision_counts = Counter(str(item.get("decision")) for item in analysis.get("decisions", []))
    decision_summary = "；".join(
        f"{decision_labels.get(key, key)} {value} 项"
        for key, value in ((key, decision_counts[key]) for key in ("confirmed", "needs_material", "insufficient", "reasonable"))
        if value
    ) or "尚无人工裁决"
    story.extend([
        Paragraph("审查结论", h1),
        Paragraph(
            f"本轮共形成 {len(analysis.get('evidence', []))} 项证据记录；人工复核结果为：{decision_summary}。"
            "报告保留每项原文位置、人工裁决和方法限制；"
            "未取得的引用全文、原始数据或原始图像不被视为已核验，任何异常均不自动等同于学术不端。",
            body,
        ),
        Paragraph(f"方法版本：{escape(str(analysis.get('method_version', METHOD_VERSION)))}　生成时间：{escape(str(analysis.get('generated_at', '')))}", small),
    ])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#697386"))
        canvas.drawString(18 * mm, 10 * mm, "SBDC - 证据优先，不自动定性")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
