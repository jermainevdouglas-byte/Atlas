# ====================================================================
# ATLAS DOCKER - QUICK START GUIDE (Windows)
# ====================================================================
# TL;DR - Get AtlasBahamas running in 5 minutes
# ====================================================================

## PREREQUISITES
- Docker Desktop for Windows installed and running
- D:\AtlasBahamas\atlasbahamas\ATLAS1\ as project directory
- D:\Storage directory (will be created if missing)


## STEP 1: PREPARE (.env file)
```powershell
cd D:\AtlasBahamas\atlasbahamas\ATLAS1
Copy-Item ".env.example" ".env" -Force
```

Use `.env.example` as the canonical template. Older `.env.production*` files are legacy references.

Edit `.env` and replace these placeholders (minimum required):
- `SECRET_KEY=REPLACE_WITH_64PLUS_CHAR_RANDOM_SECRET` → Use any 64+ character string
- `POSTGRES_PASSWORD=REPLACE_WITH_STRONG_DB_PASSWORD` → Use a strong password
- Update `POSTGRES_DSN` to match the password

Example:
```
SECRET_KEY=abc123def456ghi789jkl012mno345pqr789xyz!@#$%^&*abcdefghijklmnop
POSTGRES_PASSWORD=MyStrongPassword123!
POSTGRES_DSN=postgresql://atlasbahamas:MyStrongPassword123!@postgres:5432/atlasbahamas
```


## STEP 2: CREATE STORAGE DIRECTORY
```powershell
if (-not (Test-Path "D:\Storage")) {
    New-Item -ItemType Directory -Path "D:\Storage" -Force
}
```


## STEP 3: BUILD & START
```powershell
docker compose up -d --build
```

Wait ~40 seconds for all services to initialize.


## STEP 4: VERIFY (Quick test)
```powershell
# Check all containers running
docker compose ps

# Test home page
curl http://localhost/

# If you see HTML, you're done!
```


## SUCCESS INDICATORS
- All 4 containers showing "Up (healthy)" or "Up X seconds"
- Home page loads at http://localhost/
- No container restarts happening


## COMMON QUICK FIXES

**Containers won't start?**
```powershell
docker compose logs --tail=50 atlasbahamas_app
```

**Port 80 already in use?**
```powershell
netstat -ano | findstr :80
# Stop the process or change port in docker-compose.yml
```

**Files not persisting to D:\Storage?**
```powershell
# Make sure Docker has access to D:\
# Docker Desktop → Settings → Resources → File Sharing → Add D:\
```

**Database connection error?**
```powershell
# Wait 30+ seconds (Postgres needs time)
docker compose logs postgres | tail -20
```


## NEXT STEPS
- Login test: Navigate to login page (depends on your app routes)
- Database test: Check VALIDATION_CHECKLIST.md Section 5
- For production setup: See .env file security notes


## ACCESS
- **App**: http://localhost/
- **PostgreSQL**: localhost:5432 (internal only, not from host)
- **Redis**: localhost:6379 (internal only)
- **Storage**: D:\Storage (maps to /app/storage in container)


## STOP / RESTART
```powershell
# Stop all services
docker compose stop

# Start again
docker compose start

# Restart one service
docker compose restart atlasbahamas_app

# View logs
docker compose logs -f atlasbahamas_app
```


## FULL RUNBOOK
For detailed instructions, see: RUNBOOK_WINDOWS.ps1
For validation checklist, see: VALIDATION_CHECKLIST.md
For troubleshooting, see: TROUBLESHOOTING_WINDOWS.md



