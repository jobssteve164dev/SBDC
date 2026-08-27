FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system --gid 1001 sbdc && adduser --system --uid 1001 --ingroup sbdc sbdc
COPY pyproject.toml ./
COPY packages/domain ./packages/domain
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/apps/api:/app/apps/worker:/app/packages/domain
USER sbdc
EXPOSE 8000
CMD ["uvicorn", "sbdc_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
