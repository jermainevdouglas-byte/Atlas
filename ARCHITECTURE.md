# Atlas Architecture (Modularized Runtime)

This project runs in a single active framework: modular `BaseHTTPRequestHandler` (Option A).

## Active runtime

- `server.py`
  - Canonical entrypoint for local/dev and compatibility scripts.
  - Calls `atlas_app.core.main()`.

- `wsgi.py`
  - Production WSGI entrypoint for Gunicorn.
  - Uses `atlas_app.wsgi_adapter.WSGIHandler` against the same handler stack.

- `atlas_app/http_handler.py`
  - Composed request handler `H` built from modular mixins in `atlas_app/handlers/`.

- `atlas_app/core.py`
  - Runtime configuration, security, DB access, bootstrap, migrations, and business logic.

## Non-active scaffold

- `app.py`
  - Explicit Flask scaffold only.
  - Not used by Docker/Gunicorn deployment.
  - Kept for future route-by-route migration experiments, but disabled for real auth/runtime behavior.

## Handler modules

- `atlas_app/handlers/base.py`: request lifecycle, dispatch, static serving, role checks
- `atlas_app/handlers/auth.py`: login/register/logout/reset/profile
- `atlas_app/handlers/public.py`: uploads/api/public actions/search/favorites/inquiry/application
- `atlas_app/handlers/messages.py`: thread views/create/send
- `atlas_app/handlers/notifications.py`: alerts, preferences, onboarding
- `atlas_app/handlers/tenant.py`: tenant GET/POST flows
- `atlas_app/handlers/landlord.py`: landlord GET/POST/exports
- `atlas_app/handlers/manager.py`: manager GET/POST/exports
- `atlas_app/handlers/admin.py`: admin GET/POST/audit/submissions
- `atlas_app/handlers/property_manager.py`: unified property-manager dashboard/search

## Database + migrations

- `db.py` remains the compatibility layer (`SQLite` default, `PostgreSQL` when `POSTGRES_DSN` is set).
- `atlas_app/core.py` now applies versioned PostgreSQL SQL migrations from:
  - `migrations/postgres/*.sql` (ordered by numeric prefix)
- `schema_meta` tracks `schema_version` across backends.

## Run commands

- `py -3 server.py`
- `py -3 -m atlas_app`
- `gunicorn wsgi:app`

## Verification

- `py -3 tests/smoke_test.py`
- `py -3 tests/role_matrix_test.py`
- `py -3 -m compileall atlas_app`

