# ====================================================================
# Atlas Docker Compose - Windows PowerShell Runbook
# ====================================================================
# Location: D:\AtlasSimple\atlas\ATLAS1\
# Prerequisites: Docker Desktop for Windows, PowerShell Core or Windows PowerShell
# ====================================================================

# ---- STEP 1: Prepare Environment ----
# Run this once before first deployment:

# 1.1 Navigate to project directory
cd D:\AtlasSimple\atlas\ATLAS1

# 1.2 Create .env from production template
# Copy .env.production to .env and edit with actual secrets
Copy-Item -Path ".env.production" -Destination ".env" -Force
# Edit .env file to replace REPLACE_* placeholders with real values
# notepad .env

# 1.3 Create storage directory on host (if not exists)
if (-not (Test-Path "D:\Storage")) {
    New-Item -ItemType Directory -Path "D:\Storage" -Force
    Write-Host "Created D:\Storage directory" -ForegroundColor Green
}

# 1.4 Create SSL directory for future HTTPS (optional)
if (-not (Test-Path ".\ssl")) {
    New-Item -ItemType Directory -Path ".\ssl" -Force
    Write-Host "Created ./ssl directory for SSL certificates" -ForegroundColor Green
}


# ====================================================================
# ---- STEP 2: Build and Deploy ----
# ====================================================================

# 2.1 Build images and start all services (first time)
Write-Host "Building images and starting services..." -ForegroundColor Cyan
docker compose up -d --build

# Wait for services to initialize
Write-Host "Waiting 30 seconds for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 30


# ====================================================================
# ---- STEP 3: Verify Deployment ----
# ====================================================================

# 3.1 Check all containers are running
Write-Host "`n=== Container Status ===" -ForegroundColor Cyan
docker compose ps

# 3.2 Check service health
Write-Host "`n=== Service Health Status ===" -ForegroundColor Cyan
docker compose ps --format "table {{.Service}}\t{{.Status}}"


# ====================================================================
# ---- STEP 4: View Logs ----
# ====================================================================

# View all service logs
Write-Host "`n=== Recent Logs (All Services) ===" -ForegroundColor Cyan
docker compose logs --tail=50

# View specific service logs
Write-Host "`n=== Atlas App Logs ===" -ForegroundColor Cyan
docker compose logs --tail=100 atlas_app

Write-Host "`n=== PostgreSQL Logs ===" -ForegroundColor Cyan
docker compose logs --tail=50 postgres

Write-Host "`n=== Redis Logs ===" -ForegroundColor Cyan
docker compose logs --tail=50 redis

Write-Host "`n=== Nginx Logs ===" -ForegroundColor Cyan
docker compose logs --tail=50 nginx

# Stream logs in real-time (press Ctrl+C to stop)
# docker compose logs -f atlas_app


# ====================================================================
# ---- STEP 5: Health Verification ====
# ====================================================================

# 5.1 Test app health endpoint
Write-Host "`n=== Testing App Health ===" -ForegroundColor Cyan
$healthCheck = Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing -ErrorAction SilentlyContinue
if ($healthCheck.StatusCode -eq 200) {
    Write-Host "✓ App is healthy (HTTP 200)" -ForegroundColor Green
} else {
    Write-Host "✗ App health check failed" -ForegroundColor Red
}

# 5.2 Test app home page
Write-Host "`n=== Testing App Home Page ===" -ForegroundColor Cyan
$homeCheck = Invoke-WebRequest -Uri "http://localhost/" -UseBasicParsing -ErrorAction SilentlyContinue
if ($homeCheck.StatusCode -eq 200) {
    Write-Host "✓ App home page loaded (HTTP 200)" -ForegroundColor Green
    Write-Host "Response preview: $($homeCheck.Content.Substring(0, 100))..." -ForegroundColor Gray
} else {
    Write-Host "✗ App home page failed with HTTP $($homeCheck.StatusCode)" -ForegroundColor Red
}

# 5.3 Test database connection
Write-Host "`n=== Testing PostgreSQL Connection ===" -ForegroundColor Cyan
docker compose exec -T postgres psql -U atlas -d atlas -c "SELECT version();" 2>$null | Where-Object {$_}
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ PostgreSQL is accessible" -ForegroundColor Green
} else {
    Write-Host "✗ PostgreSQL connection failed" -ForegroundColor Red
}

# 5.4 Test Redis connection
Write-Host "`n=== Testing Redis Connection ===" -ForegroundColor Cyan
docker compose exec -T redis redis-cli PING 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Redis is accessible" -ForegroundColor Green
} else {
    Write-Host "✗ Redis connection failed" -ForegroundColor Red
}

# 5.5 Check volume mounts
Write-Host "`n=== Checking Volume Mounts ===" -ForegroundColor Cyan
docker compose exec -T atlas_app ls -la /app/data/ 2>$null
docker compose exec -T atlas_app ls -la /app/storage/ 2>$null


# ====================================================================
# ---- STEP 6: Common Operations ====
# ====================================================================

# Restart a specific service
# docker compose restart atlas_app

# Restart all services
# docker compose restart

# Stop all services (data persists)
# docker compose stop

# Start services (if already created)
# docker compose start

# Stop and remove all containers (volumes persist)
# docker compose down

# Full cleanup (removes containers, volumes, networks - DATA LOSS)
# docker compose down -v

# Rebuild a single service
# docker compose build --no-cache atlas_app
# docker compose up -d atlas_app

# Execute command in running container
# docker compose exec atlas_app python -c "import atlas_app.core as core; print(core.__version__)"

# View resource usage
# docker compose stats

# Check network connectivity
# docker compose exec atlas_app ping redis
# docker compose exec atlas_app ping postgres


# ====================================================================
# ---- STEP 7: Database Initialization (if needed) ====
# ====================================================================

# Run database migrations (adjust command to match your app)
# docker compose exec atlas_app python db.py migrate

# Check database status
# docker compose exec -T postgres psql -U atlas -d atlas -c "\dt"

# Backup PostgreSQL
# docker compose exec -T postgres pg_dump -U atlas -d atlas > backup_atlas_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql


# ====================================================================
# ---- STEP 8: Troubleshooting ====
# ====================================================================

# Check Docker system resources
# docker system df

# Inspect a specific container
# docker inspect atlas_app

# View networks
# docker network ls
# docker network inspect atlas_network

# Check image versions
# docker images | grep atlas

# Check for port conflicts
# netstat -ano | findstr :80
# netstat -ano | findstr :443
# netstat -ano | findstr :5432
# netstat -ano | findstr :6379

# Clean up unused resources
# docker system prune -a --volumes


# ====================================================================
# ---- SUMMARY ====
# ====================================================================

Write-Host "`n`n" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ATLAS DOCKER DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access Atlas at:" -ForegroundColor Cyan
Write-Host "  HTTP:  http://localhost/" -ForegroundColor Yellow
Write-Host "  Port:  80 (via nginx reverse proxy)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Services running:" -ForegroundColor Cyan
Write-Host "  - atlas_app (Gunicorn on port 5000)" -ForegroundColor Yellow
Write-Host "  - postgres (port 5432, internal only)" -ForegroundColor Yellow
Write-Host "  - redis (port 6379, internal only)" -ForegroundColor Yellow
Write-Host "  - nginx (port 80/443)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Storage paths:" -ForegroundColor Cyan
Write-Host "  - Host:      D:\Storage" -ForegroundColor Yellow
Write-Host "  - Container: /app/storage" -ForegroundColor Yellow
Write-Host ""
Write-Host "Logs:" -ForegroundColor Cyan
Write-Host "  - Run: docker compose logs -f" -ForegroundColor Yellow
Write-Host ""
Write-Host "Stop services:" -ForegroundColor Cyan
Write-Host "  - Run: docker compose stop" -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
