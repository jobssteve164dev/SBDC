from celery import Celery

from sbdc_api.config import get_settings


settings = get_settings()
app = Celery("sbdc-worker", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)
app.autodiscover_tasks(["sbdc_worker"])
