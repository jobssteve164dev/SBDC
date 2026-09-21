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

    report_bytes = review.render_pdf_report(analysis)

    assert report_bytes.startswith(b"%PDF-")
    with fitz.open(stream=report_bytes, filetype="pdf") as report:
        assert report.page_count >= 2
        assert report.metadata["title"].startswith("SBDC 深度审核报告")
        report_text = "\n".join(page.get_text() for page in report)
        assert "对照位置" in report_text
        assert "不同条件得到相同数值可能合理" in report_text
