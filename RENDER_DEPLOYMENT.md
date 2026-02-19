# Render Deployment Notes

This project is now prepared for Render with Docker + managed PostgreSQL + managed Redis.

## Included production files

- `Dockerfile`
  - Uses dynamic Render port (`$PORT`)
  - Healthcheck points to `/health`
- `render.yaml`
  - Defines:
    - `atlas-web` (web service)
    - `atlas-postgres` (managed PostgreSQL)
    - `atlas-redis` (managed Redis)
  - Sets production-safe defaults and mount path `/var/data`
- `.env.production`
  - Render-ready template (no real secrets committed)

## First deploy checklist

1. In Render, create from Blueprint using `render.yaml`.
2. Set required secret env vars in Render dashboard:
   - `SECRET_KEY`
   - `BOOTSTRAP_ADMIN_PHONE`
   - `BOOTSTRAP_ADMIN_EMAIL`
   - `BOOTSTRAP_ADMIN_USERNAME`
   - `BOOTSTRAP_ADMIN_PASSWORD`
3. Confirm web health endpoint: `/health`.
4. Log in as bootstrap admin and rotate credentials.

## Storage

- Persistent disk mount: `/var/data`
- App paths:
  - `DATABASE_PATH=/var/data/atlas.sqlite` (fallback only)
  - `UPLOAD_DIR=/var/data/uploads`
  - `LOG_DIR=/var/data/logs`
  - `BACKUP_DIR=/var/data/backups`

## Domain / host rules

- `ALLOWED_HOSTS` and `CSRF_TRUSTED_HOSTS` include `.onrender.com`
- Suffix host matching is supported in app code (for Render hostnames).

