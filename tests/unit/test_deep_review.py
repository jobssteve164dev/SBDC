import importlib
import io
import fitz
import pytest
from PIL import Image, ImageDraw


def deep_review_module():
    try:
        return importlib.import_module("sbdc_worker.deep_review")
    except ModuleNotFoundError:
        pytest.fail("深度审核管线尚未实现")


def make_audit_pdf() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 280),
        "Results and Discussion\n"
        "The lifetime is 0.98 ns at 4.7 K. A clear antibunching effect was observed.\n"
        "The measurements at 4.6 K and room temperature were not obtained from the same QD.\n"
        "Figure 3. The lifetime is 0.98 ns at 4.5 K.\n"
        "Data supporting the findings are available from the author upon reasonable request.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()
    return data


def make_unrelated_domain_pdf() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 280),
        "Clinical Results\n"
        "The response latency was 12.5 ms at 20 °C.\n"
        "The response latency was 12.5 ms at 25 °C.\n"
        "Baseline and follow-up measurements were not obtained from the same participants.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()
    return data


def make_pdf_with_reused_image() -> bytes:
    image = Image.new("RGB", (80, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 68, 68), fill="black")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    for _ in range(2):
        page = pdf.new_page()
        page.insert_image(fitz.Rect(72, 72, 232, 232), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()
    return data


def test_deep_review_preserves_locations_and_surfaces_material_limitations():
    review = deep_review_module()

    result = review.analyze_pdf(make_audit_pdf(), document_id="source-paper")

    by_code = {item["code"]: item for item in result["evidence"]}
    assert by_code["cross_condition_subject_mismatch"]["subject_location"]["page"] == 1
    assert "not obtained from the same QD" in by_code["cross_condition_subject_mismatch"]["subject_excerpt"]
    assert by_code["measurement_condition_inconsistency"]["status"] == "needs_review"
    assert "0.98 ns" in by_code["measurement_condition_inconsistency"]["explanation"]
    assert by_code["data_not_directly_available"]["severity"] == "medium"
    assert result["coverage"]["pages_total"] == 1
    assert result["coverage"]["pages_with_text"] == 1


def test_deep_review_rules_apply_outside_the_quantum_dot_sample():
    review = deep_review_module()

    result = review.analyze_pdf(make_unrelated_domain_pdf(), document_id="clinical-paper")

    codes = {item["code"] for item in result["evidence"]}
    assert "cross_condition_subject_mismatch" in codes
    assert "measurement_condition_inconsistency" in codes
    subject_item = next(item for item in result["evidence"] if item["code"] == "cross_condition_subject_mismatch")
    assert subject_item["severity"] == "medium"
    assert "statistical_mentions_detected" in result["coverage"]
    assert "statistical_mentions_reviewed" not in result["coverage"]


def test_respectively_keeps_parallel_measurements_and_conditions_aligned():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 280),
        "Lifetimes were 0.98 ns at 4.7 K and 0.94 ns at RT. "
        "The lifetimes of 0.98 and 0.94 ns at 4.5 K and RT, respectively, were reported.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="parallel-values")

    item = next(item for item in result["evidence"] if item["code"] == "measurement_condition_inconsistency")
    assert "0.98 ns" in item["explanation"]
    assert "0.94 ns" not in item["explanation"]


def test_measurement_conflict_points_to_the_outlying_condition_not_a_later_repetition():
    review = deep_review_module()
    pdf = fitz.open()
    for text in (
        "The response latency was 12.5 ms at 20 °C.",
        "The response latency was 12.5 ms at 25 °C.",
        "The response latency was 12.5 ms at 20 °C.",
    ):
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 520, 180), text, fontsize=11)
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="repeated-baseline")

    item = next(item for item in result["evidence"] if item["code"] == "measurement_condition_inconsistency")
    assert item["subject_location"]["page"] == 2
    assert item["source_location"]["page"] == 1


def test_generic_rules_do_not_confuse_conditions_with_subjects_or_unrelated_measurements():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 280),
        "The experiments were not conducted under the same conditions. "
        "The incubation duration was 10 ms at 20 °C. "
        "The response latency was 10 ms at 25 °C.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="negative-controls")

    codes = {item["code"] for item in result["evidence"]}
    assert "cross_condition_subject_mismatch" not in codes
    assert "measurement_condition_inconsistency" not in codes


def test_multiple_findings_from_the_same_rule_keep_each_location():
    review = deep_review_module()
    pdf = fitz.open()
    for text in (
        "Measurements across conditions were not obtained from the same participants.",
        "Results across visits were not collected from the same specimens.",
    ):
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 520, 180), text, fontsize=11)
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="multiple-findings")

    items = [item for item in result["evidence"] if item["code"] == "cross_condition_subject_mismatch"]
    assert [item["subject_location"]["page"] for item in items] == [1, 2]


def test_text_comparison_returns_auditable_spans_not_an_integrity_verdict():
    review = deep_review_module()
    subject = (
        "The nanowires were grown on silicon substrate under nitrogen rich conditions. "
        "The photon correlation measurement confirms an antibunching effect at room temperature."
    )
    source = (
        "We grew nanowires on silicon substrate under nitrogen rich conditions. "
        "A different experiment followed."
    )

    matches = review.compare_texts(subject, source, minimum_words=7)

    assert matches
    assert "silicon substrate under nitrogen rich conditions" in matches[0]["subject_excerpt"]
    assert matches[0]["category"] == "text_reuse"
    assert matches[0]["status"] == "needs_review"
    assert "plagiarism" not in str(matches).lower()


def test_image_screen_reports_reused_published_images_without_claiming_manipulation():
    review = deep_review_module()

    result = review.analyze_pdf(make_pdf_with_reused_image(), document_id="source-paper")

    item = next(item for item in result["evidence"] if item["code"] == "embedded_image_reuse_candidate")
    assert item["category"] == "image_similarity"
    assert item["status"] == "needs_review"
    assert "真实性" in item["limitations"][0]
    assert result["coverage"]["embedded_images_screened"] == 2


def test_image_screen_ignores_repeated_small_decorative_bitmaps():
    review = deep_review_module()
    image = Image.new("RGB", (10, 10), "black")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    for _ in range(2):
        page = pdf.new_page()
        page.insert_image(fitz.Rect(20, 20, 30, 30), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="decorative-images")

    assert result["coverage"]["embedded_images_screened"] == 0
    assert not any(item["category"] == "image_similarity" for item in result["evidence"])


def test_pdf_report_states_coverage_decisions_and_evidence_boundaries():
    review = deep_review_module()
    analysis = review.analyze_pdf(make_audit_pdf(), document_id="source-paper")
    analysis["title"] = "Room Temperature Triggered Single Photon Emission"
    analysis["coverage"].update(
        {
            "references_total": 52,
            "reference_full_texts_obtained": 0,
            "embedded_images_screened": 1,
        }
    )
    analysis["decisions"] = [
        {
            "evidence_code": "measurement_condition_inconsistency",
            "decision": "confirmed",
            "reason": "正文与图注温度标签不一致。",
        }
    ]
    analysis["coverage"]["reference_full_texts_compared"] = 1
    analysis["evidence"].append(
        {
            "code": "reference_text_reuse_candidate",
            "confidence": 0.91,
            "subject_location": {"page": 1},
            "source_location": {"page": 7},
            "subject_excerpt": "Submitted passage preserved in the report.",
            "source_excerpt": "Cited source passage preserved in the report.",
            "explanation": "需要结合引用方式人工复核。",
            "method": {"source": {"title": "Cited Source Title", "doi": "10.1000/source", "sha256": "abc123"}},
            "limitations": ["文本相似不等于抄袭。"],
        }
    )

    report_bytes = review.render_pdf_report(analysis)

    assert report_bytes.startswith(b"%PDF-")
    with fitz.open(stream=report_bytes, filetype="pdf") as report:
        assert report.page_count >= 2
        assert report.metadata["title"].startswith("SBDC 深度审核报告")
        report_text = "\n".join(page.get_text() for page in report)
        assert "对照位置" in report_text
        assert "不同条件得到相同数值可能合理" in report_text
        assert "进入文本对照" in report_text
        assert "Cited Source Title" in report_text
        assert "10.1000/source" in report_text
        assert "Cited source passage preserved" in report_text
        assert "abc123" in report_text


def test_statistical_review_recomputes_threshold_and_reported_average_from_pdf_text():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 350),
        "The measured values were 2.8, 1.6, 3.1, and 3.5 meV, with an average FWHM of approximately 2.7 meV. "
        "At room temperature g(2)(0) = 0.35 +/- 0.05 (< 0.5), confirming the threshold criterion.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="statistics")

    checks = result["statistical_checks"]
    assert any(item["kind"] == "reported_average" and item["consistent"] for item in checks)
    threshold = next(item for item in checks if item["kind"] == "threshold_with_uncertainty")
    assert threshold["calculation"] == "0.35 + 0.05 = 0.4 < 0.5"
    assert threshold["consistent"] is True
    assert result["coverage"]["statistical_mentions_recomputed"] == 2
    assert result["coverage"]["statistical_checks_consistent"] == 2


def test_statistical_review_surfaces_uncertainty_that_crosses_a_claimed_threshold():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 220),
        "The response was 0.48 +/- 0.05 (< 0.5), confirming the threshold criterion.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="statistics-crossing")

    item = next(item for item in result["evidence"] if item["code"] == "statistical_threshold_uncertainty")
    assert item["status"] == "needs_review"
    assert "0.48 + 0.05 = 0.53" in item["explanation"]
    assert item["method"]["parameters"]["calculation"] == "0.48 + 0.05 = 0.53 ≥ 0.5"
    assert result["coverage"]["statistical_checks_inconsistent"] == 1


def test_statistical_review_does_not_pair_an_average_with_an_unrelated_distant_list():
    review = deep_review_module()
    pdf = fitz.open()
    first = pdf.new_page()
    first.insert_text((72, 100), "The average lifetime of 2.7 ns was reported.", fontsize=11)
    second = pdf.new_page()
    second.insert_text((72, 100), "Unrelated calibration values were 2.8, 1.6, 3.1, and 3.5 ns.", fontsize=11)
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="unrelated-average")

    assert not any(item["kind"] == "reported_average" for item in result["statistical_checks"])


def test_statistical_review_routes_an_inconsistent_average_to_human_review():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 220),
        "The measured values were 1.0, 2.0, 3.0, and 4.0 ns, with an average lifetime of 4.5 ns.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="inconsistent-average")

    item = next(item for item in result["evidence"] if item["code"] == "statistical_average_inconsistency")
    assert item["status"] == "needs_review"
    assert "mean(1, 2, 3, 4) = 2.5" in item["explanation"]


def test_statistical_average_review_has_a_bounded_claim_budget():
    review = deep_review_module()
    blocks = [
        {
            "page": index + 1,
            "bbox": [1, 2, 3, 4],
            "text": "Values 1.0, 2.0, 3.0, and 4.0 ns; average lifetime of 2.5 ns.",
        }
        for index in range(501)
    ]

    _checks, _evidence, coverage = review._statistical_review(blocks, "bounded-statistics")

    assert coverage["statistical_average_claims_examined"] == 500
    assert coverage["statistical_review_budget_exhausted"] == 1


def test_statistical_review_binds_each_average_to_the_nearest_preceding_list():
    review = deep_review_module()
    blocks = [{
        "page": 1,
        "bbox": [1, 2, 3, 4],
        "text": (
            "Group A values were 1, 2, 3, and 4 ns; average lifetime of 2.5 ns. "
            "Group B values were 10, 10, 10, and 10 ns; average lifetime of 2.5 ns."
        ),
    }]

    checks, evidence, _coverage = review._statistical_review(blocks, "grouped-statistics")

    assert len(checks) == 2
    assert [item["consistent"] for item in checks] == [True, False]
    assert len([item for item in evidence if item["code"] == "statistical_average_inconsistency"]) == 1


def test_statistical_review_normalizes_spaced_decimals_and_deduplicates_repeated_claims():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 300),
        "The values were 2.8, 1.6, 3.1, and 3.5 meV, with an average FWHM of 2.7 meV. "
        "The average FWHM of 2.7 meV was repeated. g(2)(0) = 0.35 +/- 0 .05 (< 0.5).",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="statistics-deduplicated")

    assert [item["kind"] for item in result["statistical_checks"]].count("reported_average") == 1
    threshold = next(item for item in result["statistical_checks"] if item["kind"] == "threshold_with_uncertainty")
    assert threshold["calculation"] == "0.35 + 0.05 = 0.4 < 0.5"


def test_statistical_threshold_uses_the_measurement_nearest_the_threshold_marker():
    review = deep_review_module()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 220),
        "The values were 0.24 +/- 0.06 and 0.35 +/- 0.05 (< 0.5) at low and room temperature, respectively.",
        fontsize=11,
    )
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="nearest-threshold")

    threshold = next(item for item in result["statistical_checks"] if item["kind"] == "threshold_with_uncertainty")
    assert threshold["calculation"] == "0.35 + 0.05 = 0.4 < 0.5"


def test_advanced_image_screen_detects_nonadjacent_repeated_regions_and_preserves_coordinates():
    review = deep_review_module()
    image = Image.new("RGB", (320, 200), "white")
    draw = ImageDraw.Draw(image)
    for offset_x, offset_y in ((20, 20), (220, 100)):
        draw.rectangle((offset_x, offset_y, offset_x + 60, offset_y + 60), fill="black")
        draw.line((offset_x + 5, offset_y + 50, offset_x + 55, offset_y + 10), fill="white", width=5)
        draw.ellipse((offset_x + 18, offset_y + 18, offset_x + 38, offset_y + 38), fill="gray")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_image(fitz.Rect(72, 72, 520, 324), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="copy-move")

    item = next(item for item in result["evidence"] if item["code"] == "image_region_reuse_candidate")
    assert item["category"] == "image_forensics"
    assert item["subject_location"]["page"] == 1
    assert item["source_location"]["page"] == 1
    assert item["subject_location"]["bbox"] != item["source_location"]["bbox"]
    assert "不能据此判断图像操纵" in item["limitations"][0]
    assert result["coverage"]["image_regions_compared"] > 0


def test_advanced_image_screen_stops_at_a_reported_comparison_budget():
    review = deep_review_module()
    image = Image.new("L", (800, 800))
    image.putdata([(x * 37 + y * 19 + (x * y) % 251) % 256 for y in range(800) for x in range(800)])
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page(width=900, height=900)
    page.insert_image(fitz.Rect(50, 50, 850, 850), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="image-budget")

    assert result["coverage"]["image_regions_compared"] == 50_000
    assert result["coverage"]["image_region_comparison_budget"] == 50_000
    assert result["coverage"]["image_region_budget_exhausted"] == 1


def test_advanced_image_screen_rejects_oversized_embedded_images_before_decode():
    review = deep_review_module()
    image = Image.new("L", (2100, 2100), "white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_image(fitz.Rect(50, 50, 550, 750), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="oversized-image")

    assert result["coverage"]["advanced_images_screened"] == 0
    assert result["coverage"]["advanced_images_skipped_resource_limit"] == 1
    assert result["coverage"]["embedded_images_screened"] == 0
    assert result["coverage"]["embedded_images_skipped_resource_limit"] == 1


def test_advanced_image_screen_ignores_repeated_small_plot_markers():
    review = deep_review_module()
    image = Image.new("L", (1500, 1000), "white")
    draw = ImageDraw.Draw(image)
    for offset in (200, 900):
        draw.rectangle((offset, 300, offset + 18, 318), fill="black")
        draw.line((offset, 300, offset + 18, 318), fill="gray", width=2)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_image(fitz.Rect(72, 72, 522, 372), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="small-markers")

    assert not any(item["code"] == "image_region_reuse_candidate" for item in result["evidence"])


def test_advanced_image_screen_ignores_repeated_aligned_plot_axes():
    review = deep_review_module()
    image = Image.new("L", (240, 440), "white")
    axis_fragment = Image.new("L", (80, 80))
    axis_fragment.putdata([(x * 23 + y * 31 + (x * y) % 197) % 256 for y in range(80) for x in range(80)])
    image.paste(axis_fragment, (20, 20))
    image.paste(axis_fragment, (20, 300))
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page(width=420, height=520)
    page.insert_image(fitz.Rect(50, 50, 370, 470), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="plot-axes")

    assert not any(item["code"] == "image_region_reuse_candidate" for item in result["evidence"])


def test_advanced_image_budget_is_shared_and_repeated_xrefs_are_not_rescreened():
    review = deep_review_module()
    image = Image.new("L", (650, 650))
    image.putdata([(x * 31 + y * 23 + (x * y) % 241) % 256 for y in range(650) for x in range(650)])
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    for _ in range(2):
        page = pdf.new_page(width=750, height=750)
        page.insert_image(fitz.Rect(50, 50, 700, 700), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="two-image-budget")

    assert result["coverage"]["embedded_images_screened"] == 2
    assert result["coverage"]["advanced_images_screened"] == 1
    assert result["coverage"]["image_regions_compared"] == 50_000
    assert result["coverage"]["image_region_budget_exhausted"] == 1


def test_repeated_image_xref_is_decoded_once_per_review_stage_and_reports_task_resources():
    review = deep_review_module()
    image = Image.new("L", (320, 200), "white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    for _ in range(4):
        page = pdf.new_page()
        page.insert_image(fitz.Rect(72, 72, 520, 324), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="repeated-xref")

    assert result["coverage"]["embedded_images_screened"] == 4
    assert result["coverage"]["advanced_images_screened"] == 1
    assert result["coverage"]["image_task_decoded_pixels"] == 320 * 200 * 2
    assert result["coverage"]["image_task_decoded_pixel_budget"] == 40_000_000
    assert result["coverage"]["image_tiles_generated"] <= 2_500
    assert result["coverage"]["image_task_tile_budget"] == 25_000


def test_image_review_stops_before_task_decoded_pixel_budget(monkeypatch):
    review = deep_review_module()
    monkeypatch.setattr(review, "MAX_TASK_IMAGE_DECODED_PIXELS", 100_000)
    image = Image.new("L", (320, 200), "white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_image(fitz.Rect(72, 72, 520, 324), stream=image_bytes.getvalue())
    data = pdf.tobytes()
    pdf.close()

    result = review.analyze_pdf(data, document_id="decoded-pixel-budget")

    assert result["coverage"]["embedded_images_screened"] == 1
    assert result["coverage"]["advanced_images_screened"] == 0
    assert result["coverage"]["advanced_images_skipped_resource_limit"] == 1
    assert result["coverage"]["image_task_decoded_pixels"] == 320 * 200
    assert result["coverage"]["image_resource_budget_exhausted"] == 1


def test_pdf_report_includes_advanced_coverage_calculations_and_decision_summary():
    review = deep_review_module()
    analysis = review.analyze_pdf(make_audit_pdf(), document_id="source-paper")
    analysis["title"] = "Advanced review sample"
    analysis["coverage"].update({
        "semantic_candidate_comparisons": 12,
        "semantic_similarity_candidates": 2,
        "citation_contexts_detected": 5,
        "citation_contexts_with_full_text": 3,
        "citation_support_matches": 2,
        "citation_support_unresolved": 3,
        "citation_candidate_comparisons": 50_000,
        "citation_candidate_budget": 50_000,
        "citation_candidate_budget_exhausted": 1,
        "semantic_candidate_budget": 50_000,
        "statistical_threshold_claims_examined": 8,
        "statistical_threshold_claim_budget": 1_000,
        "statistical_average_claims_examined": 4,
        "statistical_average_claim_budget": 500,
        "statistical_value_list_comparisons": 12,
        "statistical_value_list_comparison_budget": 5_000,
        "embedded_images_skipped_resource_limit": 1,
        "advanced_images_skipped_resource_limit": 1,
        "image_tile_sampling_adjusted": 2,
        "image_regions_compared": 50_000,
        "image_region_comparison_budget": 50_000,
        "image_region_budget_exhausted": 1,
        "image_region_reuse_candidates": 0,
    })
    analysis["statistical_checks"] = [{
        "kind": "threshold_with_uncertainty", "page": 1,
        "calculation": "0.35 + 0.05 = 0.4 < 0.5", "consistent": True,
        "conclusion": "阈值关系在所报告不确定度范围内成立。",
    }]
    analysis["decisions"] = [
        {"evidence_code": item["code"], "decision": "reasonable", "reason": "已核对。"}
        for item in analysis["evidence"]
    ]

    report_bytes = review.render_pdf_report(analysis)

    with fitz.open(stream=report_bytes, filetype="pdf") as report:
        report_text = "\n".join(page.get_text() for page in report)
    assert "语义近似候选" in report_text
    assert "引用论断支持核对" in report_text
    assert "比较 50000 / 50000（已达任务上限）" in report_text
    assert "统计复算" in report_text
    assert "0.35 + 0.05 = 0.4 < 0.5" in report_text
    assert "图片局部区域比较" in report_text
    assert "50000 / 50000 组；候选 0" in report_text
    assert "阈值 8 / 1000；均值 4 / 500；列表比较 12 / 5000" in report_text
    assert "资源限界跳过 1；稀疏采样 2 幅" in report_text
    assert "合理或可接受" in report_text
