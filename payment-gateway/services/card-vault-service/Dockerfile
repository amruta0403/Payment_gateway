FROM python:3.12-slim AS base
WORKDIR /app
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN apt-get update && apt-get install -y --no-install-recommends curl && apt-get clean

FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml

FROM deps AS final
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8011
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD curl -f http://localhost:8011/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011", "--workers", "2"]
