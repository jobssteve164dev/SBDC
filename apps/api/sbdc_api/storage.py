from collections.abc import Iterator
from io import BytesIO

from minio import Minio

from .config import get_settings


settings = get_settings()
client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def source_storage_key(task_id: str, asset_id: str) -> str:
    return f"tasks/{task_id}/source/{asset_id}.pdf"


def submission_storage_key(submission_id: str, asset_id: str) -> str:
    return f"submissions/{submission_id}/source/{asset_id}.pdf"


def ensure_bucket() -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    client.put_object(settings.minio_bucket, key, BytesIO(data), len(data), content_type=content_type)


def put_file(key: str, path: str, size: int, content_type: str) -> None:
    with open(path, "rb") as stream:
        client.put_object(settings.minio_bucket, key, stream, size, content_type=content_type)


def remove_object(key: str) -> None:
    client.remove_object(settings.minio_bucket, key)


def get_bytes(key: str) -> bytes:
    response = client.get_object(settings.minio_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def stream_object(key: str) -> Iterator[bytes]:
    response = client.get_object(settings.minio_bucket, key)
    try:
        while chunk := response.read(1024 * 1024):
            yield chunk
    finally:
        response.close()
        response.release_conn()
