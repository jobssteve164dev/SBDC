FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system --gid 1001 sbdc && adduser --system --uid 1001 --ingroup sbdc sbdc
COPY pyproject.toml ./
COPY packages/domain ./packages/domain
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/apps/api:/app/apps/worker:/app/packages/domain
USER sbdc
CMD ["celery", "-A", "sbdc_worker.celery_app:app", "worker", "--loglevel=INFO", "--concurrency=1"]
