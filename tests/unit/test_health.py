from fastapi import HTTPException
import pytest

from sbdc_api import main


def test_health_rejects_an_unusable_reviewer_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.settings, "internal_api_secret", "too-short")
    with pytest.raises(HTTPException) as error:
        main.health()
    assert error.value.status_code == 503


def test_health_accepts_a_reviewer_secret_with_32_or_more_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.settings, "internal_api_secret", "x" * 32)
    assert main.health() == {"status": "ok"}
