import io
import hashlib
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


METHOD_VERSION = "pdf-evidence-rules/1.2.0"
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


def analyze_pdf(pdf_bytes: bytes, *, document_id: str) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        metadata = pdf.metadata or {}
        title = unescape(_compact(metadata.get("title") or "")) or None
        for page_index, page in enumerate(pdf):
            for image in page.get_images(full=True):
                xref = image[0]
                pixmap = fitz.Pixmap(pdf, xref)
                digest = hashlib.sha256(pixmap.samples).hexdigest()
                rects = page.get_image_rects(xref)
                rect = rects[0] if rects else page.rect
                if rect.get_area() / page.rect.get_area() < 0.01:
                    continue
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

    statistical_mentions = len(re.findall(r"(?:±|p\s*[<=>]|g\s*\(\s*2\s*\)|FWHM|lifetime)", all_text, re.IGNORECASE))
    citation_markers = {int(value) for value in re.findall(r"\[(\d+)\]", all_text)}
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
            "statistical_mentions_detected": statistical_mentions,
            "references_total": max(citation_markers, default=0),
            "reference_full_texts_obtained": 0,
        },
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
        ["非小型 PDF 内嵌位图初筛", str(coverage.get("embedded_images_screened", 0))],
        ["参考文献全文", f"{coverage.get('reference_full_texts_obtained', 0)} / {coverage.get('references_total', 0)}"],
        ["进入文本对照", str(coverage.get("reference_full_texts_compared", 0))],
        [
            "来源候选块比较",
            f"{coverage.get('reference_candidate_comparisons', 0)} / {coverage.get('reference_candidate_budget', 0)}"
            + ("（已达任务上限）" if coverage.get("reference_candidate_budget_exhausted") else ""),
        ],
        ["识别到的统计表达", str(coverage.get("statistical_mentions_detected", 0))],
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
    story.extend([Paragraph("实际审核覆盖", h1), table, Spacer(1, 4 * mm), Paragraph("需要复核的证据", h1)])

    descriptions = {
        "cross_condition_subject_mismatch": "不同条件的结果来自不同研究对象",
        "measurement_condition_inconsistency": "同一数值结果关联多个条件标签",
        "data_not_directly_available": "关键原始数据未随论文直接提供",
        "embedded_image_reuse_candidate": "PDF 内出现相同位图候选",
        "reference_text_reuse_candidate": "与引用来源存在连续文本重合",
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
    story.extend([
        Paragraph("审查结论", h1),
        Paragraph(
            f"本轮共形成 {len(analysis.get('evidence', []))} 项待复核证据。报告保留每项原文位置、人工裁决和方法限制；"
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
