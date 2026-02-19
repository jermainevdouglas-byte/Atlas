# ====================================================================
# POST-DEPLOYMENT VALIDATION CHECKLIST
# ====================================================================
# Run this checklist after: docker compose up -d --build
# Expected completion time: ~5 minutes
# ====================================================================

## SECTION 1: CONTAINER STARTUP
- [ ] All containers are running: `docker compose ps`
  - [ ] atlas_app: Up
  - [ ] postgres: Up (healthy)
  - [ ] redis: Up (healthy)
  - [ ] nginx: Up (healthy)

- [ ] No containers in "restarting" or "exited" state
- [ ] Health checks are passing (green status in ps output)
- [ ] Logs show no critical errors: `docker compose logs`


## SECTION 2: PORT ACCESSIBILITY
- [ ] Port 80 is responding: `curl http://localhost/`
- [ ] Port 5432 (PostgreSQL) is isolated (not exposed to host, internal only)
- [ ] Port 6379 (Redis) is isolated (internal only, but exposed for testing)
- [ ] No port conflicts on Windows host:
  ```powershell
  netstat -ano | findstr :80
  netstat -ano | findstr :443
  ```


## SECTION 3: APP HOME PAGE TEST
- [ ] HTTP GET `http://localhost/` returns 200 OK
- [ ] Home page HTML renders (not 500 error)
- [ ] Expected content visible (check in browser)
- [ ] No import errors in logs: `docker compose logs atlas_app`


## SECTION 4: LOGIN PAGE TEST
- [ ] Navigate to login endpoint (exact URL depends on your app)
- [ ] Login form loads without errors
- [ ] CSRF token is present in form
- [ ] No database errors in logs


## SECTION 5: DATABASE CONNECTION TEST
- [ ] PostgreSQL container is healthy:
  ```bash
  docker compose exec -T postgres psql -U atlas -d atlas -c "SELECT 1;"
  ```
- [ ] Expected output: `?column?` = `1`
- [ ] No connection timeout errors
- [ ] App can read/write to database (check logs for DB queries)


## SECTION 6: REDIS CONNECTION TEST
- [ ] Redis container is healthy:
  ```bash
  docker compose exec -T redis redis-cli PING
  ```
- [ ] Expected output: `PONG`
- [ ] Session storage works (login and check Redis keys):
  ```bash
  docker compose exec -T redis redis-cli KEYS "atlas:session:*"
  ```
- [ ] At least 1 session key appears after login


## SECTION 7: STORAGE PERSISTENCE TEST
- [ ] Host storage directory exists and is writable: `D:\Storage`
- [ ] Storage is mounted inside container:
  ```bash
  docker compose exec atlas_app ls -la /app/storage/
  ```
- [ ] Files created inside container appear on host:
  ```bash
  docker compose exec atlas_app touch /app/storage/test_file.txt
  # Then check: ls D:\Storage\test_file.txt
  ```


## SECTION 8: ENVIRONMENT VARIABLES TEST
- [ ] All required env vars are set:
  ```bash
  docker compose exec atlas_app env | grep -E "POSTGRES|REDIS|SECRET_KEY"
  ```
- [ ] No REPLACE_* placeholders remain (e.g., SECRET_KEY should not contain "REPLACE")
- [ ] PROD_MODE=1 is set
- [ ] DATABASE_PATH is correct: `/app/data/atlas.sqlite`


## SECTION 9: LOGGING TEST
- [ ] Logs are being written to container stdout:
  ```bash
  docker compose logs --tail=100 atlas_app
  ```
- [ ] No Python import errors (e.g., module not found)
- [ ] No Gunicorn startup errors
- [ ] App log entries appear in logs (request logs, etc.)


## SECTION 10: NGINX PROXY TEST
- [ ] Nginx is passing requests correctly:
  ```bash
  curl -v http://localhost/ | grep X-Forwarded
  ```
- [ ] Expected headers present:
  - [ ] `X-Forwarded-For` (client IP)
  - [ ] `X-Forwarded-Proto` (scheme: http)
  - [ ] `X-Forwarded-Host` (host header)
- [ ] No nginx errors: `docker compose logs nginx | grep error`


## SECTION 11: SECURITY HEADERS TEST
- [ ] Response headers include security controls:
  ```bash
  curl -i http://localhost/ | grep -i "Content-Security\|X-Frame\|X-Content-Type"
  ```
- [ ] Expected headers depend on app configuration (check .env settings)


## SECTION 12: RESTART RESILIENCE TEST
- [ ] Stop one service and verify restart:
  ```bash
  docker compose stop atlas_app
  # Wait 5 seconds
  docker compose ps atlas_app  # Should show restarting/up
  ```
- [ ] Data persists after restart
- [ ] No data corruption in database after restart


## SECTION 13: RESOURCE USAGE TEST
- [ ] Docker system disk usage is reasonable:
  ```bash
  docker system df
  ```
  - [ ] Images: < 2GB
  - [ ] Containers: < 500MB
  - [ ] Volumes: < 1GB
- [ ] Memory usage is stable (not continuously growing):
  ```bash
  docker compose stats --no-stream
  ```


## SECTION 14: RATE LIMITING / REDIS SESSION TEST
- [ ] Create a login session and verify Redis:
  ```bash
  # After login via browser:
  docker compose exec -T redis redis-cli KEYS "atlas:session:*"
  # Should show at least one key
  ```
- [ ] Rate limiting works (if enabled):
  ```bash
  # Perform rapid failed logins
  for i in {1..10}; do curl -X POST http://localhost/login -d "bad credentials"; done
  # Check logs for rate limit warnings
  docker compose logs atlas_app | grep -i "rate"
  ```


## SECTION 15: CLEAN SHUTDOWN TEST
- [ ] Graceful shutdown works:
  ```bash
  docker compose down
  docker compose ps  # Should show all containers exited
  ```
- [ ] Start again and verify all services recover:
  ```bash
  docker compose up -d
  docker compose ps  # All should be running after ~30s
  ```


## TROUBLESHOOTING QUICK REFERENCE

If Home Page Test (Section 3) FAILS:
- Check app logs: `docker compose logs atlas_app --tail=100`
- Look for: ImportError, ModuleNotFoundError, AttributeError
- Verify wsgi.py exists: `docker compose exec atlas_app ls -la wsgi.py`
- Verify wsgi_adapter.py exists: `docker compose exec atlas_app ls -la atlas_app/wsgi_adapter.py`

If Login Test (Section 4) FAILS:
- Check PostgreSQL connection: Follow Section 5 steps
- Check Redis connection: Follow Section 6 steps
- Verify POSTGRES_DSN is correct in .env
- Check app startup logs: `docker compose logs atlas_app | head -50`

If Database Test (Section 5) FAILS:
- Wait 15 seconds for Postgres to initialize fully
- Check Postgres logs: `docker compose logs postgres --tail=50`
- Verify POSTGRES_PASSWORD in .env matches compose env
- Manually connect: `docker compose exec postgres psql -U atlas -c "SELECT 1;"`

If Redis Test (Section 6) FAILS:
- Wait 10 seconds for Redis to start
- Check Redis logs: `docker compose logs redis --tail=50`
- Manually test: `docker compose exec redis redis-cli PING`
- Verify REDIS_URL in app .env: `redis://redis:6379/0`

If Storage Test (Section 7) FAILS:
- Verify D:\Storage directory exists on Windows host
- Check permissions: Windows user can read/write D:\Storage
- Restart Docker Desktop
- Verify mount in compose: `docker compose config | grep -A5 volumes`

If Logs Test (Section 9) FAILS:
- Check Docker daemon logs (Windows):
  ```powershell
  Get-Content "$env:LOCALAPPDATA\Docker\log\vm\dockerd.log" -Tail 100
  ```
- Check Docker Desktop application tab: Settings > Troubleshoot > Logs

## FINAL VALIDATION
- [ ] All 15 sections passed
- [ ] Home page loads without errors
- [ ] Can login (if applicable)
- [ ] Storage persists to D:\Storage
- [ ] Containers restart automatically on failure
- [ ] Logs are clean (no error spam)
- [ ] Ready for production


## SIGN-OFF
- Validated by: ___________________
- Date: ___________________
- Build version: ___________________
- Notes: _______________________________________________________________________
