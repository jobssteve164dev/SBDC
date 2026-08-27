import hashlib
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager

import fitz
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sbdc_domain import CoverageSummary, TaskStatus, transition_task

from .config import get_settings
from .database import get_db
from .models import AuditEvent, DocumentAsset, PaperTask, ParsedDocument, ParseRun, ReferenceSource
from .queue import celery_client
from .schemas import AssetOut, ParseAccepted, ParsedDocumentOut, ReferenceOut, TaskCreate, TaskOut
from .storage import ensure_bucket, put_file, source_storage_key, stream_object


settings = get_settings()


class RequestTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].endswith("/assets"):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = json.dumps({"detail": "PDF 不能超过 50 MB"}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bucket()
    yield


app = FastAPI(title="SBDC API", version="0.1.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware, max_bytes=settings.max_pdf_bytes + 1024 * 1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def get_task_or_404(db: Session, task_id: uuid.UUID, *, lock: bool = False) -> PaperTask:
    statement = select(PaperTask).where(PaperTask.id == task_id)
    if lock:
        statement = statement.with_for_update()
    task = db.scalar(statement)
    if task is None:
        raise HTTPException(status_code=404, detail="检查任务不存在")
    return task


def task_response(db: Session, task: PaperTask) -> TaskOut:
    asset = db.get(DocumentAsset, task.source_file_id) if task.source_file_id else None
    document = db.scalar(select(ParsedDocument).where(ParsedDocument.task_id == task.id))
    references = list(
        db.scalars(select(ReferenceSource).where(ReferenceSource.task_id == task.id).order_by(ReferenceSource.ordinal))
    )
    return TaskOut(
        id=task.id,
        status=task.status,
        stage_message=task.stage_message,
        evidence_level=task.evidence_level,
        retention_policy=task.retention_policy,
        coverage_summary=task.coverage_summary,
        source_file_id=task.source_file_id,
        error_code=task.error_code,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        source_asset=AssetOut.model_validate(asset) if asset else None,
        document=ParsedDocumentOut.model_validate(document) if document else None,
        references=[ReferenceOut.model_validate(item) for item in references],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    task = PaperTask(
        evidence_level=payload.evidence_level,
        retention_policy=payload.retention_policy,
        requested_checks=["document_structure", "references"],
        coverage_summary=CoverageSummary().model_dump(),
    )
    db.add(task)
    db.flush()
    db.add(AuditEvent(task_id=task.id, event_type="task.created", details={"evidence_level": "L1"}))
    db.commit()
    db.refresh(task)
    return task_response(db, task)


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> TaskOut:
    return task_response(db, get_task_or_404(db, task_id))


def mark_validation_failure(db: Session, task: PaperTask, code: str, message: str) -> None:
    task.status = TaskStatus.VALIDATION_FAILED.value
    task.stage_message = "文件验证未通过"
    task.error_code = code
    task.error_message = message
    db.add(AuditEvent(task_id=task.id, event_type="asset.rejected", details={"reason": code}))
    db.commit()


@app.post("/tasks/{task_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_source_pdf(
    task_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AssetOut:
    task = get_task_or_404(db, task_id, lock=True)
    if task.source_file_id is not None:
        raise HTTPException(status_code=409, detail="此检查任务已经上传论文")
    if task.status not in {TaskStatus.CREATED.value, TaskStatus.VALIDATION_FAILED.value}:
        raise HTTPException(status_code=409, detail="当前状态不能上传论文")
    task.status = transition_task(task.status, TaskStatus.VALIDATING).value
    task.stage_message = "正在验证 PDF"
    task.error_code = None
    task.error_message = None
    db.commit()

    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        message = "仅支持 PDF 文件"
        mark_validation_failure(db, task, "unsupported_media_type", message)
        raise HTTPException(status_code=415, detail=message)

    digest = hashlib.sha256()
    size = 0
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="sbdc-upload-", suffix=".pdf", delete=False) as temp:
            temp_path = temp.name
            first_chunk = True
            while chunk := await file.read(1024 * 1024):
                if first_chunk and not chunk.startswith(b"%PDF-"):
                    message = "文件内容不是有效 PDF"
                    mark_validation_failure(db, task, "invalid_pdf_signature", message)
                    raise HTTPException(status_code=422, detail=message)
                first_chunk = False
                size += len(chunk)
                if size > settings.max_pdf_bytes:
                    message = f"PDF 不能超过 {settings.max_pdf_bytes // 1024 // 1024} MB"
                    mark_validation_failure(db, task, "file_too_large", message)
                    raise HTTPException(status_code=413, detail=message)
                digest.update(chunk)
                temp.write(chunk)
        if size == 0:
            message = "PDF 文件为空"
            mark_validation_failure(db, task, "empty_file", message)
            raise HTTPException(status_code=422, detail=message)
        try:
            with fitz.open(temp_path) as pdf:
                if pdf.needs_pass:
                    raise ValueError("encrypted")
                page_count = pdf.page_count
                if page_count < 1:
                    raise ValueError("empty")
                if page_count > settings.max_pdf_pages:
                    message = f"PDF 不能超过 {settings.max_pdf_pages} 页"
                    mark_validation_failure(db, task, "page_limit_exceeded", message)
                    raise HTTPException(status_code=413, detail=message)
                _ = pdf[0].rect
        except HTTPException:
            raise
        except Exception:
            message = "PDF 已损坏、加密或无法读取"
            mark_validation_failure(db, task, "invalid_pdf", message)
            raise HTTPException(status_code=422, detail=message) from None

        asset_id = uuid.uuid4()
        key = source_storage_key(str(task.id), str(asset_id))
        try:
            put_file(key, temp_path, size, "application/pdf")
        except Exception:
            message = "文件存储暂时不可用，请稍后重试"
            mark_validation_failure(db, task, "storage_unavailable", message)
            raise HTTPException(status_code=503, detail=message) from None
        asset = DocumentAsset(
            id=asset_id,
            task_id=task.id,
            role="source_paper",
            storage_key=key,
            sha256=digest.hexdigest(),
            media_type="application/pdf",
            size_bytes=size,
            page_count=page_count,
            provenance={"source": "user_upload"},
        )
        db.add(asset)
        db.flush()
        task.source_file_id = asset.id
        task.stage_message = "PDF 已验证，准备解析"
        db.add(
            AuditEvent(
                task_id=task.id,
                event_type="asset.accepted",
                details={"asset_id": str(asset.id), "sha256": asset.sha256, "size_bytes": size, "pages": page_count},
            )
        )
        db.commit()
        db.refresh(asset)
        return AssetOut.model_validate(asset)
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.post("/tasks/{task_id}/parse", response_model=ParseAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_parse(task_id: uuid.UUID, db: Session = Depends(get_db)) -> ParseAccepted:
    task = get_task_or_404(db, task_id, lock=True)
    if task.source_file_id is None:
        raise HTTPException(status_code=409, detail="请先上传并验证 PDF")
    asset = db.get(DocumentAsset, task.source_file_id)
    if asset is None or asset.task_id != task.id:
        raise HTTPException(status_code=409, detail="源论文资产不可用")
    if task.status in {TaskStatus.PARSING.value, TaskStatus.REFERENCES_READY.value} and task.parse_source_sha256 == asset.sha256:
        return ParseAccepted(task_id=task.id, status=task.status, enqueued=False)
    if task.status not in {TaskStatus.VALIDATING.value, TaskStatus.PARSING_FAILED.value}:
        raise HTTPException(status_code=409, detail="当前状态不能开始解析")

    task.status = transition_task(task.status, TaskStatus.PARSING).value
    task.stage_message = "正在解析论文结构与参考文献"
    task.error_code = None
    task.error_message = None
    task.parse_attempt += 1
    task.parse_source_sha256 = asset.sha256
    celery_task_id = f"parse:{task.id}:{asset.sha256[:16]}:{task.parse_attempt}"
    run = ParseRun(
        task_id=task.id,
        source_sha256=asset.sha256,
        attempt=task.parse_attempt,
        celery_task_id=celery_task_id,
    )
    db.add(run)
    db.add(AuditEvent(task_id=task.id, event_type="parse.queued", details={"attempt": task.parse_attempt}))
    db.commit()
    try:
        celery_client.send_task("sbdc.parse_document", args=[str(task.id), str(run.id)], task_id=celery_task_id)
    except Exception:
        task.status = TaskStatus.PARSING_FAILED.value
        task.stage_message = "解析任务未能启动"
        task.error_code = "queue_unavailable"
        task.error_message = "解析服务暂时不可用，请稍后重试"
        run.status = "failed"
        db.add(AuditEvent(task_id=task.id, event_type="parse.failed", details={"reason": "queue_unavailable"}))
        db.commit()
        raise HTTPException(status_code=503, detail=task.error_message) from None
    return ParseAccepted(task_id=task.id, status=task.status, enqueued=True)


@app.get("/tasks/{task_id}/assets/{asset_id}/content")
def get_asset_content(task_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    get_task_or_404(db, task_id)
    asset = db.scalar(select(DocumentAsset).where(DocumentAsset.id == asset_id, DocumentAsset.task_id == task_id))
    if asset is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return StreamingResponse(
        stream_object(asset.storage_key),
        media_type=asset.media_type,
        headers={"Content-Disposition": 'inline; filename="paper.pdf"', "Cache-Control": "private, no-store"},
    )
