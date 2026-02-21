# Production Readiness Checklist

This checklist upgrades AtlasBahamas for production while preserving current behavior.

## Current State

- App runtime: modular Python HTTP server (`atlasbahamas_app/core.py`, `atlasbahamas_app/http_handler.py`)
- Database: SQLite (active)
- Sessions/rate limits: Redis-backed when configured, with SQLite/in-process fallback
- Deployment: local runtime

## Target Production State

- Reverse proxy + TLS: Nginx
- App process manager: Gunicorn (via `wsgi.py` adapter)
- Database: PostgreSQL
- Cache/session/rate-limit backend: Redis
- Background workers: Celery (optional)
- Containerization: Docker Compose

## Phase 1 (Safe, immediate)

- [x] Add production scaffolding files (`docker-compose.yml`, `Dockerfile`, `.env.example`, `nginx.conf`, `deploy.sh`)
- [x] Add migration helper modules (`db.py`, `redis_client.py`)
- [x] Keep BaseHTTPRequestHandler as active runtime; retain Flask as non-production scaffold (`app.py`) and WSGI adapter path (`wsgi.py`, `atlasbahamas_app/wsgi_adapter.py`)
- [x] Add secure production env templates (`.env.example`, `.env.production.template`)
- [x] Add backup + restore verification tooling (`tools/backup_restore.py`, `tools/backup_cron.example`)
- [x] Add release gate tooling (`tools/release_gate.py`)
- [x] Add PostgreSQL migration tooling (`tools/migrate_sqlite_to_postgres.py`) and runtime SQL migrations (`migrations/postgres/*.sql`)
- [x] Preserve current runtime and pass test suite

## Phase 2 (Migration)

- [ ] Convert route handlers from `BaseHTTPRequestHandler` to Flask blueprints (optional, not required for deploy)
- [ ] Swap SQLite queries to PostgreSQL-compatible query layer
- [x] Move session/rate-limiting to Redis-backed store with SQLite fallback
- [ ] Add background jobs (email reminders/escalations)

## Phase 3 (Hardening)

- [x] Enforce HTTPS + secure cookie policy controls in runtime configuration
- [x] Add structured logging + critical email alert hooks
- [ ] Rotate secrets in deployed `.env` and disable demo credentials in production runtime
- [ ] CI/CD checks: lint, tests, container scan

## Commands

- Current app tests:
  - `py -3 tests/smoke_test.py`
  - `py -3 tests/role_matrix_test.py`
- Container stack (after `.env` setup):
  - `docker compose up -d --build`

## Notes

- The current app remains fully operational on SQLite while you migrate incrementally.
- PostgreSQL schema bootstrap remains backward-compatible via `SCHEMA`; versioned SQL migrations are now applied from `migrations/postgres`.


