# Render Deployment Notes (2026-02-19)

This repo now deploys as a Flask web service with:
- managed Redis (`atlasbahamas-redis`)
- managed persistent disk mounted at `/var/data`
- SQLite runtime database at `/var/data/atlasbahamas.sqlite`

## Blueprint files

- `render.yaml`
  - one `web` service (`atlasbahamas-web`)
  - one `redis` service (`atlasbahamas-redis`)
  - secure defaults (`PROD_MODE=1`, `ENFORCE_HTTPS=1`, secure cookies, host allowlist)
  - `SEED_DEMO_USERS=0` for production
  - generated `SECRET_KEY`
- `.env.production`
  - mirror of production env vars for local review
  - no committed real secret values

## Go-live sequence

1. Push repository updates to GitHub `main`.
2. In Render, deploy from `render.yaml` Blueprint.
3. In Render dashboard, verify these env vars are present and non-placeholder:
   - `SECRET_KEY`
   - `REDIS_URL` (auto from managed Redis)
   - `ALLOWED_HOSTS`
   - `CSRF_TRUSTED_HOSTS`
4. Confirm health endpoint:
   - `GET /health` returns `{"ok": true, "db": true}` and `redis: true/null`.
5. Open home page and validate role flows:
   - tenant door -> login -> tenant dashboard
   - landlord door -> login -> landlord dashboard
6. Run post-deploy workflow checks:
   - tenant can submit payment and maintenance request
   - landlord can update payment/maintenance statuses

## Notes

- SQLite on Render is acceptable for demo launch with a single web instance and persistent disk.
- If you scale horizontally, migrate to PostgreSQL and centralize workflow state.
