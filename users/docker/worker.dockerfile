FROM python:3.8-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app
ENV PYTHONPATH /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install --upgrade pip --no-cache && \
    pip install -r requirements.txt --no-cache && \
    rm /app/requirements.txt

COPY ./app /app/app

CMD ["arq", "app.worker.WorkerSettings"]
