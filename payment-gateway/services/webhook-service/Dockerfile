# Build context: workspace root
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libpq-dev gcc     && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN groupadd -r appuser && useradd -r -g appuser appuser

FROM base AS deps
RUN pip install --no-cache-dir     "fastapi>=0.111.0"     "uvicorn[standard]>=0.29.0"     "sqlalchemy>=2.0.30"     "alembic>=1.13.0"     "asyncpg>=0.29.0"     "pydantic>=2.7.0"     "pydantic-settings>=2.2.0"     "aiokafka>=0.11.0"     "httpx>=0.27.0"     "redis[asyncio]>=5.0.4"     "python-jose[cryptography]>=3.3.0"     "cryptography>=42.0.0"     "structlog>=24.1.0"     "prometheus-fastapi-instrumentator>=7.0.0"     "celery[redis]>=5.4.0"     "boto3>=1.34.0"     "sentry-sdk[fastapi,sqlalchemy]>=2.0.0"     "starlette>=0.37.0"
RUN pip install --no-cache-dir "psycopg2-binary>=2.9.9"
FROM deps AS final
COPY shared/ /app/shared/
COPY services/webhook-service/ /app/
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8021
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3     CMD curl -f http://localhost:8021/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8021", "--workers", "2"]
