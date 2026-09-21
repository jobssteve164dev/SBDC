import hashlib
import ipaddress
import re
import socket
import ssl
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import quote, urljoin, urlparse

import fitz
import httpx
import urllib3


INDEX_VERSION = "task-reference-index/1.0.0"
WORD = re.compile(r"[\w'-]+", re.UNICODE)
STOPWORDS = {
    "about", "after", "also", "been", "before", "between", "could", "from", "have", "into",
    "more", "other", "over", "paper", "results", "study", "than", "that", "their", "these",
    "this", "through", "under", "using", "were", "which", "with", "would",
}


def _metadata_candidate_matches(reference: dict[str, Any], candidate: dict[str, Any]) -> bool:
    candidate_title = _first(candidate.get("title")) or ""
    structured_title = reference.get("title") or ""
    expected = structured_title or reference.get("raw_citation") or ""
    title_words = {word for word in _words(candidate_title) if len(word) >= 3}
    expected_words = set(_words(expected))
    overlap = title_words & expected_words
    if len(title_words) < 3 or len(overlap) / len(title_words) < 0.8:
        return False
    if structured_title and len(overlap) / max(len(expected_words), 1) < 0.8:
        return False
    expected_year = str(reference.get("year") or "")
    date_parts = (candidate.get("published") or candidate.get("published-print") or {}).get("date-parts", [[]])
    candidate_year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
    year_matches = bool(expected_year and candidate_year and expected_year == candidate_year)
    if expected_year and candidate_year and not year_matches:
        return False
    expected_families = {name.split()[-1].lower() for name in reference.get("authors", []) if name.split()}
    candidate_families = {str(author.get("family", "")).lower() for author in candidate.get("author", []) if author.get("family")}
    author_matches = bool(expected_families and candidate_families and not expected_families.isdisjoint(candidate_families))
    if expected_families and candidate_families and not author_matches:
        return False
    return bool(structured_title or year_matches or author_matches)


def _doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
    return normalized.lower() or None


def _first(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value) if value else None


def resolve_open_access(reference: dict[str, Any], client: httpx.Client) -> dict[str, Any]:
    result = dict(reference)
    doi = _doi(reference.get("doi"))
    metadata: dict[str, Any] = {}
    try:
        if doi:
            response = client.get(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        else:
            response = client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": reference.get("raw_citation", ""), "rows": 1},
            )
        response.raise_for_status()
        payload = response.json().get("message", {})
        if not doi:
            items = payload.get("items", [])
            payload = items[0] if items else {}
            if not payload or float(payload.get("score", 0)) < 30 or not _metadata_candidate_matches(reference, payload):
                result["metadata_status"] = "ambiguous"
                result["full_text_status"] = "metadata_unavailable"
                return result
        metadata = payload
    except (httpx.HTTPError, ValueError, TypeError):
        result["metadata_status"] = "lookup_failed"
        result["full_text_status"] = "metadata_unavailable"
        return result

    doi = _doi(metadata.get("DOI")) or doi
    authors = [
        " ".join(part for part in (item.get("given"), item.get("family")) if part).strip()
        for item in metadata.get("author", [])
    ]
    date_parts = (metadata.get("published") or metadata.get("published-print") or {}).get("date-parts", [[]])
    year = str(date_parts[0][0]) if date_parts and date_parts[0] else reference.get("year")
    result.update({
        "doi": doi,
        "title": _first(metadata.get("title")) or reference.get("title"),
        "authors": [item for item in authors if item] or reference.get("authors", []),
        "year": year,
        "venue": _first(metadata.get("container-title")) or reference.get("venue"),
        "metadata_status": "resolved",
    })
    if not doi:
        result["full_text_status"] = "identifier_missing"
        return result
    try:
        response = client.get(f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='/')}")
        response.raise_for_status()
        work = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        result["full_text_status"] = "oa_lookup_failed"
        return result
    location = work.get("best_oa_location") or {}
    pdf_url = location.get("pdf_url") if (work.get("open_access") or {}).get("is_oa") else None
    if not pdf_url and (work.get("open_access") or {}).get("is_oa"):
        pdf_url = next(
            (item.get("pdf_url") for item in work.get("locations", []) if item.get("is_oa") and item.get("pdf_url")),
            None,
        )
    if pdf_url:
        result.update({"full_text_status": "available", "access_url": pdf_url})
    else:
        result["full_text_status"] = "not_open_access"
    return result


def _resolve_addresses(host: str) -> list[str]:
    return list({item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})


def _public_addresses(url: str, resolver: Callable[[str], list[str]]) -> tuple[Any, list[str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Open full text URL must use the public network")
    try:
        ipaddress.ip_address(parsed.hostname)
        addresses = [parsed.hostname]
    except ValueError:
        try:
            addresses = resolver(parsed.hostname)
        except OSError as error:
            raise ValueError("Open full text URL must resolve on the public network") from error
    if not addresses:
        raise ValueError("Open full text URL must resolve on the public network")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Open full text URL must use the public network")
    return parsed, sorted(addresses)


def _pinned_get(url: str, address: str) -> tuple[int, dict[str, str], Any]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = {"Host": parsed.hostname or "", "User-Agent": "SBDC/0.1 (open-access fetch)"}
    if parsed.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            address, port=port, retries=False, timeout=30,
            ssl_context=ssl.create_default_context(), assert_hostname=parsed.hostname,
            server_hostname=parsed.hostname,
        )
    else:
        pool = urllib3.HTTPConnectionPool(address, port=port, retries=False, timeout=30)
    response = pool.urlopen("GET", path, headers=headers, redirect=False, preload_content=False)
    return response.status, {key.lower(): value for key, value in response.headers.items()}, response


def download_open_pdf(
    url: str,
    client: httpx.Client | None = None,
    *,
    max_bytes: int = 52_428_800,
    max_pages: int = 500,
    resolver: Callable[[str], list[str]] = _resolve_addresses,
) -> bytes:
    current_url = url
    for redirect_count in range(6):
        _parsed, addresses = _public_addresses(current_url, resolver)
        if client is None:
            status, headers, raw_response = _pinned_get(current_url, addresses[0])
            chunks_iterator = raw_response.stream(64 * 1024)
            close_response = raw_response.release_conn
        else:
            response_context = client.stream("GET", current_url, follow_redirects=False)
            response = response_context.__enter__()
            status, headers = response.status_code, dict(response.headers)
            chunks_iterator = response.iter_bytes()
            close_response = lambda: response_context.__exit__(None, None, None)
        try:
            if status in {301, 302, 303, 307, 308}:
                location = headers.get("location")
                if not location or redirect_count == 5:
                    raise ValueError("Open full text redirect chain is invalid")
                current_url = urljoin(current_url, location)
                continue
            if status >= 400:
                raise ValueError(f"Open full text request failed with HTTP {status}")
            declared = headers.get("content-length")
            if declared and int(declared) > max_bytes:
                raise ValueError("Open PDF exceeds the configured size limit")
            chunks: list[bytes] = []
            size = 0
            for chunk in chunks_iterator:
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Open PDF exceeds the configured size limit")
                chunks.append(chunk)
            break
        finally:
            close_response()
    else:
        raise ValueError("Open full text redirect chain is invalid")
    data = b"".join(chunks)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Open full text did not return a valid PDF")
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass or not 1 <= pdf.page_count <= max_pages:
                raise ValueError
            _ = pdf[0].rect
    except Exception as error:
        raise ValueError("Open full text did not return a valid PDF") from error
    return data


def extract_pdf_blocks(pdf_bytes: bytes, document_id: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page_number, page in enumerate(pdf, start=1):
            for item in page.get_text("blocks"):
                text = re.sub(r"\s+", " ", item[4]).strip()
                if text:
                    blocks.append({
                        "document_id": document_id,
                        "page": page_number,
                        "bbox": [round(float(value), 2) for value in item[:4]],
                        "text": text,
                    })
    return blocks


def pdf_page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        return pdf.page_count


def build_reference_index(task_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    inverted: dict[str, list[list[int]]] = defaultdict(list)
    normalized_documents = []
    for document_index, document in enumerate(documents):
        blocks = document["blocks"]
        normalized_documents.append({
            "reference_id": document["reference_id"],
            "asset_id": document["asset_id"],
            "title": document.get("title"),
            "doi": document.get("doi"),
            "sha256": document.get("sha256"),
            "blocks": blocks,
        })
        for block_index, block in enumerate(blocks):
            for token in set(WORD.findall(block["text"].lower())):
                if len(token) >= 4:
                    inverted[token].append([document_index, block_index])
    return {
        "version": INDEX_VERSION,
        "task_id": task_id,
        "documents": normalized_documents,
        "inverted": dict(inverted),
        "digest": hashlib.sha256(
            "|".join(document["asset_id"] for document in normalized_documents).encode()
        ).hexdigest(),
    }


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _matched_excerpt(text: str, start_word: int, word_count: int) -> str:
    matches = list(WORD.finditer(text))
    first = matches[start_word]
    last = matches[start_word + word_count - 1]
    return text[first.start():last.end()]


def compare_reference_corpus(
    subject_blocks: list[dict[str, Any]], index: dict[str, Any], *, minimum_words: int = 10,
    max_candidate_comparisons: int = 50_000, metrics: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    comparisons = 0
    total_blocks = sum(len(document["blocks"]) for document in index["documents"])
    maximum_postings = max(20, total_blocks // 10)
    if metrics is not None:
        metrics.update({
            "candidate_comparisons": 0,
            "candidate_budget": max_candidate_comparisons,
            "candidate_budget_exhausted": 0,
        })
    for subject in subject_blocks:
        subject_words = _words(subject["text"])
        if len(subject_words) < minimum_words:
            continue
        candidates: set[tuple[int, int]] = set()
        anchors = sorted(
            (
                token for token in set(subject_words)
                if len(token) >= 5 and token not in STOPWORDS
                and 0 < len(index["inverted"].get(token, [])) <= maximum_postings
            ),
            key=lambda token: (len(index["inverted"].get(token, [])), token),
        )[:12]
        for token in anchors:
            for location in index["inverted"].get(token, []):
                candidates.add((location[0], location[1]))
        for document_index, block_index in sorted(candidates):
            if comparisons >= max_candidate_comparisons:
                if metrics is not None:
                    metrics["candidate_budget_exhausted"] = 1
                return _sorted_evidence(evidence)
            comparisons += 1
            if metrics is not None:
                metrics["candidate_comparisons"] = comparisons
            document = index["documents"][document_index]
            source = document["blocks"][block_index]
            source_words = _words(source["text"])
            matches = SequenceMatcher(None, subject_words, source_words, autojunk=False).get_matching_blocks()
            for match in matches:
                if match.size < minimum_words:
                    continue
                key = (
                    document["asset_id"], subject["page"], tuple(subject.get("bbox") or []),
                    source["page"], tuple(source.get("bbox") or []), match.a, match.b, match.size,
                )
                if key in seen:
                    continue
                seen.add(key)
                subject_excerpt = _matched_excerpt(subject["text"], match.a, match.size)
                source_excerpt = _matched_excerpt(source["text"], match.b, match.size)
                confidence = min(0.99, 0.6 + match.size / max(len(subject_words), len(source_words)) * 0.4)
                subject_location = {key: subject.get(key) for key in ("document_id", "page", "bbox")}
                subject_location.update({"word_start": match.a, "word_end": match.a + match.size})
                source_location = {key: source.get(key) for key in ("document_id", "page", "bbox")}
                source_location.update({"word_start": match.b, "word_end": match.b + match.size})
                evidence.append({
                "code": "reference_text_reuse_candidate",
                "category": "text_reuse",
                "status": "needs_review",
                "severity": "medium" if match.size < 30 else "high",
                "confidence": round(confidence, 3),
                "subject_location": subject_location,
                "source_location": source_location,
                "subject_excerpt": subject_excerpt,
                "source_excerpt": source_excerpt,
                "explanation": "待检论文与一篇已合法取得的引用全文存在连续文本重合，需要结合引文位置和学科惯例人工复核。",
                "method": {
                    "detector": "reference-text-alignment", "version": INDEX_VERSION,
                    "parameters": {"minimum_words": minimum_words},
                    "source": {key: document.get(key) for key in ("reference_id", "title", "doi", "sha256")},
                },
                "limitations": ["文本相似不等于抄袭；直接引语、正确引用和通用方法描述需要人工排除。"],
                "artifacts": [document["asset_id"]],
                })
    return _sorted_evidence(evidence)


def _sorted_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(evidence, key=lambda item: (
        item["subject_location"].get("page") or 0,
        item["subject_location"].get("word_start") or 0,
        item["source_location"].get("document_id") or "",
        item["source_location"].get("word_start") or 0,
    ))
