# Two tails, not users/'s three: no arq worker until stage 2 gives this service
# a hold to expire. `prod` stays last so an untargeted build gets the lean one.
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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]


FROM base AS prod
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "3"]
