import fitz
import httpx
import pytest
import sbdc_worker.reference_pipeline as reference_pipeline


from sbdc_worker.reference_pipeline import (
    build_reference_index,
    compare_reference_corpus,
    compare_semantic_reference_corpus,
    download_open_pdf,
    evaluate_citation_support,
    extract_pdf_blocks,
    resolve_open_access,
)


def make_pdf(text: str) -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 520, 720), text, fontsize=11)
    data = pdf.tobytes()
    pdf.close()
    return data


def public_resolver(_host: str) -> list[str]:
    return ["8.8.8.8"]


def test_resolve_open_access_normalizes_metadata_and_uses_an_explicit_open_pdf():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {
                "DOI": "10.1000/Example", "title": ["Reliable Source"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "published": {"date-parts": [[2024]]}, "container-title": ["Evidence Journal"],
            }})
        return httpx.Response(200, json={
            "open_access": {"is_oa": True},
            "best_oa_location": {"pdf_url": "https://repository.example/paper.pdf", "landing_page_url": "https://repository.example/item"},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = resolve_open_access({"doi": "https://doi.org/10.1000/Example", "raw_citation": "fallback"}, client)

    assert result["doi"] == "10.1000/example"
    assert result["title"] == "Reliable Source"
    assert result["authors"] == ["Ada Lovelace"]
    assert result["year"] == "2024"
    assert result["venue"] == "Evidence Journal"
    assert result["metadata_status"] == "resolved"
    assert result["full_text_status"] == "available"
    assert result["access_url"] == "https://repository.example/paper.pdf"


def test_resolve_open_access_uses_an_open_location_when_best_location_has_no_pdf():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"DOI": "10.1000/example", "title": ["Source"]}})
        return httpx.Response(200, json={
            "open_access": {"is_oa": True}, "best_oa_location": {"pdf_url": None},
            "locations": [{"is_oa": True, "pdf_url": "https://repository.example/copy.pdf"}],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = resolve_open_access({"doi": "10.1000/example", "raw_citation": "Source"}, client)

    assert result["access_url"] == "https://repository.example/copy.pdf"


def test_resolve_open_access_rejects_a_high_score_title_search_result_when_title_does_not_match():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"
        return httpx.Response(200, json={"message": {"items": [{
            "DOI": "10.1000/unrelated", "title": ["An unrelated research topic"], "score": 91.0,
        }]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = resolve_open_access({"doi": None, "raw_citation": "Reliable nanowire photon emission study"}, client)

    assert result["metadata_status"] == "ambiguous"
    assert result["full_text_status"] == "metadata_unavailable"
    assert result.get("doi") is None


def test_resolve_open_access_rejects_a_generic_title_without_author_or_year_confirmation():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"
        return httpx.Response(200, json={"message": {"items": [{
            "DOI": "10.1000/generic", "title": ["Photon emission study"], "score": 95.0,
        }]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = resolve_open_access({
            "doi": None,
            "raw_citation": "A long citation about reliable nanowire photon emission study in advanced materials",
            "title": None, "authors": [], "year": None,
        }, client)

    assert result["metadata_status"] == "ambiguous"
    assert result.get("doi") is None


def test_download_open_pdf_rejects_html_even_when_server_labels_it_pdf():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"<html>paywall</html>")
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError, match="valid PDF"):
            download_open_pdf("https://repository.example/paper.pdf", client, resolver=public_resolver)


def test_task_index_and_text_evidence_preserve_both_pdf_locations():
    subject = make_pdf("Nanowires were grown on silicon substrate under nitrogen rich conditions for the optical experiment.")
    source = make_pdf("The nanowires were grown on silicon substrate under nitrogen rich conditions for the optical experiment.")
    subject_blocks = extract_pdf_blocks(subject, "source-paper")
    source_blocks = extract_pdf_blocks(source, "reference-asset")

    index = build_reference_index("task-123", [{
        "reference_id": "ref-1", "asset_id": "reference-asset", "blocks": source_blocks,
        "title": "Reliable Source", "doi": "10.1000/source", "sha256": "abc123",
    }])
    evidence = compare_reference_corpus(subject_blocks, index, minimum_words=8)

    assert index["task_id"] == "task-123"
    assert index["documents"][0]["asset_id"] == "reference-asset"
    assert evidence
    assert evidence[0]["code"] == "reference_text_reuse_candidate"
    assert evidence[0]["subject_location"]["document_id"] == "source-paper"
    assert evidence[0]["subject_location"]["page"] == 1
    assert evidence[0]["source_location"]["document_id"] == "reference-asset"
    assert evidence[0]["source_location"]["page"] == 1
    assert "Nanowires were grown" in evidence[0]["subject_excerpt"]
    assert evidence[0]["method"]["source"]["title"] == "Reliable Source"
    assert evidence[0]["method"]["source"]["doi"] == "10.1000/source"
    assert evidence[0]["method"]["source"]["sha256"] == "abc123"
    assert "抄袭" not in evidence[0]["explanation"]


def test_text_evidence_keeps_distinct_matches_on_the_same_page_pair():
    first = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    second = "north south east west spring summer autumn winter red green blue gold"
    subject = [{"document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4], "text": f"{first} unrelated bridge {second}"}]
    source = [{"document_id": "source", "page": 1, "bbox": [5, 6, 7, 8], "text": f"{first} different material {second}"}]
    index = build_reference_index("task", [{"reference_id": "ref", "asset_id": "source", "blocks": source}])

    evidence = compare_reference_corpus(subject, index, minimum_words=10)

    assert len(evidence) == 2
    assert [item["subject_location"]["word_start"] for item in evidence] == [0, 14]


def test_text_evidence_stops_at_an_auditable_candidate_comparison_budget():
    phrase = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    subject = [{"document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4], "text": phrase}]
    source_blocks = [
        {"document_id": "source", "page": page, "bbox": [5, 6, 7, 8], "text": phrase}
        for page in range(1, 4)
    ]
    index = build_reference_index("task", [{"reference_id": "ref", "asset_id": "source", "blocks": source_blocks}])
    metrics: dict[str, int] = {}

    evidence = compare_reference_corpus(
        subject, index, minimum_words=10, max_candidate_comparisons=1, metrics=metrics
    )

    assert len(evidence) == 1
    assert metrics == {"candidate_comparisons": 1, "candidate_budget": 1, "candidate_budget_exhausted": 1}


def test_download_open_pdf_rejects_private_network_targets_before_request():
    with httpx.Client(transport=httpx.MockTransport(lambda _request: pytest.fail("request must not be sent"))) as client:
        with pytest.raises(ValueError, match="public network"):
            download_open_pdf("http://127.0.0.1/private.pdf", client)


def test_download_open_pdf_validates_redirect_targets_before_following_them():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private.pdf"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="public network"):
            download_open_pdf("https://repository.example/paper.pdf", client, resolver=public_resolver)

    assert requested == ["https://repository.example/paper.pdf"]


def test_download_open_pdf_pins_the_verified_address_in_production(monkeypatch):
    pdf = make_pdf("Verified public source")
    calls: list[tuple[str, str]] = []

    class Response:
        def stream(self, _size: int):
            yield pdf

        def release_conn(self):
            return None

    def pinned_get(url: str, address: str):
        calls.append((url, address))
        return 200, {"content-length": str(len(pdf))}, Response()

    monkeypatch.setattr(reference_pipeline, "_pinned_get", pinned_get)

    result = download_open_pdf(
        "https://repository.example/paper.pdf", resolver=lambda _host: ["8.8.8.8"]
    )

    assert result == pdf
    assert calls == [("https://repository.example/paper.pdf", "8.8.8.8")]


def test_semantic_comparison_surfaces_reworded_source_passages_without_calling_them_misconduct():
    subject = [{
        "document_id": "subject", "page": 2, "bbox": [1, 2, 3, 4],
        "text": "A randomized clinical trial found the intervention reduced systolic blood pressure in adults.",
    }]
    source = [{
        "document_id": "source", "page": 7, "bbox": [5, 6, 7, 8],
        "text": "Adults in the randomized clinical trial showed reduced systolic blood pressure after receiving the intervention.",
    }]
    index = build_reference_index("task", [{
        "reference_id": "ref-7", "ordinal": 7, "asset_id": "source", "blocks": source,
        "title": "Clinical trial source", "doi": "10.1000/semantic", "sha256": "def456",
    }])

    result = compare_semantic_reference_corpus(subject, index, minimum_score=0.52)

    assert len(result["evidence"]) == 1
    item = result["evidence"][0]
    assert item["code"] == "reference_semantic_similarity_candidate"
    assert item["source_location"]["page"] == 7
    assert item["method"]["source"]["ordinal"] == 7
    assert item["method"]["parameters"]["score"] >= 0.52
    assert "不等于不当复用" in item["limitations"][0]
    assert result["coverage"]["semantic_candidate_comparisons"] == 1


def test_semantic_comparison_caps_repetitive_domain_candidates_per_source():
    subject = [
        {"document_id": "subject", "page": page, "bbox": [1, 2, 3, 4], "text": "A randomized clinical trial found the intervention reduced systolic blood pressure in adults."}
        for page in range(1, 9)
    ]
    source = [
        {"document_id": "source", "page": page, "bbox": [5, 6, 7, 8], "text": "Adults in the randomized clinical trial showed reduced systolic blood pressure after receiving the intervention."}
        for page in range(1, 9)
    ]
    index = build_reference_index("task", [{"reference_id": "ref", "ordinal": 1, "asset_id": "source", "blocks": source}])

    result = compare_semantic_reference_corpus(subject, index, minimum_score=0.52)

    assert len(result["evidence"]) == 3
    assert result["coverage"]["semantic_similarity_candidates"] == 3


def test_citation_support_recomputes_numeric_alignment_against_the_cited_source():
    subject = [{
        "document_id": "subject", "page": 3, "bbox": [1, 2, 3, 4],
        "text": "The prior device operated up to 280 K with a measured purity of 0.35 [29].",
    }]
    source = [{
        "document_id": "source", "page": 4, "bbox": [5, 6, 7, 8],
        "text": "The device retained single photon operation at 280 K and the measured purity was 0.24.",
    }]
    index = build_reference_index("task", [{
        "reference_id": "ref-29", "ordinal": 29, "asset_id": "source", "blocks": source,
        "title": "Cited experiment", "doi": "10.1000/cited", "sha256": "abc789",
    }])

    result = evaluate_citation_support(subject, index, minimum_score=0.35)

    assert result["coverage"] == {
        "citation_contexts_detected": 1,
        "citation_contexts_with_full_text": 1,
        "citation_support_matches": 0,
        "citation_support_unresolved": 0,
        "citation_numeric_mismatches": 1,
        "citation_direction_conflicts": 0,
        "citation_candidate_comparisons": 1,
        "citation_candidate_budget": 50_000,
        "citation_candidate_budget_exhausted": 0,
    }
    item = result["evidence"][0]
    assert item["code"] == "citation_numeric_mismatch_candidate"
    assert item["subject_location"]["page"] == 3
    assert item["source_location"]["page"] == 4
    assert item["method"]["source"]["ordinal"] == 29
    assert item["method"]["subject_numbers"] == ["0.35", "280"]
    assert item["method"]["source_numbers"] == ["0.24", "280"]


def test_citation_support_records_supported_and_unresolved_contexts_without_false_anomalies():
    subject = [
        {"document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4], "text": "Operation reached 280 K [29]."},
        {"document_id": "subject", "page": 2, "bbox": [1, 2, 3, 4], "text": "A separate historical claim [30]."},
    ]
    source = [{
        "document_id": "source", "page": 4, "bbox": [5, 6, 7, 8],
        "text": "The emitter continued to operate at a temperature of 280 K.",
    }]
    index = build_reference_index("task", [{
        "reference_id": "ref-29", "ordinal": 29, "asset_id": "source", "blocks": source,
    }])

    result = evaluate_citation_support(subject, index, minimum_score=0.2)

    assert result["evidence"] == []
    assert result["coverage"]["citation_contexts_detected"] == 2
    assert result["coverage"]["citation_contexts_with_full_text"] == 1
    assert result["coverage"]["citation_support_matches"] == 1
    assert result["coverage"]["citation_support_unresolved"] == 1


def test_citation_support_ignores_bibliography_entries_that_begin_with_a_marker():
    subject = [{
        "document_id": "subject", "page": 7, "bbox": [1, 2, 3, 4],
        "text": "[29] X. Sun, P. Wang, Appl. Phys. Lett. 2019, 115, 022101.",
    }]
    index = build_reference_index("task", [])

    result = evaluate_citation_support(subject, index)

    assert result["coverage"]["citation_contexts_detected"] == 0
    assert result["coverage"]["citation_support_unresolved"] == 0


def test_citation_support_only_compares_the_sentence_attached_to_the_marker():
    subject = [{
        "document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4],
        "text": "Earlier devices reached 200 K with purity 0.24 [28]. This source reports operation up to 280 K [29]. Later work reached 300 K [30].",
    }]
    source = [{
        "document_id": "source", "page": 2, "bbox": [5, 6, 7, 8],
        "text": "The single photon device continued to operate at a temperature of 280 K.",
    }]
    index = build_reference_index("task", [{"reference_id": "ref-29", "ordinal": 29, "asset_id": "source", "blocks": source}])

    result = evaluate_citation_support(subject, index, minimum_score=0.2)

    assert result["evidence"] == []
    assert result["coverage"]["citation_contexts_with_full_text"] == 1
    assert result["coverage"]["citation_support_matches"] == 1


def test_citation_support_counts_one_claim_context_for_a_reference_range():
    subject = [{
        "document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4],
        "text": "Prior emitters operated at elevated temperatures [29–34].",
    }]
    index = build_reference_index("task", [])

    result = evaluate_citation_support(subject, index)

    assert result["coverage"]["citation_contexts_detected"] == 1
    assert result["coverage"]["citation_support_unresolved"] == 1


def test_citation_support_combines_numbers_from_all_sources_in_a_multi_reference_claim():
    subject = [{
        "document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4],
        "text": "Prior devices operated at temperatures of 280 K and 300 K [29,30].",
    }]
    documents = []
    for ordinal, temperature in ((29, 280), (30, 300)):
        documents.append({
            "reference_id": f"ref-{ordinal}", "ordinal": ordinal, "asset_id": f"source-{ordinal}",
            "blocks": [{
                "document_id": f"source-{ordinal}", "page": 2, "bbox": [5, 6, 7, 8],
                "text": f"The prior device operated at a temperature of {temperature} K.",
            }],
        })
    result = evaluate_citation_support(subject, build_reference_index("task", documents), minimum_score=0.2)

    assert result["evidence"] == []
    assert result["coverage"]["citation_support_matches"] == 1
    assert result["coverage"]["citation_numeric_mismatches"] == 0


def test_citation_support_reports_when_its_comparison_budget_truncates_contexts():
    subject = [{
        "document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4],
        "text": "The device operated at 280 K [29].",
    }]
    source = [
        {"document_id": "source", "page": 2, "bbox": [5, 6, 7, 8], "text": "Unrelated source material."},
        {"document_id": "source", "page": 3, "bbox": [5, 6, 7, 8], "text": "The device operated at 280 K."},
    ]
    index = build_reference_index("task", [{"reference_id": "ref-29", "ordinal": 29, "asset_id": "source", "blocks": source}])

    result = evaluate_citation_support(subject, index, minimum_score=0.2, max_candidate_comparisons=1)

    assert result["coverage"]["citation_candidate_comparisons"] == 1
    assert result["coverage"]["citation_candidate_budget"] == 1
    assert result["coverage"]["citation_candidate_budget_exhausted"] == 1
    assert result["coverage"]["citation_support_unresolved"] == 1


def test_citation_support_does_not_call_opposite_direction_claims_a_match():
    subject = [{
        "document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4],
        "text": "Treatment X increased mortality in adults [1].",
    }]
    source = [{
        "document_id": "source", "page": 2, "bbox": [5, 6, 7, 8],
        "text": "Treatment X decreased mortality in adults.",
    }]
    index = build_reference_index("task", [{"reference_id": "ref-1", "ordinal": 1, "asset_id": "source", "blocks": source}])

    result = evaluate_citation_support(subject, index, minimum_score=0.2)

    assert result["coverage"]["citation_support_matches"] == 0
    assert result["coverage"]["citation_direction_conflicts"] == 1
    assert result["evidence"][0]["code"] == "citation_direction_conflict_candidate"


def test_citation_direction_check_leaves_multi_predicate_and_negated_claims_unresolved():
    cases = [
        (
            "Treatment X increased survival and decreased mortality in adults [1].",
            "Treatment X increased survival and decreased mortality in adults.",
        ),
        ("Treatment X did not increase mortality in adults [1].", "Treatment X increased mortality in adults."),
    ]
    for subject_text, source_text in cases:
        index = build_reference_index("task", [{
            "reference_id": "ref-1", "ordinal": 1, "asset_id": "source",
            "blocks": [{"document_id": "source", "page": 2, "bbox": [5, 6, 7, 8], "text": source_text}],
        }])
        result = evaluate_citation_support(
            [{"document_id": "subject", "page": 1, "bbox": [1, 2, 3, 4], "text": subject_text}],
            index,
            minimum_score=0.2,
        )

        assert result["evidence"] == []
        assert result["coverage"]["citation_support_matches"] == 0
        assert result["coverage"]["citation_direction_conflicts"] == 0
        assert result["coverage"]["citation_support_unresolved"] == 1
