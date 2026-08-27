from celery import Celery

from .config import get_settings


settings = get_settings()
celery_client = Celery("sbdc-api", broker=settings.redis_url, backend=settings.redis_url)
