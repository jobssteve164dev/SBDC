from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://sbdc:sbdc@postgres:5432/sbdc"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "sbdc-local"
    minio_secret_key: str = "sbdc-local-secret"
    minio_bucket: str = "sbdc"
    minio_secure: bool = False
    grobid_url: str = "http://grobid:8070"
    max_pdf_bytes: int = 52_428_800
    max_pdf_pages: int = 500
    request_timeout_seconds: int = 300
    cors_origins: str = "http://localhost:3000"
    public_cookie_secure: bool = True
    public_session_days: int = 30
    public_origins: str = "https://sbdc.szlk.uk,http://localhost:3000,http://127.0.0.1:3100"
    internal_api_secret: str = Field(
        default="",
        validation_alias=AliasChoices("SBDC_INTERNAL_API_SECRET", "internal_api_secret"),
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def select_installed_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
