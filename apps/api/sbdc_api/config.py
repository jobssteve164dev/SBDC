from functools import lru_cache

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
