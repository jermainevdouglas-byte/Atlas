# ====================================================================
# ENVIRONMENT SETUP CHECKLIST (.env Configuration)
# ====================================================================
# Before running: docker compose up -d --build
# Follow this step-by-step to configure .env properly
# ====================================================================

## STEP 1: CREATE .env FILE
```powershell
cd D:\AtlasSimple\atlas\ATLAS1
Copy-Item ".env.example" ".env" -Force
```

`.env.example` is the active source template for new deployments.

## STEP 2: EDIT .env IN TEXT EDITOR
```powershell
notepad .env
```

Or use any text editor (VS Code, Notepad++, etc.)


## STEP 3: MANDATORY CHANGES (Must change these before deploying)

### SECRET_KEY (Application security key)
**Current:** `SECRET_KEY=REPLACE_WITH_64PLUS_CHAR_RANDOM_SECRET_abc123...`

**Action:** Replace with a random 64+ character string
- No spaces or special characters that need escaping (stick to alphanumeric + _-!@#$%)
- Use a generator like: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

**Example:**
```
SECRET_KEY=kL9pQ3xR7mN2vC5bH8jF1tW4sD6aE0_8uI9oP2qR3sT4uV5wX6yZ7-aB1cD2eFg
```

**Verification:** Should be at least 64 characters long and random


### POSTGRES_PASSWORD (Database password)
**Current:** `POSTGRES_PASSWORD=REPLACE_WITH_STRONG_DB_PASSWORD_min16chars`

**Action:** Replace with a strong password (minimum 16 characters)
- Include uppercase letters (A-Z)
- Include lowercase letters (a-z)
- Include numbers (0-9)
- Include special characters (!@#$%^&*_-)
- AVOID: quotes ("), backslashes (\), or semicolons (;)

**Example:**
```
POSTGRES_PASSWORD=SecureDB_Pass123!456#789
```

**Important:** Must be at least 16 characters long


### POSTGRES_DSN (PostgreSQL connection string)
**Current:** `POSTGRES_DSN=postgresql://atlas:REPLACE_WITH_STRONG_DB_PASSWORD_min16chars@postgres:5432/atlas`

**Action:** Update the password part to match POSTGRES_PASSWORD above

**Before:**
```
POSTGRES_DSN=postgresql://atlas:REPLACE_WITH_STRONG_DB_PASSWORD_min16chars@postgres:5432/atlas
```

**After (matching example passwords above):**
```
POSTGRES_DSN=postgresql://atlas:SecureDB_Pass123!456#789@postgres:5432/atlas
```

**Format:** `postgresql://[USERNAME]:[PASSWORD]@[HOST]:[PORT]/[DATABASE]`
- USERNAME: atlas (don't change)
- PASSWORD: must match POSTGRES_PASSWORD
- HOST: postgres (don't change, Docker internal DNS)
- PORT: 5432 (don't change)
- DATABASE: atlas (don't change)


### REDIS_PASSWORD (Cache password)
**Current:** `REDIS_PASSWORD=REPLACE_WITH_REDIS_PASSWORD`

**Action:** Replace with a strong password (8+ characters, or leave empty for development)

**Example:**
```
REDIS_PASSWORD=RedisCache_Pwd456!
```

**Note:** This is separate from POSTGRES_PASSWORD. Can use a different value.


### REDIS_URL (Redis connection string)
**Current:** `REDIS_URL=redis://:REPLACE_WITH_REDIS_PASSWORD@redis:6379/0`

**Action:** Update the password part to match REDIS_PASSWORD

**Before:**
```
REDIS_URL=redis://:REPLACE_WITH_REDIS_PASSWORD@redis:6379/0
```

**After (matching example above):**
```
REDIS_URL=redis://:RedisCache_Pwd456!@redis:6379/0
```

**Format:** `redis://:[PASSWORD]@[HOST]:[PORT]/[DB]`
- PASSWORD: must match REDIS_PASSWORD (after the colon)
- HOST: redis (don't change, Docker internal DNS)
- PORT: 6379 (don't change)
- DB: 0 (don't change)


## STEP 4: OPTIONAL CUSTOMIZATION (Recommended for production)

### DOMAIN (Your site's hostname)
**Current:** `DOMAIN=atlas.example.com`

**Action:** Replace with your actual domain (or localhost for development)

**Examples:**
- Production: `DOMAIN=atlas.mycompany.com`
- Development: `DOMAIN=localhost`


### SMTP_HOST, SMTP_USER, SMTP_PASS (Email notifications)
**Current:** Empty (alerts disabled)

**Action:** Configure if you want email alerts for errors

**Examples for Gmail:**
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=atlas@mycompany.com
```

**Leave empty** if not needed


### LOG_LEVEL (Application logging verbosity)
**Current:** `LOG_LEVEL=INFO`

**Options:**
- DEBUG: Very verbose, shows every operation
- INFO: Standard, shows important events (recommended)
- WARNING: Only warnings and errors
- ERROR: Only errors

**Recommendation for production:** Keep as INFO


### HSTS_PRELOAD (HTTPS security header)
**Current:** `HSTS_PRELOAD=0`

**Action:** Set to 1 only if:
- You have SSL/HTTPS configured
- You want to register with browser HSTS preload list
- You're committed to running HTTPS indefinitely

**For development:** Keep as 0


## STEP 5: VERIFY YOUR CHANGES

### Checklist
- [ ] SECRET_KEY: 64+ random characters, no spaces
- [ ] POSTGRES_PASSWORD: 16+ characters, strong (upper+lower+num+special)
- [ ] POSTGRES_DSN: password part matches POSTGRES_PASSWORD
- [ ] REDIS_PASSWORD: 8+ characters (or empty for dev)
- [ ] REDIS_URL: password part matches REDIS_PASSWORD
- [ ] DOMAIN: Set to your domain or localhost
- [ ] PROD_MODE=1: Should be set (production mode)
- [ ] No REPLACE_* strings remaining (except PROMOTE_CMD, SMTP_PASS which can be empty)

### Quick verification command (PowerShell)
```powershell
# Check for any remaining REPLACE_ placeholders
(Get-Content .env) -match "REPLACE_" | Select-Object -First 10
# Should return nothing or only comments
```

### Detailed verification
```powershell
# Check all critical values are set
@("SECRET_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD", "DOMAIN") | ForEach-Object {
    $value = (Get-Content .env | Select-String "^$_=" | ForEach-Object {$_.ToString().Split('=')[1]})
    Write-Host "$_`: $($value.Substring(0, [Math]::Min(20, $value.Length)))..."
}
```


## STEP 6: SAVE AND CLOSE

- Save the .env file (Ctrl+S or File → Save)
- Close the text editor
- Do NOT commit .env to Git (should be in .gitignore)


## STEP 7: READY TO DEPLOY

```powershell
cd D:\AtlasSimple\atlas\ATLAS1

# Create storage directory if needed
if (-not (Test-Path "D:\Storage")) {
    New-Item -ItemType Directory -Path "D:\Storage" -Force
}

# Deploy
docker compose up -d --build

# Wait for initialization
Start-Sleep -Seconds 40

# Verify
docker compose ps
curl http://localhost/
```


## TROUBLESHOOTING ENV ISSUES

### "password authentication failed"
**Problem:** POSTGRES_PASSWORD doesn't match POSTGRES_DSN

**Solution:**
1. Open .env
2. Find POSTGRES_PASSWORD value: `SecureDB_Pass123!456#789`
3. Find POSTGRES_DSN and verify it contains same password:
   `postgresql://atlas:SecureDB_Pass123!456#789@postgres:5432/atlas`
4. If mismatch, update POSTGRES_DSN to match
5. Rebuild: `docker compose down && docker compose up -d --build`


### "redis: connection refused"
**Problem:** REDIS_PASSWORD or REDIS_URL incorrect

**Solution:**
1. Open .env
2. Find REDIS_PASSWORD value
3. Find REDIS_URL and verify it contains same password:
   `redis://:[PASSWORD]@redis:6379/0` ← PASSWORD part should match REDIS_PASSWORD
4. If using empty password, use: `redis://redis:6379/0` (no colon before hostname)
5. Rebuild: `docker compose down && docker compose up -d --build`


### "App won't start, no database"
**Problem:** Database path or connection string wrong

**Solution:**
1. Check POSTGRES_DSN format:
   - Must be: `postgresql://atlas:[PASSWORD]@postgres:5432/atlas`
   - HOST must be `postgres` (not 127.0.0.1 or localhost)
2. Verify POSTGRES_USER=atlas matches POSTGRES_DSN
3. Check logs: `docker compose logs postgres --tail=50`
4. If Postgres failed to init, delete volume and rebuild:
   ```powershell
   docker compose down -v
   docker compose up -d --build
   Start-Sleep -Seconds 60
   ```


### "Special characters in password causing issues"
**Problem:** Password contains characters that need escaping

**Solution:**
Use a password with only these safe characters:
- Uppercase letters: A-Z
- Lowercase letters: a-z
- Numbers: 0-9
- Safe special: !@#$%^&*_- (avoid quotes, backslashes, semicolons)

**Example of SAFE password:**
```
MySecurePass_123!@#
```

**Example of UNSAFE password (avoid):**
```
My"Pass\123;etc    ← Contains ", \, ; which need escaping
```


### "Can't find .env file"
**Problem:** .env file doesn't exist

**Solution:**
```powershell
cd D:\AtlasSimple\atlas\ATLAS1
Copy-Item ".env.example" ".env" -Force
# Now edit .env
notepad .env
```


## SECURITY REMINDERS

✓ **Do:**
- Use strong, random passwords (16+ chars)
- Store .env securely (not in version control)
- Regenerate SECRET_KEY for each environment
- Use different passwords for prod vs dev

✗ **Don't:**
- Commit .env to Git
- Share passwords in logs or error messages
- Use the same password for multiple services
- Use simple passwords like "password" or "123456"
- Hardcode secrets in Dockerfile


## PASSWORD GENERATOR (Optional)

### Generate SECRET_KEY (64 chars)
```powershell
-join ((1..64) | ForEach-Object {[char]::ConvertFromUtf32((65..90+97..122+48..57 | Get-Random))})
```

### Generate POSTGRES_PASSWORD (20 chars)
```powershell
$chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*_-"
-join (1..20 | ForEach-Object {$chars[(Get-Random -Maximum $chars.Length)]})
```

### Generate REDIS_PASSWORD (16 chars)
```powershell
$chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%"
-join (1..16 | ForEach-Object {$chars[(Get-Random -Maximum $chars.Length)]})
```


## FINAL CHECKLIST

- [ ] .env file created (copied from .env.example)
- [ ] SECRET_KEY changed and is 64+ chars
- [ ] POSTGRES_PASSWORD changed and is 16+ chars
- [ ] POSTGRES_DSN updated to match POSTGRES_PASSWORD
- [ ] REDIS_PASSWORD set
- [ ] REDIS_URL updated to match REDIS_PASSWORD
- [ ] DOMAIN configured to your site
- [ ] PROD_MODE=1 is set
- [ ] No REPLACE_* placeholders remain (except optional fields)
- [ ] File saved and closed
- [ ] Ready to run: `docker compose up -d --build`

---

**Next:** Run `docker compose up -d --build` and follow VALIDATION_CHECKLIST.md


