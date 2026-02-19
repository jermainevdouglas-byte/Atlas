# ====================================================================
# WINDOWS DOCKER TROUBLESHOOTING GUIDE
# ====================================================================
# Common issues when running Atlas on Docker Desktop for Windows
# ====================================================================

## ISSUE 1: Docker Daemon Won't Start

### Symptoms:
- "Cannot connect to Docker daemon"
- "Docker Desktop is starting..."
- PowerShell commands hang

### Solutions:

**1.1 Restart Docker Desktop:**
```powershell
# Kill all Docker processes
Stop-Process -Name "Docker Desktop" -Force
Get-Process | Where-Object {$_.ProcessName -like "*docker*"} | Stop-Process -Force

# Wait 10 seconds
Start-Sleep -Seconds 10

# Restart Docker Desktop
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# Wait for startup
Start-Sleep -Seconds 30

# Verify daemon is running
docker ps
```

**1.2 Check Docker Desktop logs:**
```powershell
# View live logs (Windows 10/11)
Get-Content "$env:LOCALAPPDATA\Docker\log\vm\dockerd.log" -Tail 100 -Wait

# Or check in Docker Desktop UI: Settings > Troubleshoot > Logs
```

**1.3 Increase Docker memory/CPU allocation:**
- Open Docker Desktop
- Right-click tray icon → Settings
- Go to Resources tab
- Increase:
  - Memory: 4GB minimum (8GB+ recommended)
  - CPUs: 4 minimum
  - Swap: 2GB
- Click "Apply & Restart"

**1.4 Reinstall Docker Desktop:**
```powershell
# Uninstall
Add-AppxPackage -Path "\\server\shares\Docker.Desktop.appxbundle"
# Or use Programs & Features in Control Panel

# Reinstall from: https://docs.docker.com/desktop/install/windows-install/
```


## ISSUE 2: Port Already in Use

### Symptoms:
- `docker compose up` fails with "port 80 already in use"
- "bind: address already in use"
- "Port 5432 is already allocated"

### Solutions:

**2.1 Find process using the port:**
```powershell
# Check what's using port 80
netstat -ano | findstr :80

# Find process name by PID (e.g., PID 1234)
Get-Process -Id 1234 | Select-Object ProcessName, Id

# Common culprits: IIS, Apache, Skype, OneDrive, Windows services
```

**2.2 Stop the conflicting service:**
```powershell
# Stop IIS (common Windows service)
Stop-Service -Name W3SVC
Stop-Service -Name WAS
Stop-Service -Name IISADMIN

# Disable for auto-start
Set-Service -Name W3SVC -StartupType Disabled

# Or kill by process name
Stop-Process -Name "iisexpress" -Force
```

**2.3 Use different ports in docker-compose.yml:**
```yaml
# Change in docker-compose.yml:
nginx:
  ports:
    - "8080:80"      # Use 8080 instead of 80
    - "8443:443"     # Use 8443 instead of 443
```

**2.4 Restart Docker to free ports:**
```powershell
docker compose down
# Wait 5 seconds
docker compose up -d
```


## ISSUE 3: Containers Exiting Immediately

### Symptoms:
- `docker compose ps` shows "Exited (1)" or "Exited (127)"
- Container exits within 1-2 seconds of starting
- No error in compose output

### Solutions:

**3.1 Check container exit codes:**
```powershell
# View exit reason
docker compose logs atlas_app --tail=50

# Exit code 1 = general error (check logs above)
# Exit code 127 = command not found (check COPY paths in Dockerfile)
# Exit code 137 = OOM kill (increase Docker memory)
```

**3.2 Common exit code 127 causes (file not found):**
```powershell
# Verify wsgi.py exists in container
docker compose exec atlas_app ls -la wsgi.py

# Verify all COPY paths in Dockerfile exist on host
# Check: docker build . --verbose

# Rebuild without cache
docker compose build --no-cache atlas_app
docker compose up -d
```

**3.3 Check app startup errors:**
```powershell
# View full startup logs
docker compose logs atlas_app

# Look for:
# - ImportError: No module named 'X'
# - ModuleNotFoundError
# - SyntaxError
# - AttributeError in wsgi.py or wsgi_adapter.py
```

**3.4 If PostgreSQL exiting:**
```powershell
docker compose logs postgres --tail=50

# Common Postgres issues:
# - "POSTGRES_PASSWORD is not set"
# - Permission denied on data volume
# - Incompatible data format from old version
```

**Fix by clearing Postgres data:**
```powershell
# WARNING: This deletes database content
docker compose down -v  # -v removes volumes
docker compose up -d postgres
```


## ISSUE 4: Volume Mounts Not Working

### Symptoms:
- `D:\Storage` changes don't appear in container
- Container changes don't appear in `D:\Storage`
- "Cannot find a matching path"
- Files appear in container but not on host

### Solutions:

**4.1 Verify Windows path format in docker-compose.yml:**
```yaml
# CORRECT - use forward slashes OR backslashes
volumes:
  - D:\Storage:/app/storage        # This works
  - D:/Storage:/app/storage        # This also works
  - ./relative/path:/app/path      # Relative paths work too

# INCORRECT
  - D:\\Storage:/app/storage       # Double backslash fails
  - $env:Storage:/app/storage      # Don't use PowerShell variables
```

**4.2 Check Docker Desktop mount settings:**
- Docker Desktop UI → Settings → Resources → File Sharing
- Verify `D:` drive is listed
- If not, click "+" and add `D:\`
- Click "Apply & Restart"

**4.3 Check Windows file permissions:**
```powershell
# Ensure your user can read/write D:\Storage
icacls D:\Storage /grant $env:USERNAME:(OI)(CI)F

# Verify
Get-Acl D:\Storage | Format-List
```

**4.4 Verify mount inside container:**
```powershell
# Check if mount is visible
docker compose exec atlas_app mount | grep storage

# Or check directory
docker compose exec atlas_app ls -la /app/storage/

# Create test file and verify on host
docker compose exec atlas_app touch /app/storage/test.txt
ls D:\Storage\test.txt  # Should exist
```

**4.5 Restart Docker daemon for mount refresh:**
```powershell
docker compose down
Stop-Process -Name "Docker Desktop" -Force
Start-Sleep -Seconds 10
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Sleep -Seconds 30
docker compose up -d
```


## ISSUE 5: Database Connection Refused

### Symptoms:
- "postgresql connection refused"
- "SQLALCHEMY_DATABASE_URI could not connect"
- "Password authentication failed"
- App logs show "no connection to server"

### Solutions:

**5.1 Verify Postgres container is running:**
```powershell
docker compose ps postgres

# Should show: STATUS = Up X seconds (healthy)
# If "Exited", check logs:
docker compose logs postgres --tail=50
```

**5.2 Check database credentials match:**
```powershell
# In .env file, verify:
# POSTGRES_USER=atlas
# POSTGRES_PASSWORD=REPLACE_WITH_STRONG...
# POSTGRES_DSN=postgresql://atlas:PASSWORD@postgres:5432/atlas

# PASSWORD in both lines must match exactly
```

**5.3 Test connection from app container:**
```powershell
# Test using psql inside container
docker compose exec postgres psql -U atlas -d atlas -c "SELECT version();"

# Expected: PostgreSQL 16.x...
```

**5.4 Test from app to Postgres:**
```powershell
# From atlas_app container
docker compose exec atlas_app python -c "
import psycopg
try:
    conn = psycopg.connect('postgresql://atlas:PASSWORD@postgres:5432/atlas')
    print('Connected to Postgres')
    conn.close()
except Exception as e:
    print(f'Connection failed: {e}')
"
# Replace PASSWORD with actual password from .env
```

**5.5 Wait longer for Postgres initialization:**
```powershell
# First start can take 30+ seconds
Start-Sleep -Seconds 60
docker compose ps  # Check health status

# If still not healthy, check log
docker compose logs postgres | tail -30
```


## ISSUE 6: Redis Connection Refused

### Symptoms:
- "redis connection refused"
- "Cannot connect to redis server"
- Sessions not persisting
- Rate limiting not working

### Solutions:

**6.1 Verify Redis is running:**
```powershell
docker compose ps redis

# Should show: Up X seconds (healthy)
```

**6.2 Test Redis connectivity:**
```powershell
# From host (if port exposed)
docker compose exec redis redis-cli PING
# Expected: PONG

# Or from app container
docker compose exec atlas_app python -c "
import redis
r = redis.Redis(host='redis', port=6379, db=0)
print(r.ping())
"
# Expected: True
```

**6.3 Check REDIS_URL format in .env:**
```powershell
# Correct format
REDIS_URL=redis://redis:6379/0

# If password is set
REDIS_URL=redis://:password@redis:6379/0

# Docker DNS automatically resolves 'redis' to container IP
```

**6.4 Wait for Redis startup:**
```powershell
# Redis startup is usually fast, but check
docker compose logs redis --tail=20
```


## ISSUE 7: App Crashes with ImportError

### Symptoms:
- "ModuleNotFoundError: No module named 'X'"
- "ImportError: cannot import name 'X'"
- App exits with status code 1

### Solutions:

**7.1 Check requirements.txt is copied:**
```powershell
# Verify in Dockerfile COPY line exists
docker compose exec atlas_app cat requirements.txt

# Check pip installed packages
docker compose exec atlas_app pip list | grep -i gunicorn
```

**7.2 Verify all imports in Python files:**
```powershell
# Check wsgi.py
docker compose exec atlas_app python wsgi.py  # This will hang, press Ctrl+C

# Or check for syntax errors
docker compose exec atlas_app python -m py_compile wsgi.py
docker compose exec atlas_app python -m py_compile atlas_app/wsgi_adapter.py
```

**7.3 Rebuild without cache (fresh install):**
```powershell
docker compose down
docker compose build --no-cache atlas_app
docker compose up -d --build
```

**7.4 Check if requirements match app code:**
```powershell
# Verify gunicorn version
docker compose exec atlas_app pip show gunicorn

# Verify Flask version (if app uses Flask)
docker compose exec atlas_app pip show Flask

# Check for missing dependencies
docker compose logs atlas_app | grep -i "error\|failed\|not found"
```


## ISSUE 8: Memory Usage Constantly Growing (Memory Leak)

### Symptoms:
- `docker compose stats` shows memory increasing continuously
- App slows down over time
- Docker Desktop shows high memory usage

### Solutions:

**8.1 Check current memory usage:**
```powershell
docker compose stats --no-stream

# Look at memory usage for atlas_app
# If > 2GB, likely a leak
```

**8.2 Increase Docker Desktop memory limit:**
```powershell
# Docker Desktop UI → Settings → Resources
# Set Memory to 8GB or higher
# Click Apply & Restart
```

**8.3 Check app logs for memory-heavy operations:**
```powershell
docker compose logs atlas_app --tail=100
# Look for: large file uploads, unfinished loops, unclosed connections
```

**8.4 Restart app service to free memory:**
```powershell
docker compose restart atlas_app

# Monitor after restart
docker compose stats --no-stream atlas_app
```

**8.5 Check for application memory leaks:**
```powershell
# Profile Python memory (if app supports it)
docker compose exec atlas_app python -m tracemalloc
# This depends on app implementation
```


## ISSUE 9: Windows Firewall Blocking Docker

### Symptoms:
- App unreachable from localhost
- "Cannot reach server" in browser
- App works, but port not accessible

### Solutions:

**9.1 Allow Docker through Windows Firewall:**
```powershell
# Run as Administrator:

# Check Docker is allowed
Get-NetFirewallProfile -Name Public | Select-Object -ExpandProperty Enabled

# If needed, disable firewall temporarily (NOT recommended for production)
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $False

# Or add Docker rule
New-NetFirewallRule -DisplayName "Docker" -Direction Inbound -Action Allow -Program "C:\Program Files\Docker\Docker\Docker.exe"

# Re-enable firewall
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $True
```

**9.2 Test from localhost:**
```powershell
# Use 127.0.0.1 explicitly
curl http://127.0.0.1/
curl http://127.0.0.1:80/

# If works with 127.0.0.1 but not localhost, it's a DNS issue
# Add to hosts file:
# 127.0.0.1 localhost
# File: C:\Windows\System32\drivers\etc\hosts (edit as Admin)
```


## ISSUE 10: Nginx Shows "502 Bad Gateway"

### Symptoms:
- Browser shows "502 Bad Gateway"
- `curl http://localhost/` returns 502
- App container is running but unreachable via nginx

### Solutions:

**10.1 Check if app is responding:**
```powershell
# Test app directly (bypass nginx)
docker compose port atlas_app 5000  # Shows mapped port

# Test app directly
curl http://localhost:5000/
# Should work if app is healthy

# If this fails, go to ISSUE 3 or 7 above
```

**10.2 Check nginx configuration:**
```powershell
# Verify nginx.conf syntax
docker compose exec nginx nginx -t
# Expected: "syntax is ok"

# View nginx.conf
docker compose exec nginx cat /etc/nginx/nginx.conf
```

**10.3 Verify DNS resolution in nginx container:**
```powershell
# Can nginx resolve 'atlas_app' hostname?
docker compose exec nginx nslookup atlas_app

# If "nslookup: command not found", install it
# Or check network connectivity
docker compose exec nginx ping atlas_app
```

**10.4 Check network connectivity:**
```powershell
# Verify containers are on same network
docker network ls
docker network inspect atlas_network

# Both atlas_app and nginx should be listed
# If not, recreate network:
docker compose down
docker network rm atlas_network  # Only if not auto-removed
docker compose up -d
```

**10.5 Check nginx logs:**
```powershell
docker compose logs nginx --tail=50

# Look for: upstream timed out, connection refused, no servers
```

**10.6 Increase proxy timeout in nginx.conf:**
```nginx
# In nginx.conf, inside location block:
proxy_connect_timeout 60s;
proxy_send_timeout 60s;
proxy_read_timeout 60s;
```


## ISSUE 11: Slow Container Startup

### Symptoms:
- Takes > 2 minutes to reach "healthy" status
- Health checks timing out
- Containers repeatedly restart

### Solutions:

**11.1 Increase health check timeouts:**
```yaml
# In docker-compose.yml, increase retries:
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5000/"]
  interval: 10s
  timeout: 10s        # Increase from 5s to 10s
  retries: 10         # Increase from 3 to 10
  start_period: 60s   # Increase from 40s to 60s
```

**11.2 Check system resources:**
```powershell
# Is Docker running low on CPU/memory?
docker compose stats --no-stream

# If high usage, increase Docker Desktop resources:
# Settings → Resources → Memory/CPUs
```

**11.3 Profile startup:**
```powershell
# Measure time to health
$start = Get-Date
docker compose up -d
while ((docker compose ps | grep atlas_app) -notmatch "healthy") {
    Start-Sleep -Seconds 2
}
$elapsed = (Get-Date) - $start
Write-Host "Startup time: $($elapsed.TotalSeconds) seconds"
```


## ISSUE 12: Windows Path Issues in Docker

### Symptoms:
- "cannot find specified path"
- Mount paths not recognized
- Path separators causing errors

### Solutions:

**12.1 Use forward slashes consistently:**
```yaml
# DO use forward slashes or absolute Windows paths:
volumes:
  - D:/Storage:/app/storage           # Forward slashes
  - D:\Storage:/app/storage           # Windows backslashes (also works)
  - ./relative:/app/relative          # Relative paths

# DON'T use:
  - $env:SystemRoot/Docker            # Don't use PowerShell variables
  - /D/Storage:/app/storage           # Don't use Unix-style /D/
```

**12.2 Convert paths properly in docker-compose.yml:**
```bash
# Generate compose file with correct paths
cd D:\AtlasSimple\atlas\ATLAS1

# Create .env with proper paths
Add-Content -Path ".env" -Value "STORAGE_PATH=D:/Storage"  # Forward slashes

# Or edit docker-compose.yml manually to use:
- ${STORAGE_PATH}:/app/storage  # Reads from .env
```


## ISSUE 13: Docker Daemon Disk Full

### Symptoms:
- "no space left on device"
- "Error response from daemon"
- Containers fail to start
- docker system df shows 100% usage

### Solutions:

**13.1 Check disk usage:**
```powershell
docker system df

# Shows usage for images, containers, volumes, build cache
```

**13.2 Clean up unused resources:**
```powershell
# Remove unused images (safe)
docker image prune -a --force

# Remove unused containers
docker container prune -f

# Remove unused volumes (CAUTION: deletes data)
docker volume prune -f

# Remove all unused resources at once
docker system prune -a --volumes -f
```

**13.3 Check disk space on host:**
```powershell
Get-Volume | Where-Object {$_.DriveLetter -eq 'C'}
# Look at SizeRemaining - should be > 10GB

# If disk full, delete large files or add storage
```

**13.4 Relocate Docker data directory (advanced):**
```powershell
# Docker Desktop UI → Settings → Advanced
# Uncheck "Use the system default setting"
# Set "Disk image location" to a drive with more space
# Click "Apply"
```


## ISSUE 14: Cannot Access Container Filesystem

### Symptoms:
- "Error response from daemon"
- `docker compose exec` commands hang or error
- Cannot view files inside container

### Solutions:

**14.1 Check if container is running:**
```powershell
docker compose ps atlas_app
# Status must be "Up"

# If not running, start it
docker compose up -d atlas_app
```

**14.2 Use docker exec instead of compose:**
```powershell
# Try with container name directly
docker exec atlas_app ls /app

# Or get container ID first
$cid = docker ps --filter "name=atlas_app" -q
docker exec $cid ls /app
```

**14.3 Check Docker Desktop daemon:**
```powershell
# Restart Docker Desktop
Stop-Process -Name "Docker Desktop" -Force
Start-Sleep -Seconds 10
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Sleep -Seconds 30

# Try again
docker compose exec atlas_app pwd
```


## ISSUE 15: Nginx/PostgreSQL/Redis Show "Exited (0)"

### Symptoms:
- Service exits immediately after starting
- Status shows "Exited (0)" (successful exit, not an error)
- Services are not running

### Solutions:

**15.1 Understand exit code 0:**
```
Exit code 0 = Normal/Successful termination (but should keep running!)
This means the service started, did what it was told, then stopped.
For services, they should keep running (never exit).
```

**15.2 Check if healthcheck is causing exit:**
```powershell
# View compose file
docker compose config | grep -A5 healthcheck

# Healthcheck failure can cause restart loop
# Check logs for healthcheck failures
docker compose logs postgres | grep -i health
```

**15.3 For PostgreSQL specifically:**
```powershell
# PostgreSQL exits successfully after init if no persistent volume
docker compose logs postgres --tail=20

# Must have volume mount for data
# In docker-compose.yml, verify:
postgres:
  volumes:
    - postgres_data:/var/lib/postgresql/data  # This is required
```

**15.4 For Redis specifically:**
```powershell
# Redis should not exit on its own
docker compose logs redis --tail=20

# If no persistence issues, check command:
redis:
  command: ["redis-server", "--appendonly", "yes"]
  # Command should keep redis-server running
```


## WINDOWS-SPECIFIC ENVIRONMENT CHECK

Run this comprehensive diagnostic:

```powershell
# Comprehensive system check
Write-Host "=== DOCKER INSTALLATION ===" -ForegroundColor Cyan
docker --version
docker compose version

Write-Host "`n=== DOCKER DAEMON ===" -ForegroundColor Cyan
docker ps  # If this fails, daemon is not running

Write-Host "`n=== AVAILABLE RESOURCES ===" -ForegroundColor Cyan
$mem = Get-ComputerInfo -Property CsPhysicalMemory | Select-Object -ExpandProperty CsPhysicalMemory
Write-Host "System RAM: $($mem / 1GB) GB"

Get-Volume | Where-Object {$_.DriveLetter} | ForEach-Object {
    Write-Host "Drive $($_.DriveLetter): Used $($_.SizeUsed / 1GB) GB / Total $($_.Size / 1GB) GB"
}

Write-Host "`n=== DOCKER DESKTOP MEMORY ===" -ForegroundColor Cyan
Get-Process | Where-Object {$_.ProcessName -eq "Docker Desktop"} | Select-Object ProcessName, @{
    Name="Memory (MB)"
    Expression={$_.WorkingSet / 1MB -as [int]}
}

Write-Host "`n=== RUNNING CONTAINERS ===" -ForegroundColor Cyan
docker compose ps

Write-Host "`n=== NETWORK CONNECTIVITY ===" -ForegroundColor Cyan
Test-NetConnection -ComputerName 8.8.8.8 -Port 443 | Select-Object TcpTestSucceeded

Write-Host "`n=== PORTS IN USE ===" -ForegroundColor Cyan
foreach ($port in @(80, 443, 5000, 5432, 6379)) {
    $process = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($process) {
        $proc_name = (Get-Process -Id $process.OwningProcess).ProcessName
        Write-Host "Port $port: IN USE by $proc_name"
    } else {
        Write-Host "Port $port: Available"
    }
}

Write-Host "`n=== FIREWALL STATUS ===" -ForegroundColor Cyan
Get-NetFirewallProfile | Select-Object Name, Enabled

Write-Host "`nDiagnostics complete!" -ForegroundColor Green
```


## CONTACT / ESCALATION

If issue persists after above troubleshooting:

1. Collect diagnostic data:
```powershell
docker compose logs --all > logs.txt  2>&1
docker system df > disk_usage.txt
docker inspect atlas_app > container_inspect.txt
Get-Process Docker* | Out-File -FilePath docker_processes.txt
```

2. Check Docker issues: https://github.com/docker/for-win/issues

3. Check Compose issues: https://github.com/docker/compose/issues
