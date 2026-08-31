# One image, three tails: the API, the arq worker, and a dev variant that also
# carries the test and lint tooling. `prod` is last so an untargeted build gets
# the lean image.
FROM python:3.8-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY ./alembic.ini /app/alembic.ini
COPY ./scripts /app/scripts
COPY ./migrations /app/migrations
COPY ./app /app/app


FROM base AS worker
CMD ["arq", "app.worker.WorkerSettings"]


FROM base AS dev
COPY ./requirements-dev.txt /app/requirements-dev.txt
RUN pip install -r requirements-dev.txt
COPY ./tests /app/tests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]


# 3 workers matches the WEB_CONCURRENCY the archived base image defaulted to.
FROM base AS prod
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "3"]
