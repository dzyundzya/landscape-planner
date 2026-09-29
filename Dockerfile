FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS python-builder

ENV POETRY_VERSION=1.8.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root


FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app appuser \
    && mkdir -p /data/storage

COPY --from=python-builder /app/.venv /app/.venv
COPY app/ /app/app/
COPY config/ /app/config/
COPY alembic.ini /app/alembic.ini
COPY --from=frontend-builder /build/app/static /app/app/static

RUN chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:backend_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
