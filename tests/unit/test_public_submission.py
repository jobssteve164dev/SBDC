import uuid
from datetime import UTC, datetime
from io import BytesIO

import fitz
import pytest
from fastapi import HTTPException, Response, UploadFile
from starlette.requests import Request

from sbdc_api import main
from sbdc_api.models import PublicUser, ResearchSubmission
from sbdc_api.public_auth import hash_password, normalize_email, verify_password
from sbdc_api.storage import submission_storage_key


def test_public_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("a-correct-horse-battery-staple")
    second = hash_password("a-correct-horse-battery-staple")

    assert first != second
    assert verify_password("a-correct-horse-battery-staple", first)
    assert not verify_password("wrong-password-value", first)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Researcher@Example.ORG ", "researcher@example.org"),
        ("person+review@example.cn", "person+review@example.cn"),
    ],
)
def test_public_email_is_normalized(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


def test_public_email_rejects_invalid_values() -> None:
    for value in ("", "not-an-email", "name@", "@example.org"):
        with pytest.raises(ValueError):
            normalize_email(value)


def test_submission_storage_key_never_uses_uploaded_filename() -> None:
    submission_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    key = submission_storage_key(str(submission_id), str(asset_id))

    assert key == f"submissions/{submission_id}/source/{asset_id}.pdf"
    assert "paper" not in key


class FakeSession:
    def __init__(self, user: PublicUser | None = None) -> None:
        self.added: list[object] = []
        self.user = user
        self.commit_calls = 0

    def scalar(self, _statement):
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def get(self, model, item_id, **_kwargs):
        if model is PublicUser:
            return self.user
        return next((item for item in self.added if isinstance(item, model) and getattr(item, "id", None) == item_id), None)

    def flush(self) -> None:
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid.uuid4()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        return None

    def refresh(self, _item: object) -> None:
        if getattr(_item, "status", None) is None:
            _item.status = "received"
        if getattr(_item, "created_at", None) is None:
            _item.created_at = datetime.now(UTC)


def test_registration_issues_public_only_secure_session_cookie() -> None:
    response = Response()
    db = FakeSession()

    account = main.register_public_user(
        request=Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)}),
        response=response,
        email=" Researcher@Example.org ",
        password="correct-horse-battery-staple",
        db=db,
    )

    assert account.email == "researcher@example.org"
    cookie = response.headers["set-cookie"]
    assert "sbdc_public_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert any(item.__class__.__name__ == "PublicSession" for item in db.added)


@pytest.mark.asyncio
async def test_submission_validates_and_stores_a_real_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = fitz.open()
    pdf.new_page()
    payload = pdf.tobytes()
    pdf.close()
    uploaded = UploadFile(filename="revealing-user-filename.pdf", file=BytesIO(payload), headers={"content-type": "application/pdf"})
    stored: dict[str, object] = {}
    monkeypatch.setattr(main, "put_file", lambda key, path, size, content_type: stored.update(
        key=key, size=size, content_type=content_type
    ))
    user = PublicUser(id=uuid.uuid4(), email="researcher@example.org", password_hash="unused", is_active=True)
    db = FakeSession(user)

    result = await main.create_public_submission(
        request=Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)}),
        title="一篇待核查论文",
        reason="论文结论与引用来源之间似乎存在不一致，需要复核。",
        rights_confirmed=True,
        file=uploaded,
        authors="示例作者",
        user=user,
        db=db,
    )

    assert result.title == "一篇待核查论文"
    assert result.page_count == 1
    assert result.status == "received"
    assert stored["content_type"] == "application/pdf"
    assert "revealing-user-filename" not in str(stored["key"])
    assert any(isinstance(item, ResearchSubmission) for item in db.added)
    assert user.quota_count == 1
    assert user.quota_bytes == len(payload)
    submission = next(item for item in db.added if isinstance(item, ResearchSubmission))
    assert submission.status == "received"
    assert submission.cleanup_after is None


def test_cross_site_public_write_is_rejected() -> None:
    request = Request({
        "type": "http", "method": "POST", "path": "/public/submissions",
        "headers": [(b"origin", b"https://attacker.example"), (b"sec-fetch-site", b"cross-site")],
    })

    with pytest.raises(HTTPException) as error:
        main.trusted_public_write(request)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_database_failure_removes_stored_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = fitz.open()
    pdf.new_page()
    uploaded = UploadFile(filename="paper.pdf", file=BytesIO(pdf.tobytes()), headers={"content-type": "application/pdf"})
    pdf.close()
    removed: list[str] = []
    monkeypatch.setattr(main, "put_file", lambda *_args: None)
    monkeypatch.setattr(main, "remove_object", removed.append)

    class FailingSession(FakeSession):
        def commit(self) -> None:
            self.commit_calls += 1
            if self.commit_calls == 2:
                raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        active_user = PublicUser(id=uuid.uuid4(), email="test@example.org", password_hash="unused", is_active=True)
        failing_db = FailingSession(active_user)
        await main.create_public_submission(
            request=Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.2", 1)}),
            title="待核查论文", reason="这是一段足够长的核查原因说明。", rights_confirmed=True,
            file=uploaded, authors=None, user=active_user, db=failing_db,
        )

    assert len(removed) == 1
    assert removed[0].startswith("submissions/")
    submission = next(item for item in failing_db.added if isinstance(item, ResearchSubmission))
    assert submission.status == "purged"
    assert submission.quota_released is True
    assert active_user.quota_count == 0
    assert active_user.quota_bytes == 0
