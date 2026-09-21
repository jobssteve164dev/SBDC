import fitz
import httpx
import pytest
import sbdc_worker.reference_pipeline as reference_pipeline


from sbdc_worker.reference_pipeline import (
    build_reference_index,
    compare_reference_corpus,
    download_open_pdf,
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
