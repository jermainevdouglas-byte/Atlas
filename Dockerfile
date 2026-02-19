FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data /app/data/logs /app/data/uploads /app/storage

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-5000}/health" || exit 1'

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-3} --threads ${GUNICORN_THREADS:-6} --timeout ${GUNICORN_TIMEOUT:-90} --access-logfile - --error-logfile - wsgi:app"]

