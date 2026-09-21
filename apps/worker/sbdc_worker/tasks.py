import hashlib
import json
import logging
import uuid
from urllib.parse import urlsplit, urlunsplit

import httpx
import urllib3
from sqlalchemy import delete, select

from sbdc_api.config import get_settings
from sbdc_api.database import SessionLocal
from sbdc_api.models import (
    AuditEvent, DocumentAsset, EvidenceRecord, PaperTask, ParsedDocument, ParseRun,
    ReferenceSource, ReviewRun,
)
from sbdc_api.storage import get_bytes, put_bytes, reference_index_storage_key, reference_storage_key
from sbdc_domain import CoverageSummary, TaskStatus

from .celery_app import app
from .tei import parse_tei
from .deep_review import METHOD_VERSION, analyze_pdf
from .reference_pipeline import (
    build_reference_index, compare_reference_corpus, download_open_pdf, extract_pdf_blocks, pdf_page_count,
    resolve_open_access,
)


settings = get_settings()
logger = logging.getLogger(__name__)


def _public_url_without_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _prepare_reference_corpus(db, task: PaperTask, source_asset: DocumentAsset) -> tuple[dict, list[dict], dict]:
    references = list(db.scalars(select(ReferenceSource).where(ReferenceSource.task_id == task.id)))
    documents: list[dict] = []
    total_bytes = 0
    total_pages = 0
    total_characters = 0
    obtained_count = 0
    skipped_budget = 0
    task.status = TaskStatus.FETCHING_SOURCES.value
    task.stage_message = "正在确认引用并获取合法开放全文"
    db.commit()
    with httpx.Client(
        timeout=settings.academic_api_timeout_seconds,
        headers={"User-Agent": "SBDC/0.1 (source-based research review)"},
    ) as client:
        for reference in references:
            try:
                if reference.full_text_asset_id:
                    existing_asset = db.get(DocumentAsset, reference.full_text_asset_id)
                    if existing_asset and existing_asset.retention_state == "active":
                        data = get_bytes(existing_asset.storage_key)
                        blocks = extract_pdf_blocks(data, str(existing_asset.id))
                        characters = sum(len(block["text"]) for block in blocks)
                        pages = existing_asset.page_count or pdf_page_count(data)
                        if (
                            obtained_count >= settings.max_reference_fulltexts
                            or total_bytes + len(data) > settings.max_reference_total_bytes
                            or total_pages + pages > settings.max_reference_total_pages
                            or total_characters + characters > settings.max_reference_total_characters
                        ):
                            skipped_budget += 1
                            continue
                        total_bytes += len(data)
                        total_pages += pages
                        obtained_count += 1
                        if blocks:
                            documents.append({
                                "reference_id": str(reference.id), "asset_id": str(existing_asset.id),
                                "title": reference.title, "doi": reference.doi, "sha256": existing_asset.sha256,
                                "blocks": blocks,
                            })
                            total_characters += characters
                        continue
                resolved = resolve_open_access(
                    {
                        "doi": reference.doi, "raw_citation": reference.raw_citation, "title": reference.title,
                        "authors": reference.authors, "year": reference.year, "venue": reference.venue,
                    },
                    client,
                )
                for field in ("doi", "title", "authors", "year", "venue", "metadata_status", "full_text_status"):
                    if field in resolved:
                        setattr(reference, field, resolved[field])
                url = resolved.get("access_url")
                if not url:
                    continue
                if obtained_count >= settings.max_reference_fulltexts:
                    reference.full_text_status = "budget_exceeded"
                    skipped_budget += 1
                    continue
                reference.access_url = _public_url_without_query(url)
                remaining_bytes = settings.max_reference_total_bytes - total_bytes
                remaining_pages = settings.max_reference_total_pages - total_pages
                if remaining_bytes <= 0 or remaining_pages <= 0:
                    reference.full_text_status = "budget_exceeded"
                    skipped_budget += 1
                    continue
                data = download_open_pdf(
                    url, max_bytes=min(settings.max_pdf_bytes, remaining_bytes),
                    max_pages=min(settings.max_pdf_pages, remaining_pages),
                )
                asset_id = uuid.uuid4()
                key = reference_storage_key(str(task.id), str(asset_id))
                blocks = extract_pdf_blocks(data, str(asset_id))
                characters = sum(len(block["text"]) for block in blocks)
                pages = pdf_page_count(data)
                if total_characters + characters > settings.max_reference_total_characters:
                    reference.full_text_status = "budget_exceeded"
                    skipped_budget += 1
                    continue
                asset = DocumentAsset(
                    id=asset_id, task_id=task.id, role="reference_full_text", storage_key=key,
                    sha256=hashlib.sha256(data).hexdigest(), media_type="application/pdf", size_bytes=len(data),
                    page_count=pages, license_status="open_access", retention_state="pending",
                    provenance={"source": "openalex_open_location", "reference_id": str(reference.id), "access_url": reference.access_url},
                )
                db.add(asset)
                db.commit()
                try:
                    put_bytes(key, data, "application/pdf")
                except Exception:
                    asset.retention_state = "purge_failed"
                    db.commit()
                    raise
                asset.retention_state = "active"
                reference.full_text_asset_id = asset.id
                reference.full_text_status = "obtained" if blocks else "obtained_no_text"
                total_bytes += len(data)
                total_pages += pages
                obtained_count += 1
                if blocks:
                    documents.append({
                        "reference_id": str(reference.id), "asset_id": str(asset.id), "title": reference.title,
                        "doi": reference.doi, "sha256": asset.sha256, "blocks": blocks,
                    })
                    total_characters += characters
                db.add(AuditEvent(
                    task_id=task.id, event_type="reference.full_text_obtained",
                    details={"reference_id": str(reference.id), "asset_id": str(asset.id), "sha256": asset.sha256},
                ))
                db.commit()
            except (httpx.HTTPError, urllib3.exceptions.HTTPError, ValueError, OSError):
                reference.full_text_status = "download_failed"
                reference.failure_reason = "open_full_text_unavailable_or_invalid"
    db.commit()

    task.status = TaskStatus.INDEXING.value
    task.stage_message = "正在建立本任务的引用对照索引"
    db.commit()
    index = build_reference_index(str(task.id), documents)
    index_bytes = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode()
    while documents and len(index_bytes) > settings.max_reference_index_bytes:
        documents.pop()
        skipped_budget += 1
        index = build_reference_index(str(task.id), documents)
        index_bytes = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode()
    if len(index_bytes) > settings.max_reference_index_bytes:
        raise ValueError("Reference index exceeds the configured task budget")
    index_asset = DocumentAsset(
        id=uuid.uuid4(), task_id=task.id, role="reference_index", storage_key="pending",
        sha256=hashlib.sha256(index_bytes).hexdigest(), media_type="application/json", size_bytes=len(index_bytes),
        license_status="derived_private", retention_state="pending", provenance={"version": index["version"]},
    )
    index_asset.storage_key = reference_index_storage_key(str(task.id), str(index_asset.id))
    db.add(index_asset)
    db.commit()
    try:
        put_bytes(index_asset.storage_key, index_bytes, "application/json")
    except Exception:
        index_asset.retention_state = "purge_failed"
        db.commit()
        raise
    index_asset.retention_state = "active"
    db.add(AuditEvent(
        task_id=task.id, event_type="reference.indexed",
        details={"documents": len(documents), "index_sha256": index_asset.sha256},
    ))
    task.status = TaskStatus.CHECKING.value
    task.stage_message = "正在对照待检论文与引用全文"
    db.commit()
    return index, documents, {
        "reference_full_texts_compared": len(documents),
        "reference_full_texts_skipped_budget": skipped_budget,
        "reference_corpus_bytes": total_bytes,
        "reference_corpus_pages": total_pages,
        "reference_corpus_characters": total_characters,
        "reference_index_bytes": len(index_bytes),
    }


def grobid_parse(pdf_bytes: bytes) -> tuple[bytes, str | None]:
    multipart = [
        ("includeRawCitations", (None, "1")),
        ("segmentSentences", (None, "1")),
        ("teiCoordinates", (None, "ref")),
        ("teiCoordinates", (None, "biblStruct")),
        ("teiCoordinates", (None, "p")),
        ("teiCoordinates", (None, "figure")),
        ("teiCoordinates", (None, "formula")),
        ("input", ("paper.pdf", pdf_bytes, "application/pdf")),
    ]
    with httpx.Client(timeout=settings.request_timeout_seconds) as client:
        response = client.post(f"{settings.grobid_url}/api/processFulltextDocument", files=multipart)
        response.raise_for_status()
        version = None
        try:
            version_response = client.get(f"{settings.grobid_url}/api/version", timeout=10)
            if version_response.is_success:
                version = version_response.text.strip()[:80]
        except httpx.HTTPError:
            pass
    if not response.content.lstrip().startswith(b"<?xml") and b"<TEI" not in response.content[:500]:
        raise ValueError("GROBID did not return TEI XML")
    return response.content, version


@app.task(name="sbdc.parse_document")
def parse_document(task_id: str, run_id: str) -> dict[str, str]:
    parsed_task_id = uuid.UUID(task_id)
    parsed_run_id = uuid.UUID(run_id)
    db = SessionLocal()
    run = None
    try:
        task = db.scalar(select(PaperTask).where(PaperTask.id == parsed_task_id).with_for_update())
        run = db.get(ParseRun, parsed_run_id)
        if task is None or run is None or run.task_id != parsed_task_id:
            return {"status": "ignored", "reason": "task_or_run_missing"}
        asset = db.get(DocumentAsset, task.source_file_id)
        if asset is None or asset.task_id != task.id or asset.sha256 != run.source_sha256:
            run.status = "ignored"
            db.commit()
            return {"status": "ignored", "reason": "source_changed"}
        existing = db.scalar(
            select(ParsedDocument).where(
                ParsedDocument.task_id == task.id,
                ParsedDocument.source_sha256 == asset.sha256,
            )
        )
        if existing is not None:
            task.status = TaskStatus.REFERENCES_READY.value
            task.stage_message = "论文解析完成"
            run.status = "succeeded"
            db.commit()
            return {"status": "already_complete"}
        run.status = "running"
        db.commit()

        pdf_bytes = get_bytes(asset.storage_key)
        tei, parser_version = grobid_parse(pdf_bytes)
        parsed = parse_tei(tei, pdf_bytes)
        tei_key = f"tasks/{task.id}/parsed/{asset.id}/fulltext.tei.xml"
        put_bytes(tei_key, tei, "application/xml")

        db.execute(delete(ReferenceSource).where(ReferenceSource.task_id == task.id))
        document = ParsedDocument(
            task_id=task.id,
            asset_id=asset.id,
            source_sha256=asset.sha256,
            title=parsed["title"],
            authors=parsed["authors"],
            abstract=parsed["abstract"],
            language=parsed["language"],
            sections=parsed["sections"],
            page_map=parsed["page_map"],
            tei_storage_key=tei_key,
            parser_version=parser_version,
        )
        db.add(document)
        for item in parsed["references"]:
            db.add(ReferenceSource(task_id=task.id, **item))

        parsed_count = sum(1 for item in parsed["references"] if item["parse_status"] == "parsed")
        failed_count = len(parsed["references"]) - parsed_count
        reasons = {"bibliographic_fields_missing": failed_count} if failed_count else {}
        located_sections = sum(1 for section in parsed["sections"] if section["page"] is not None)
        task.coverage_summary = CoverageSummary(
            references_total=len(parsed["references"]),
            references_parsed=parsed_count,
            references_failed=failed_count,
            failure_reasons=reasons,
            body_sections=len(parsed["sections"]),
            located_sections=located_sections,
        ).model_dump()
        task.status = TaskStatus.REFERENCES_READY.value
        task.stage_message = "论文解析完成，可查看结构和引用"
        task.error_code = None
        task.error_message = None
        run.status = "succeeded"
        db.add(
            AuditEvent(
                task_id=task.id,
                event_type="parse.completed",
                details={
                    "parser": "grobid",
                    "sections": len(parsed["sections"]),
                    "references_total": len(parsed["references"]),
                    "references_parsed": parsed_count,
                },
            )
        )
        db.commit()
        return {"status": "completed"}
    except Exception as exc:
        db.rollback()
        logger.error(
            "document parsing failed",
            extra={"task_id": task_id, "error_type": type(exc).__name__},
        )
        task = db.get(PaperTask, parsed_task_id)
        run = db.get(ParseRun, parsed_run_id)
        if task is not None and run is not None:
            task.status = TaskStatus.PARSING_FAILED.value
            task.stage_message = "论文解析失败"
            task.error_code = "document_parse_failed"
            task.error_message = "解析服务未能识别这份 PDF，请确认文件可正常阅读后重试"
            run.status = "failed"
            db.add(AuditEvent(task_id=task.id, event_type="parse.failed", details={"reason": "document_parse_failed"}))
            db.commit()
        return {"status": "failed"}
    finally:
        db.close()


@app.task(name="sbdc.deep_review_document")
def deep_review_document(task_id: str, run_id: str) -> dict[str, str]:
    parsed_task_id = uuid.UUID(task_id)
    parsed_run_id = uuid.UUID(run_id)
    db = SessionLocal()
    try:
        task = db.scalar(select(PaperTask).where(PaperTask.id == parsed_task_id).with_for_update())
        run = db.get(ReviewRun, parsed_run_id)
        if task is None or run is None or run.task_id != parsed_task_id:
            return {"status": "ignored", "reason": "task_or_run_missing"}
        asset = db.get(DocumentAsset, task.source_file_id)
        if asset is None or asset.task_id != task.id or asset.sha256 != run.source_sha256:
            run.status = "ignored"
            db.commit()
            return {"status": "ignored", "reason": "source_changed"}
        run.status = "running"
        db.commit()

        source_bytes = get_bytes(asset.storage_key)
        index, reference_documents, corpus_coverage = _prepare_reference_corpus(db, task, asset)
        analysis = analyze_pdf(source_bytes, document_id=str(asset.id))
        comparison_metrics: dict[str, int] = {}
        analysis["evidence"].extend(compare_reference_corpus(
            extract_pdf_blocks(source_bytes, str(asset.id)), index,
            max_candidate_comparisons=settings.max_reference_candidate_comparisons,
            metrics=comparison_metrics,
        ))
        document = db.scalar(select(ParsedDocument).where(ParsedDocument.task_id == task.id))
        references = list(db.scalars(select(ReferenceSource).where(ReferenceSource.task_id == task.id)))
        analysis["title"] = document.title if document and document.title else analysis.get("title")
        analysis["coverage"]["references_total"] = len(references)
        analysis["coverage"]["reference_full_texts_obtained"] = sum(
            1 for reference in references if reference.full_text_status in {"obtained", "obtained_no_text"}
        )
        analysis["coverage"]["references_metadata_resolved"] = sum(
            1 for reference in references if reference.metadata_status == "resolved"
        )
        analysis["coverage"]["reference_full_texts_indexed"] = len(reference_documents)
        analysis["coverage"].update(corpus_coverage)
        analysis["coverage"].update({
            "reference_candidate_comparisons": comparison_metrics["candidate_comparisons"],
            "reference_candidate_budget": comparison_metrics["candidate_budget"],
            "reference_candidate_budget_exhausted": comparison_metrics["candidate_budget_exhausted"],
        })
        analysis["coverage"]["reference_full_text_failure_reasons"] = {
            status: sum(1 for reference in references if reference.full_text_status == status)
            for status in sorted({
                reference.full_text_status for reference in references
                if reference.full_text_status not in {"obtained"}
            })
        }
        evidence_version = f"{asset.sha256}:{METHOD_VERSION}:{index['digest'][:16]}"
        for item in analysis["evidence"]:
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "code": item["code"],
                        "subject_location": item["subject_location"],
                        "source_location": item["source_location"],
                        "subject_excerpt": item["subject_excerpt"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            existing = db.scalar(
                select(EvidenceRecord).where(
                    EvidenceRecord.task_id == task.id,
                    EvidenceRecord.fingerprint == fingerprint,
                    EvidenceRecord.evidence_version == evidence_version,
                )
            )
            values = {
                key: item[key]
                for key in (
                    "category", "status", "severity", "confidence", "subject_location", "source_location",
                    "subject_excerpt", "source_excerpt", "explanation", "method", "limitations", "artifacts",
                )
            }
            if existing is None:
                db.add(
                    EvidenceRecord(
                        task_id=task.id, code=item["code"], fingerprint=fingerprint,
                        evidence_version=evidence_version, **values
                    )
                )
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
        task.coverage_summary = {**task.coverage_summary, **analysis["coverage"], "method_version": METHOD_VERSION}
        if analysis["evidence"]:
            task.status = TaskStatus.REVIEW_READY.value
            task.stage_message = "深度检查完成，请逐项复核证据"
        else:
            task.status = TaskStatus.REVIEWED.value
            task.stage_message = "深度检查完成，未发现需要人工裁决的证据"
        task.error_code = None
        task.error_message = None
        run.status = "succeeded"
        db.add(
            AuditEvent(
                task_id=task.id,
                event_type="review.completed",
                details={"method_version": METHOD_VERSION, "evidence_count": len(analysis["evidence"])},
            )
        )
        db.commit()
        return {"status": "completed"}
    except Exception as exc:
        db.rollback()
        logger.error("deep review failed", extra={"task_id": task_id, "error_type": type(exc).__name__})
        task = db.get(PaperTask, parsed_task_id)
        run = db.get(ReviewRun, parsed_run_id)
        if task is not None and run is not None:
            task.status = TaskStatus.CHECKING_FAILED.value
            task.stage_message = "深度检查未能完成"
            task.error_code = "deep_review_failed"
            task.error_message = "检查服务未能完成证据提取，请稍后重试"
            run.status = "failed"
            db.add(AuditEvent(task_id=task.id, event_type="review.failed", details={"reason": "deep_review_failed"}))
            db.commit()
        return {"status": "failed"}
    finally:
        db.close()
