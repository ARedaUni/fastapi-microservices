# `prod` stays last so an untargeted build gets the lean one.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY ./alembic.ini /app/alembic.ini
COPY ./migrations /app/migrations
COPY ./app /app/app


FROM base AS dev
COPY ./requirements-dev.txt /app/requirements-dev.txt
RUN pip install -r requirements-dev.txt
COPY ./pyproject.toml /app/pyproject.toml
COPY ./tests /app/tests
# An SSE stream never finishes on its own, so without a timeout shutdown waits
# on open tabs forever. Cut them after 5s; the browser reconnects and refetches.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload", "--timeout-graceful-shutdown", "5"]


FROM base AS worker
CMD ["arq", "app.worker.WorkerSettings"]


FROM base AS prod
# An SSE stream never finishes on its own, so without a timeout shutdown waits
# on open tabs forever. Cut them after 5s; the browser reconnects and refetches.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "3", "--timeout-graceful-shutdown", "5"]
