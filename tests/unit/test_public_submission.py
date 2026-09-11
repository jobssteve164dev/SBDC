import uuid
from datetime import UTC, datetime
from io import BytesIO

import fitz
import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from sbdc_api import main
from sbdc_api.models import ResearchSubmission
from sbdc_api.public_auth import normalize_email
from sbdc_api.schemas import PublicSubmissionOut
from sbdc_api.storage import submission_storage_key


def submission_request(locale: str = "zh-CN") -> Request:
    path = "/en/submit" if locale == "en" else "/submit"
    return Request({
        "type": "http", "method": "POST", "path": "/submissions",
        "headers": [(b"referer", f"https://sbdc.szlk.uk{path}".encode())],
        "client": ("127.0.0.1", 1),
    })


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
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_calls = 0

    def scalar(self, _statement):
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def get(self, model, item_id, **_kwargs):
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


@pytest.mark.asyncio
async def test_anonymous_submission_validates_and_stores_a_real_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = fitz.open()
    pdf.new_page()
    payload = pdf.tobytes()
    pdf.close()
    uploaded = UploadFile(filename="revealing-user-filename.pdf", file=BytesIO(payload), headers={"content-type": "application/pdf"})
    stored: dict[str, object] = {}
    monkeypatch.setattr(main, "put_file", lambda key, path, size, content_type: stored.update(
        key=key, size=size, content_type=content_type
    ))
    db = FakeSession()

    result = await main.create_public_submission(
        request=submission_request(),
        title="一篇待核查论文",
        reason="论文结论与引用来源之间似乎存在不一致，需要复核。",
        contact_email=" Researcher@Example.org ",
        is_public=True,
        rights_confirmed=True,
        terms_accepted=True,
        file=uploaded,
        authors="示例作者",
        db=db,
    )

    assert result.title == "一篇待核查论文"
    assert result.page_count == 1
    assert result.status == "received"
    assert stored["content_type"] == "application/pdf"
    assert "revealing-user-filename" not in str(stored["key"])
    assert any(isinstance(item, ResearchSubmission) for item in db.added)
    submission = next(item for item in db.added if isinstance(item, ResearchSubmission))
    assert submission.status == "received"
    assert submission.contact_email == "researcher@example.org"
    assert submission.is_public is True
    assert submission.terms_version == main.SUBMISSION_TERMS_VERSION
    assert submission.terms_locale == "zh-CN"
    assert submission.terms_accepted_at is not None
    assert submission.terms_notice_sha256 == main.submission_notice_sha256("zh-CN")
    assert submission.cleanup_after is None


@pytest.mark.asyncio
async def test_submission_rejects_missing_terms_acceptance() -> None:
    uploaded = UploadFile(filename="paper.pdf", file=BytesIO(b"%PDF-invalid"), headers={"content-type": "application/pdf"})
    with pytest.raises(HTTPException) as error:
        await main.create_public_submission(
            request=submission_request(),
            title="待核查论文", reason="这是一段足够长的核查原因说明。", rights_confirmed=True,
            terms_accepted=False, contact_email="test@example.org",
            is_public=False, file=uploaded, authors=None, db=FakeSession(),
        )
    assert error.value.status_code == 422
    assert "条款" in error.value.detail


def test_submission_terms_language_is_derived_from_the_page_url() -> None:
    assert main.submission_terms_locale(submission_request("zh-CN")) == "zh-CN"
    assert main.submission_terms_locale(submission_request("en")) == "en"

    forged = Request({
        "type": "http", "method": "POST", "path": "/submissions",
        "headers": [(b"referer", b"https://attacker.example/en/submit")],
    })
    with pytest.raises(HTTPException) as error:
        main.submission_terms_locale(forged)
    assert error.value.status_code == 403


def test_public_submission_projection_never_exposes_contact_email() -> None:
    item = ResearchSubmission(
        id=uuid.uuid4(), contact_email="private@example.org", title="公开论文", authors="示例作者",
        reason="公开说明只包含投稿者主动公开的核查理由。", is_public=True, rights_confirmed=True,
        status="received", storage_key="submissions/example/source/example.pdf", sha256="0" * 64,
        size_bytes=128, page_count=1, created_at=datetime.now(UTC),
    )

    payload = PublicSubmissionOut.model_validate(item).model_dump()

    assert payload["title"] == "公开论文"
    assert "contact_email" not in payload
    assert "storage_key" not in payload


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
        failing_db = FailingSession()
        await main.create_public_submission(
            request=submission_request(),
            title="待核查论文", reason="这是一段足够长的核查原因说明。", rights_confirmed=True,
            terms_accepted=True,
            contact_email="test@example.org", is_public=False,
            file=uploaded, authors=None, db=failing_db,
        )

    assert len(removed) == 1
    assert removed[0].startswith("submissions/")
    submission = next(item for item in failing_db.added if isinstance(item, ResearchSubmission))
    assert submission.status == "purged"


def test_reviewer_can_publish_and_withdraw_a_review_notice() -> None:
    item = ResearchSubmission(
        id=uuid.uuid4(), contact_email="private@example.org", title="待公示论文", reason="需要复核引用。",
        is_public=False, rights_confirmed=True, status="received", storage_key="submissions/x/source/y.pdf",
        sha256="0" * 64, size_bytes=128, page_count=1, created_at=datetime.now(UTC),
    )
    db = FakeSession()
    db.add(item)

    published = main.update_review_publication(
        submission_id=item.id, publish=True, review_outcome="insufficient_evidence",
        review_summary="现有材料不足以支持进一步结论，建议补充原始数据。", db=db,
    )
    assert published.review_published is True
    assert published.review_published_at is not None

    withdrawn = main.update_review_publication(
        submission_id=item.id, publish=False, review_outcome="insufficient_evidence",
        review_summary="现有材料不足以支持进一步结论，建议补充原始数据。", db=db,
    )
    assert withdrawn.review_published is False
    assert withdrawn.review_published_at is None
