import hashlib
import asyncio
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
import secrets
import hmac
import logging

import fitz
from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sbdc_domain import CoverageSummary, TaskStatus, transition_task

from .config import get_settings
from .database import SessionLocal, get_db
from .models import (
    AuditEvent, DocumentAsset, PaperTask, ParsedDocument, ParseRun, PublicSession,
    PublicUser, ReferenceSource, ResearchSubmission,
)
from .public_auth import hash_password, normalize_email, verify_password
from .public_rate_limit import public_rate_limiter
from .queue import celery_client
from .schemas import (
    AssetOut, ParseAccepted, ParsedDocumentOut, PublicUserOut, ReferenceOut,
    ReviewerSubmissionOut, SubmissionOut, TaskCreate, TaskOut,
)
from .storage import ensure_bucket, put_file, remove_object, source_storage_key, stream_object, submission_storage_key


settings = get_settings()
logger = logging.getLogger(__name__)


class RequestTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        limited_path = scope["path"].endswith("/assets") or scope["path"] == "/public/submissions"
        if scope["type"] != "http" or scope["method"] != "POST" or not limited_path:
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


def cleanup_incomplete_submissions() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        items = list(db.scalars(select(ResearchSubmission).where(
            ResearchSubmission.status.in_(["uploading", "purge_failed", "purging"]),
            ResearchSubmission.cleanup_after <= now,
        ).with_for_update(skip_locked=True).limit(100)))
        item_ids = [item.id for item in items]
        for item in items:
            item.status = "purging"
            item.cleanup_after = now + timedelta(minutes=15)
        db.commit()
        for item_id in item_ids:
            item = db.get(ResearchSubmission, item_id, with_for_update=True, populate_existing=True)
            if item is None or item.status != "purging":
                db.rollback()
                continue
            try:
                remove_object(item.storage_key)
                item.status = "purged"
                item.cleanup_error = None
                item.cleanup_after = None
            except Exception as error:
                item.status = "purge_failed"
                item.cleanup_attempts += 1
                item.cleanup_error = type(error).__name__[:120]
                item.cleanup_after = datetime.now(UTC) + timedelta(minutes=15)
            release_submission_quota(db, item)
            db.commit()


def release_submission_quota(db: Session, item: ResearchSubmission) -> None:
    if item.quota_released:
        return
    user = db.get(PublicUser, item.submitted_by_id, with_for_update=True, populate_existing=True)
    if user and item.created_at and user.quota_date == item.created_at.date():
        user.quota_count = max(0, user.quota_count - 1)
        user.quota_bytes = max(0, user.quota_bytes - item.size_bytes)
    item.quota_released = True


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(15 * 60)
        try:
            await asyncio.to_thread(cleanup_incomplete_submissions)
        except Exception:
            logger.exception("scheduled submission cleanup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bucket()
    try:
        await asyncio.to_thread(cleanup_incomplete_submissions)
    except Exception:
        logger.exception("startup submission cleanup failed")
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


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


PUBLIC_SESSION_COOKIE = "sbdc_public_session"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",", 1)[0]
    return (forwarded.strip() or (request.client.host if request.client else "unknown"))[:128]


def trusted_public_write(request: Request) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status_code=403, detail="请求来源无效，请从 SBDC 页面重试")
    origin = request.headers.get("origin")
    allowed = {value.strip().rstrip("/") for value in settings.public_origins.split(",") if value.strip()}
    if not origin or origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="请求来源无效，请从 SBDC 页面重试")


def require_internal_reviewer(
    internal_secret: str | None = Header(default=None, alias="X-SBDC-Internal-Secret"),
) -> None:
    expected = settings.internal_api_secret
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="审查服务认证尚未配置")
    if not internal_secret or not hmac.compare_digest(internal_secret, expected):
        raise HTTPException(status_code=401, detail="无权访问审查投稿")


def _set_public_session(response: Response, db: Session, user: PublicUser) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.public_session_days)
    db.add(PublicSession(user_id=user.id, token_hash=_token_hash(token), expires_at=expires_at))
    db.commit()
    response.set_cookie(
        PUBLIC_SESSION_COOKIE, token, max_age=settings.public_session_days * 86400,
        httponly=True, secure=settings.public_cookie_secure, samesite="lax", path="/",
    )


def current_public_user(
    session_token: str | None = Cookie(default=None, alias=PUBLIC_SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> PublicUser:
    if not session_token or len(session_token) > 200:
        raise HTTPException(status_code=401, detail="请先登录投稿账号")
    session = db.scalar(
        select(PublicSession).where(
            PublicSession.token_hash == _token_hash(session_token),
            PublicSession.expires_at > datetime.now(UTC),
        )
    )
    user = db.get(PublicUser, session.user_id) if session else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="请先登录投稿账号")
    return user


@app.post("/public/auth/register", response_model=PublicUserOut, status_code=201)
def register_public_user(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(trusted_public_write),
) -> PublicUserOut:
    if not public_rate_limiter.allow(f"register:{_client_key(request)}", limit=5, window_seconds=3600):
        raise HTTPException(status_code=429, detail="注册尝试过多，请稍后再试")
    try:
        normalized = normalize_email(email)
        password_hash = hash_password(password)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if db.scalar(select(PublicUser).where(PublicUser.email == normalized)):
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    user = PublicUser(email=normalized, password_hash=password_hash)
    db.add(user)
    db.flush()
    _set_public_session(response, db, user)
    return PublicUserOut.model_validate(user)


@app.post("/public/auth/login", response_model=PublicUserOut)
def login_public_user(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(trusted_public_write),
) -> PublicUserOut:
    if not public_rate_limiter.allow(f"login:{_client_key(request)}", limit=12, window_seconds=900):
        raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")
    try:
        normalized = normalize_email(email)
    except ValueError:
        normalized = "invalid@example.invalid"
    user = db.scalar(select(PublicUser).where(PublicUser.email == normalized))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    _set_public_session(response, db, user)
    return PublicUserOut.model_validate(user)


@app.post("/public/auth/logout", status_code=204)
def logout_public_user(
    _request: Request,
    response: Response,
    session_token: str | None = Cookie(default=None, alias=PUBLIC_SESSION_COOKIE),
    db: Session = Depends(get_db),
    _: None = Depends(trusted_public_write),
) -> Response:
    if session_token:
        session = db.scalar(select(PublicSession).where(PublicSession.token_hash == _token_hash(session_token)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(PUBLIC_SESSION_COOKIE, path="/")
    return response


@app.get("/public/me", response_model=PublicUserOut)
def get_public_me(user: PublicUser = Depends(current_public_user)) -> PublicUserOut:
    return PublicUserOut.model_validate(user)


@app.get("/public/submissions", response_model=list[SubmissionOut])
def list_own_submissions(
    user: PublicUser = Depends(current_public_user),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    items = db.scalars(
        select(ResearchSubmission).where(
            ResearchSubmission.submitted_by_id == user.id,
            ResearchSubmission.status == "received",
        )
        .order_by(ResearchSubmission.created_at.desc()).limit(100)
    )
    return [SubmissionOut.model_validate(item) for item in items]


@app.post("/public/submissions", response_model=SubmissionOut, status_code=201)
async def create_public_submission(
    request: Request,
    title: str = Form(...),
    reason: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    authors: str | None = Form(default=None),
    user: PublicUser = Depends(current_public_user),
    db: Session = Depends(get_db),
    _: None = Depends(trusted_public_write),
) -> SubmissionOut:
    title = title.strip()
    reason = reason.strip()
    authors = authors.strip() if authors else None
    if not 2 <= len(title) <= 500 or not 10 <= len(reason) <= 4000:
        raise HTTPException(status_code=422, detail="请填写论文题名和至少 10 个字符的投稿说明")
    if authors and len(authors) > 1000:
        raise HTTPException(status_code=422, detail="作者信息不能超过 1000 个字符")
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="请确认你有权提交该文件用于审查")
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")
    if not public_rate_limiter.allow(f"submit:{user.id}:{_client_key(request)}", limit=12, window_seconds=86400):
        raise HTTPException(status_code=429, detail="今日投稿已达上限，请稍后再试")

    submission_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    digest = hashlib.sha256()
    size = 0
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="sbdc-submission-", suffix=".pdf", delete=False) as temp:
            temp_path = temp.name
            first_chunk = True
            while chunk := await file.read(1024 * 1024):
                if first_chunk and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(status_code=422, detail="文件内容不是有效 PDF")
                first_chunk = False
                size += len(chunk)
                if size > settings.max_pdf_bytes:
                    raise HTTPException(status_code=413, detail="PDF 不能超过 50 MB")
                digest.update(chunk)
                temp.write(chunk)
        try:
            with fitz.open(temp_path) as pdf:
                if pdf.needs_pass or pdf.page_count < 1:
                    raise ValueError
                page_count = pdf.page_count
                if page_count > settings.max_pdf_pages:
                    raise HTTPException(status_code=413, detail=f"PDF 不能超过 {settings.max_pdf_pages} 页")
                _ = pdf[0].rect
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=422, detail="PDF 已损坏、加密或无法读取") from None
        key = submission_storage_key(str(submission_id), str(asset_id))
        locked_user = db.get(PublicUser, user.id, with_for_update=True, populate_existing=True)
        if locked_user is None or not locked_user.is_active:
            raise HTTPException(status_code=401, detail="请先登录投稿账号")
        quota_date = datetime.now(UTC).date()
        if locked_user.quota_date != quota_date:
            locked_user.quota_date = quota_date
            locked_user.quota_count = 0
            locked_user.quota_bytes = 0
        if locked_user.quota_count >= 10 or locked_user.quota_bytes + size > 200 * 1024 * 1024:
            raise HTTPException(status_code=429, detail="今日投稿已达上限，请稍后再试")
        locked_user.quota_count += 1
        locked_user.quota_bytes += size
        item = ResearchSubmission(
            id=submission_id, submitted_by_id=user.id, title=title, authors=authors,
            reason=reason, rights_confirmed=True, status="uploading", storage_key=key,
            sha256=digest.hexdigest(), size_bytes=size, page_count=page_count,
            cleanup_after=datetime.now(UTC) + timedelta(hours=1), quota_released=False,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        try:
            put_file(key, temp_path, size, "application/pdf")
        except Exception:
            try:
                remove_object(key)
                item.status = "purged"
                item.cleanup_error = None
                item.cleanup_after = None
            except Exception as error:
                item.status = "purge_failed"
                item.cleanup_attempts += 1
                item.cleanup_error = type(error).__name__[:120]
                item.cleanup_after = datetime.now(UTC) + timedelta(minutes=15)
            release_submission_quota(db, item)
            db.commit()
            raise HTTPException(status_code=503, detail="文件存储暂时不可用，请稍后重试") from None
        item = db.get(ResearchSubmission, submission_id, with_for_update=True, populate_existing=True)
        if item is None or item.status != "uploading":
            with suppress(Exception):
                remove_object(key)
            raise HTTPException(status_code=503, detail="投稿处理超时，请重新提交")
        item.status = "received"
        item.cleanup_after = None
        try:
            db.commit()
        except Exception:
            db.rollback()
            try:
                remove_object(key)
                persisted = db.get(ResearchSubmission, submission_id)
                if persisted:
                    persisted.status = "purged"
                    persisted.cleanup_error = None
                    persisted.cleanup_after = None
                    release_submission_quota(db, persisted)
                    db.commit()
            except Exception:
                db.rollback()
                persisted = db.get(ResearchSubmission, submission_id)
                if persisted:
                    persisted.status = "purge_failed"
                    persisted.cleanup_attempts += 1
                    persisted.cleanup_error = "object_cleanup_failed"
                    persisted.cleanup_after = datetime.now(UTC) + timedelta(minutes=15)
                    release_submission_quota(db, persisted)
                    with suppress(Exception):
                        db.commit()
                logger.exception("submission object cleanup failed for key %s", key)
            raise
        db.refresh(item)
        return SubmissionOut.model_validate(item)
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.get("/submissions", response_model=list[ReviewerSubmissionOut])
def list_reviewer_submissions(
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_reviewer),
) -> list[ReviewerSubmissionOut]:
    rows = db.execute(
        select(ResearchSubmission, PublicUser.email)
        .join(PublicUser, PublicUser.id == ResearchSubmission.submitted_by_id)
        .where(ResearchSubmission.status == "received")
        .order_by(ResearchSubmission.created_at.desc()).limit(200)
    )
    return [ReviewerSubmissionOut(
        id=item.id, title=item.title, authors=item.authors, reason=item.reason,
        status=item.status, size_bytes=item.size_bytes, page_count=item.page_count,
        created_at=item.created_at, submitter_email=email,
    ) for item, email in rows]


@app.get("/submissions/{submission_id}/content")
def get_submission_content(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_reviewer),
) -> StreamingResponse:
    item = db.get(ResearchSubmission, submission_id)
    if item is None:
        raise HTTPException(status_code=404, detail="投稿不存在")
    return StreamingResponse(
        stream_object(item.storage_key), media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="submitted-paper.pdf"', "Cache-Control": "private, no-store"},
    )


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
