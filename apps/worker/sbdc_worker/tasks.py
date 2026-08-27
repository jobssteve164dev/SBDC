import logging
import uuid

import httpx
from sqlalchemy import delete, select

from sbdc_api.config import get_settings
from sbdc_api.database import SessionLocal
from sbdc_api.models import AuditEvent, DocumentAsset, PaperTask, ParsedDocument, ParseRun, ReferenceSource
from sbdc_api.storage import get_bytes, put_bytes
from sbdc_domain import CoverageSummary, TaskStatus

from .celery_app import app
from .tei import parse_tei


settings = get_settings()
logger = logging.getLogger(__name__)


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
