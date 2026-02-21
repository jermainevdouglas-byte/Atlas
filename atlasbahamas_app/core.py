#!/usr/bin/env python3
"""
AtlasBahamas - Pure-Python Property Management Server
Run:  python server.py      Open: http://127.0.0.1:5000
Self-contained: all files are embedded and created on first launch.
"""
import os, re, json, sqlite3, secrets, hashlib, hmac, sys, traceback, time, threading, smtplib, logging
from logging.handlers import RotatingFileHandler
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
try:
    from db import connect_db, postgres_enabled, DBOperationalError
except Exception:  # pragma: no cover - sqlite-only fallback
    connect_db = None
    postgres_enabled = lambda *_args, **_kwargs: False
    DBOperationalError = (sqlite3.OperationalError,)
try:
    from redis_client import RedisClient
except Exception:
    RedisClient = None

def _env_bool(name, default=False):
    v = os.getenv(name)
    if v is None:
        return bool(default)
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _env_int(name, default):
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return int(default)

def _env_csv(name, default=""):
    raw = os.getenv(name, default if default is not None else "")
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]

def _normalize_host_value(value):
    txt = (value or "").strip().lower()
    if not txt:
        return ""
    if "://" in txt:
        try:
            txt = (urlparse(txt).netloc or "").strip().lower()
        except Exception:
            return ""
    txt = txt.split("/", 1)[0].strip()
    if txt.startswith("[") and "]" in txt:
        txt = txt[1:txt.find("]")]
    return txt

def _is_local_host_value(host_value):
    h = _normalize_host_value(host_value)
    if h.count(":") == 1:
        h = h.split(":", 1)[0]
    return h in ("localhost", "127.0.0.1", "::1")

def _load_secret_key(data_dir):
    default_marker = "atlasbahamas_secret_key_change_in_production"
    env_key = (os.getenv("SECRET_KEY") or "").strip()
    # A valid explicit env key always wins.
    if env_key and env_key != default_marker and len(env_key) >= 32:
        return env_key
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / ".secret_key"
    try:
        if secret_file.exists():
            key = secret_file.read_text(encoding="utf-8").strip()
            if len(key) >= 32:
                return key
    except Exception:
        pass
    # Generate once and persist. This avoids a hardcoded shared default key.
    key = secrets.token_urlsafe(64)
    try:
        secret_file.write_text(key, encoding="utf-8")
    except Exception:
        pass
    return key

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
TEMPLATES_DIR = SITE_DIR / "templates"
STATIC_DIR = SITE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", r"D:\Storage"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(STORAGE_ROOT)))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "atlasbahamas.sqlite"))
SECRET_KEY = _load_secret_key(DATA_DIR)

def _build_allowed_hosts():
    hosts = []
    for raw in _env_csv("ALLOWED_HOSTS", os.getenv("CSRF_TRUSTED_HOSTS", "")):
        h = _normalize_host_value(raw)
        if h and h not in hosts:
            hosts.append(h)
    base_host = _normalize_host_value(PUBLIC_BASE_URL)
    if base_host and base_host not in hosts:
        hosts.append(base_host)
    bind_host = _normalize_host_value(HOST)
    if bind_host and bind_host not in ("0.0.0.0", "::") and bind_host not in hosts:
        hosts.append(bind_host)
    for local in ("localhost", "127.0.0.1", "::1"):
        if local not in hosts:
            hosts.append(local)
    return tuple(hosts)

ALLOWED_HOSTS = _build_allowed_hosts()
DEFAULT_PUBLIC_HOST = _normalize_host_value(PUBLIC_BASE_URL) or (ALLOWED_HOSTS[0] if ALLOWED_HOSTS else "localhost")

SESSION_COOKIE = "ATLASBAHAMAS_SESSION"
CSRF_COOKIE = "ATLASBAHAMAS_CSRF"
SESSION_DAYS = 7
LOGIN_MAX_ATTEMPTS = _env_int("LOGIN_MAX_ATTEMPTS", _env_int("MAX_LOGIN_ATTEMPTS", 5))
LOGIN_LOCK_SECONDS = _env_int("LOGIN_LOCK_SECONDS", max(30, _env_int("LOGIN_ATTEMPT_TIMEOUT_MINUTES", 15) * 60))
LOGIN_TRACK_SECONDS = _env_int("LOGIN_TRACK_SECONDS", max(LOGIN_LOCK_SECONDS, 900))
INVITE_EXPIRY_HOURS = int(os.getenv("INVITE_EXPIRY_HOURS", "72"))
INVITE_RESEND_COOLDOWN_MIN = int(os.getenv("INVITE_RESEND_COOLDOWN_MIN", "30"))
MAX_IMAGE_UPLOAD_BYTES = max(1024 * 1024, _env_int("MAX_IMAGE_UPLOAD_BYTES", 5 * 1024 * 1024))
MAX_PDF_UPLOAD_BYTES = max(1024 * 1024, _env_int("MAX_PDF_UPLOAD_BYTES", 10 * 1024 * 1024))
MAX_ATTACHMENT_UPLOAD_BYTES = max(1024 * 1024, _env_int("MAX_ATTACHMENT_UPLOAD_BYTES", 10 * 1024 * 1024))
MAX_REQUEST_BYTES = max(1024 * 1024, _env_int("MAX_REQUEST_BYTES", 40 * 1024 * 1024))
MAX_MULTIPART_PARTS = max(10, _env_int("MAX_MULTIPART_PARTS", 200))
ENFORCE_HTTPS = _env_bool("ENFORCE_HTTPS", not _is_local_host_value(HOST))
SECURITY_HEADERS_ENABLED = _env_bool("SECURITY_HEADERS_ENABLED", True)
HSTS_MAX_AGE = max(0, _env_int("HSTS_MAX_AGE", 31536000))
PROD_MODE = _env_bool("PROD_MODE", ENFORCE_HTTPS and not _is_local_host_value(HOST))
FORCE_SECURE_COOKIES = _env_bool("FORCE_SECURE_COOKIES", ENFORCE_HTTPS and not _is_local_host_value(HOST))
SESSION_COOKIE_SAMESITE = (os.getenv("SESSION_COOKIE_SAMESITE", "Strict" if PROD_MODE else "Lax") or "Lax").strip().title()
CSRF_COOKIE_SAMESITE = (os.getenv("CSRF_COOKIE_SAMESITE", SESSION_COOKIE_SAMESITE) or SESSION_COOKIE_SAMESITE).strip().title()
if SESSION_COOKIE_SAMESITE not in ("Lax", "Strict", "None"):
    SESSION_COOKIE_SAMESITE = "Lax"
if CSRF_COOKIE_SAMESITE not in ("Lax", "Strict", "None"):
    CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
HSTS_INCLUDE_SUBDOMAINS = _env_bool("HSTS_INCLUDE_SUBDOMAINS", True)
HSTS_PRELOAD = _env_bool("HSTS_PRELOAD", False)
ALLOW_RESET_LINK_IN_RESPONSE_NONLOCAL = _env_bool("ALLOW_RESET_LINK_IN_RESPONSE_NONLOCAL", False)
HOUSEKEEPING_INTERVAL_SECONDS = max(60, _env_int("HOUSEKEEPING_INTERVAL_SECONDS", 3600))
PASSWORD_RESET_RETENTION_DAYS = max(1, _env_int("PASSWORD_RESET_RETENTION_DAYS", 30))
LOG_LEVEL = (os.getenv("LOG_LEVEL", "INFO") or "INFO").strip().upper()
LOG_JSON = _env_bool("LOG_JSON", True)
LOG_DIR = Path(os.getenv("LOG_DIR", str(DATA_DIR / "logs")))
LOG_FILE = os.getenv("LOG_FILE", str(LOG_DIR / "atlasbahamas.log"))
LOG_MAX_BYTES = max(1024 * 1024, _env_int("LOG_MAX_BYTES", 20 * 1024 * 1024))
LOG_BACKUP_COUNT = max(1, _env_int("LOG_BACKUP_COUNT", 10))
ERROR_ALERT_EMAIL_TO = (os.getenv("ERROR_ALERT_EMAIL_TO") or "").strip()
ERROR_ALERT_COOLDOWN_SECONDS = max(60, _env_int("ERROR_ALERT_COOLDOWN_SECONDS", 900))
REDIS_SESSIONS_ENABLED = _env_bool("REDIS_SESSIONS_ENABLED", True)
REDIS_SESSION_PREFIX = (os.getenv("REDIS_SESSION_PREFIX", "atlasbahamas:session:") or "atlasbahamas:session:").strip() or "atlasbahamas:session:"
REDIS_SESSION_USER_PREFIX = (os.getenv("REDIS_SESSION_USER_PREFIX", "atlasbahamas:session_uid:") or "atlasbahamas:session_uid:").strip() or "atlasbahamas:session_uid:"
SCHEMA_VERSION = 17
POSTGRES_MIGRATIONS_REL = ("migrations", "postgres")
RATE_LIMIT_RULES = {
    "/login": (12, 60),
    "/inquiry": (20, 300),
    "/apply": (20, 300),
    "/landlord/tenant/invite": (30, 300),
    "/manager/tenant/invite": (30, 300),
}
SMTP_HOST = (os.getenv("SMTP_HOST") or "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = (os.getenv("SMTP_USER") or "").strip()
SMTP_PASS = os.getenv("SMTP_PASS") or ""
SMTP_FROM = (os.getenv("SMTP_FROM") or "").strip()
SMTP_USE_TLS = (os.getenv("SMTP_USE_TLS", "1") or "1").strip().lower() in ("1", "true", "yes", "on")
RESET_LINK_IN_RESPONSE = (os.getenv("RESET_LINK_IN_RESPONSE", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
SEED_DEMO_DATA = _env_bool("SEED_DEMO_DATA", False)
BOOTSTRAP_ADMIN_FULL_NAME = (os.getenv("BOOTSTRAP_ADMIN_FULL_NAME") or "AtlasBahamas Administrator").strip() or "AtlasBahamas Administrator"
BOOTSTRAP_ADMIN_PHONE = (os.getenv("BOOTSTRAP_ADMIN_PHONE") or "").strip()
BOOTSTRAP_ADMIN_EMAIL = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip()
BOOTSTRAP_ADMIN_USERNAME = (os.getenv("BOOTSTRAP_ADMIN_USERNAME") or "").strip()
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or ""
CLEAR_SESSIONS_ON_START = _env_bool("CLEAR_SESSIONS_ON_START", True)
PUBLIC_PATHS = {"/", "/about", "/contact", "/login", "/register", "/forgot", "/reset"}
CSRF_EXEMPT_PATHS = {"/login", "/register", "/forgot", "/reset"}

PERMISSION_LABELS = [
    ("tenant.portal", "Tenant dashboard + tools"),
    ("tenant.payment.submit", "Tenant payment submission"),
    ("tenant.maintenance.submit", "Tenant maintenance submission"),
    ("tenant.invite.respond", "Tenant invite accept/decline"),
    ("landlord.portal", "Property Manager dashboard + tools"),
    ("landlord.property.manage", "Property Manager property/unit management"),
    ("landlord.tenant_sync.manage", "Property Manager tenant sync"),
    ("landlord.listing.submit", "Property Manager listing submissions"),
    ("manager.portal", "Property Manager operations dashboard"),
    ("manager.property.manage", "Property Manager property registration/view"),
    ("manager.leases.manage", "Property Manager lease assignment/removal"),
    ("manager.ops.update", "Property Manager maintenance/check/payment updates"),
    ("manager.tenant_sync.manage", "Property Manager tenant sync"),
    ("manager.listing.submit", "Property Manager listing submissions"),
    ("admin.portal", "Admin console access"),
    ("admin.submissions.review", "Admin approve/reject listing submissions"),
    ("admin.permissions.manage", "Admin role permission management"),
    ("admin.audit.read", "Admin audit view/export"),
]

PERMISSION_DEFAULTS = {
    "tenant.portal": {"tenant", "admin"},
    "tenant.payment.submit": {"tenant", "admin"},
    "tenant.maintenance.submit": {"tenant", "admin"},
    "tenant.invite.respond": {"tenant", "admin"},
    # Manager + landlord are merged into property_manager.
    "landlord.portal": {"property_manager", "admin"},
    "landlord.property.manage": {"property_manager", "admin"},
    "landlord.tenant_sync.manage": {"property_manager", "admin"},
    "landlord.listing.submit": {"property_manager", "admin"},
    "manager.portal": {"property_manager", "admin"},
    "manager.property.manage": {"property_manager", "admin"},
    "manager.leases.manage": {"property_manager", "admin"},
    "manager.ops.update": {"property_manager", "admin"},
    "manager.tenant_sync.manage": {"property_manager", "admin"},
    "manager.listing.submit": {"property_manager", "admin"},
    "admin.portal": {"admin"},
    "admin.submissions.review": {"admin"},
    "admin.permissions.manage": {"admin"},
    "admin.audit.read": {"admin"},
}

_LOGIN_GUARD = {}
_LOGIN_GUARD_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS = {}
_RATE_LIMIT_LOCK = threading.Lock()
_HOUSEKEEPING_LOCK = threading.Lock()
_LAST_HOUSEKEEPING_TS = 0.0
_LAST_DAILY_AUTOMATION_DATE = ""
_LOGGER = logging.getLogger("atlasbahamas")
_LOG_READY = False
_ALERT_LOCK = threading.Lock()
_LAST_ALERT_TS = {}
_REDIS_LOCK = threading.Lock()
_REDIS_CACHE = None
_REDIS_DISABLED = False

def setup_logging():
    global _LOG_READY
    if _LOG_READY:
        return _LOGGER
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOGGER.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    _LOGGER.handlers = []
    if LOG_JSON:
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                return json.dumps(payload, ensure_ascii=True)
        fmt = JsonFormatter()
    else:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    _LOGGER.addHandler(fh)
    _LOGGER.addHandler(sh)
    _LOG_READY = True
    return _LOGGER

def logger():
    return setup_logging()

def log_event(level, message, **fields):
    lg = logger()
    if fields:
        try:
            message = f"{message} | {json.dumps(fields, ensure_ascii=True, default=str)}"
        except Exception:
            pass
    lg.log(level, message)

def _send_error_alert_once(alert_key, subject, body):
    if not ERROR_ALERT_EMAIL_TO:
        return False
    now = int(time.time())
    with _ALERT_LOCK:
        last = _LAST_ALERT_TS.get(alert_key, 0)
        if now - last < ERROR_ALERT_COOLDOWN_SECONDS:
            return False
        _LAST_ALERT_TS[alert_key] = now
    try:
        return send_email(ERROR_ALERT_EMAIL_TO, subject, body)
    except Exception:
        return False

def log_exception(message, **fields):
    lg = logger()
    if fields:
        try:
            message = f"{message} | {json.dumps(fields, ensure_ascii=True, default=str)}"
        except Exception:
            pass
    lg.exception(message)
    _send_error_alert_once(
        fields.get("alert_key") or "generic_error",
        f"AtlasBahamas Critical Error: {fields.get('scope') or 'runtime'}",
        f"{message}\n\nHost={HOST}:{PORT}\nTime={datetime.now(timezone.utc).isoformat(timespec='seconds')}",
    )

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  EMBEDDED FILES â€” auto-written to disk on first start
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def redis_runtime_client():
    global _REDIS_CACHE, _REDIS_DISABLED
    if not REDIS_SESSIONS_ENABLED or RedisClient is None or _REDIS_DISABLED:
        return None
    if _REDIS_CACHE is not None:
        return _REDIS_CACHE
    with _REDIS_LOCK:
        if _REDIS_CACHE is not None:
            return _REDIS_CACHE
        if _REDIS_DISABLED:
            return None
        try:
            client = RedisClient()
            if not client.enabled or not client.ping():
                _REDIS_DISABLED = True
                log_event(logging.WARNING, "redis_unavailable_fallback_sqlite_sessions")
                return None
            _REDIS_CACHE = client
            log_event(logging.INFO, "redis_sessions_enabled")
            return _REDIS_CACHE
        except Exception as e:
            _REDIS_DISABLED = True
            log_event(logging.WARNING, "redis_init_failed_fallback_sqlite_sessions", error=str(e))
            return None

def _redis_session_key(raw):
    return f"{REDIS_SESSION_PREFIX}{raw}"

def _redis_user_session_key(uid):
    return f"{REDIS_SESSION_USER_PREFIX}{to_int(uid, 0)}"

def _expires_to_ttl_seconds(expires_at):
    ts = str(expires_at or "").strip()
    if not ts:
        return max(1, SESSION_DAYS * 86400)
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ttl = int((dt - datetime.now(timezone.utc)).total_seconds())
        return max(0, ttl)
    except Exception:
        return max(1, SESSION_DAYS * 86400)

def cache_session_redis(raw, user_id, expires_at, ip_hash="", user_agent_hash=""):
    token = (raw or "").strip()
    uid = to_int(user_id, 0)
    if not token or uid <= 0:
        return False
    cli = redis_runtime_client()
    if not cli:
        return False
    ttl = _expires_to_ttl_seconds(expires_at)
    if ttl <= 0:
        return False
    ukey = _redis_user_session_key(uid)
    prior = cli.get_text(ukey) or ""
    if prior and prior != token:
        cli.delete(_redis_session_key(prior))
    payload = {
        "user_id": uid,
        "expires_at": str(expires_at or ""),
        "ip_hash": str(ip_hash or ""),
        "user_agent_hash": str(user_agent_hash or ""),
    }
    ok_sess = cli.set_json(_redis_session_key(token), payload, ttl_seconds=ttl)
    ok_user = cli.set_text(ukey, token, ttl_seconds=ttl)
    return bool(ok_sess and ok_user)

def get_session_redis(raw):
    token = (raw or "").strip()
    if not token:
        return None
    cli = redis_runtime_client()
    if not cli:
        return None
    data = cli.get_json(_redis_session_key(token))
    if not isinstance(data, dict):
        return None
    uid = to_int(data.get("user_id"), 0)
    if uid <= 0:
        cli.delete(_redis_session_key(token))
        return None
    if _expires_to_ttl_seconds(data.get("expires_at")) <= 0:
        delete_session_redis(token, user_id=uid)
        return None
    return {
        "user_id": uid,
        "expires_at": str(data.get("expires_at") or ""),
        "ip_hash": str(data.get("ip_hash") or ""),
        "user_agent_hash": str(data.get("user_agent_hash") or ""),
    }

def delete_session_redis(raw, user_id=None):
    token = (raw or "").strip()
    cli = redis_runtime_client()
    if not cli:
        return
    uid = to_int(user_id, 0)
    if token:
        if uid <= 0:
            sess = cli.get_json(_redis_session_key(token)) or {}
            uid = to_int(sess.get("user_id"), 0)
        cli.delete(_redis_session_key(token))
    if uid > 0:
        ukey = _redis_user_session_key(uid)
        if token:
            mapped = cli.get_text(ukey) or ""
            if (not mapped) or mapped == token:
                cli.delete(ukey)
        else:
            cli.delete(ukey)

def clear_redis_sessions():
    cli = redis_runtime_client()
    if not cli:
        return 0
    removed = 0
    removed += cli.delete_by_prefix(REDIS_SESSION_PREFIX)
    removed += cli.delete_by_prefix(REDIS_SESSION_USER_PREFIX)
    return removed

def invalidate_session_raw(raw):
    token = (raw or "").strip()
    if not token:
        return
    db_write_retry(lambda c: c.execute("DELETE FROM sessions WHERE session_id=?", (token,)))
    delete_session_redis(token)

def invalidate_user_sessions(c, user_id):
    uid = to_int(user_id, 0)
    if uid <= 0:
        return 0
    rows = c.execute("SELECT session_id FROM sessions WHERE user_id=?", (uid,)).fetchall()
    c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    deleted = 0
    for r in rows:
        sid = (r["session_id"] or "").strip()
        if sid:
            delete_session_redis(sid, user_id=uid)
            deleted += 1
    if deleted == 0:
        delete_session_redis("", user_id=uid)
    return deleted

def _user_row_to_dict(r):
    return {
        "id": r["id"],
        "full_name": r["full_name"],
        "username": r["username"],
        "role": r["role"],
        "account_number": r["account_number"],
        "email": r["email"],
        "phone": r["phone"],
    }

EMBEDDED_FILES = {

"site/templates/base.html": '''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preload" as="image" href="/static/img/door_hero.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/css/styles.css"><title>{{title}}</title></head>
<body>
<header class="header"><div class="container">
<nav class="nav">
  <div class="nav-left desktop-only">
    <a class="pill" data-nav="/about" href="/about">About Us</a>
    <a class="pill" data-nav="/contact" href="/contact">Contact Us</a>
    <a class="pill" data-nav="/listings" href="/listings">Listings</a>
  </div>

  <a class="brand" href="/">AtlasBahamas</a>

  <div class="nav-right">
    <div class="nav-actions desktop-only">{{nav_right}}</div>

    <div class="menu-wrap">
      <button class="hamburger" id="hamburgerBtn" type="button" aria-label="Menu" aria-expanded="false">
        <span class="bar"></span><span class="bar"></span><span class="bar"></span>
      </button>
      <div class="menu-panel" id="hamburgerPanel" role="menu" aria-label="Site menu">
        <a class="menu-item" href="/about">About Us</a>
        <a class="menu-item" href="/contact">Contact Us</a>
        <a class="menu-item" href="/listings">Listings</a>
        <div class="menu-sep"></div>
        {{nav_menu}}
      </div>
    </div>
  </div>
</nav></div></header>
{{content}}
{{scripts}}
<script>
(function(){
  function getCookie(name){
    var m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.$?*|{}()\\[\\]\\\\\\/\\+^]/g, '\\\\$&') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  }

  // Set active state on top links.
  var p = location.pathname || '/';
  document.querySelectorAll('.nav-left [data-nav]').forEach(function(a){
    var target = a.getAttribute('data-nav') || '';
    var active = (p === target) || (target === '/listings' && p.indexOf('/listing/') === 0);
    if(active) a.classList.add('is-active');
  });

  // Inject a consistent in-page Back to Dashboard button on role tool pages.
  (function injectBackToDashboard(){
    var marker = document.getElementById('atlasRoleMarker');
    if(!marker) return;
    var home = marker.getAttribute('data-home') || '';
    var path = location.pathname || '/';
    if(!home || path === home) return;
    if(!/^\\/(tenant|landlord|manager|property-manager|admin)(\\/|$)/.test(path)) return;
    if(document.getElementById('atlasBackToDash')) return;
    var exists = Array.prototype.some.call(document.querySelectorAll('a[href]'), function(a){
      return (a.getAttribute('href') || '') === home && /back\\s+to\\s+dashboard/i.test(a.textContent || '');
    });
    if(exists) return;
    var row = document.createElement('div');
    row.className = 'row';
    row.style.margin = '0 0 12px 0';
    row.innerHTML = '<a id="atlasBackToDash" class="ghost-btn" href=\"' + home + '\">Back to Dashboard</a>';
    var hdr = document.querySelector('.public-header') || document.querySelector('.dash-top');
    if(hdr){
      hdr.insertAdjacentElement('afterend', row);
      return;
    }
    var host = document.querySelector('.public-inner') || document.querySelector('.container') || document.body;
    if(host.firstChild) host.insertBefore(row, host.firstChild);
    else host.appendChild(row);
  })();

  // CSRF hidden field injection for all POST forms (double-submit cookie pattern).
  var csrf = getCookie('ATLASBAHAMAS_CSRF');
  if(csrf){
    document.querySelectorAll('form[method=\"POST\"], form[method=\"post\"]').forEach(function(form){
      if(form.querySelector('input[name=\"csrf_token\"]')) return;
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'csrf_token';
      input.value = csrf;
      form.appendChild(input);
    });
  }

  const btn=document.getElementById('hamburgerBtn');
  const panel=document.getElementById('hamburgerPanel');
  if(btn&&panel){
    function close(){ panel.classList.remove('open'); btn.setAttribute('aria-expanded','false'); }
    btn.addEventListener('click', function(e){
      e.stopPropagation();
      const open=panel.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function(){ close(); });
    panel.addEventListener('click', function(e){ e.stopPropagation(); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') close(); });
  }
  // Profile dropdown (desktop)
  const pbtn=document.querySelector('.profile-btn');
  const ppanel=document.querySelector('.profile-panel');
  if(pbtn&&ppanel){
    function pclose(){ ppanel.classList.remove('open'); pbtn.setAttribute('aria-expanded','false'); }
    pbtn.addEventListener('click', function(e){
      e.stopPropagation();
      const open=ppanel.classList.toggle('open');
      pbtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function(){ pclose(); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') pclose(); });
    ppanel.addEventListener('click', function(e){ e.stopPropagation(); });
  }
  // Legacy dropdown compatibility (older nav markup)
  const lbtn=document.querySelector('.dd-trigger');
  const lpanel=document.querySelector('.dd-menu');
  if(lbtn&&lpanel){
    function lclose(){ lpanel.classList.remove('open'); lbtn.setAttribute('aria-expanded','false'); }
    lbtn.addEventListener('click', function(e){
      e.stopPropagation();
      const open=lpanel.classList.toggle('open');
      lbtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function(){ lclose(); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') lclose(); });
    lpanel.addEventListener('click', function(e){ e.stopPropagation(); });
  }

  // Collapsible manager dashboard sections.
  document.addEventListener('click', function(e){
    var head = e.target && e.target.closest ? e.target.closest('[data-toggle="ops-nav"]') : null;
    if(!head) return;
    var section = head.closest('.ops-nav-section');
    if(!section) return;
    section.classList.toggle('open');
    var caret = head.querySelector('.ops-nav-caret');
    if(caret){
      caret.textContent = section.classList.contains('open') ? '▾' : '▸';
    }
  });

  // Form submit loading states to prevent accidental duplicate actions.
  document.querySelectorAll('form').forEach(function(form){
    form.addEventListener('submit', function(){
      var buttons = form.querySelectorAll('button[type="submit"]');
      if(!buttons || !buttons.length) return;
      buttons.forEach(function(btn){
        if(btn.disabled) return;
        var original = btn.getAttribute('data-original-label') || btn.innerHTML;
        btn.setAttribute('data-original-label', original);
        btn.disabled = true;
        btn.style.opacity = '0.72';
        btn.innerHTML = 'Processing...';
      });
      setTimeout(function(){
        buttons.forEach(function(btn){
          var original = btn.getAttribute('data-original-label');
          if(original){
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = original;
          }
        });
      }, 12000);
    });
  });

  // Share buttons (works for dynamically added elements too)
  function _atlasShare(url, title){
    try{
      if(navigator.share){
        navigator.share({title: title || document.title, url: url}).catch(function(){});
        return;
      }
    }catch(e){}
    // Fallback: try clipboard, else prompt
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(url).then(function(){
        alert("Link copied to clipboard");
      }).catch(function(){
        prompt("Copy this link:", url);
      });
    }else{
      prompt("Copy this link:", url);
    }
  }
  window.atlasShare = _atlasShare;
  document.addEventListener('click', function(e){
    var el = e.target && e.target.closest ? e.target.closest('[data-share-url]') : null;
    if(!el) return;
    e.preventDefault();
    e.stopPropagation();
    _atlasShare(el.getAttribute('data-share-url'), el.getAttribute('data-share-title') || '');
  });

})();
</script>
</body></html>''',

"site/templates/landlord_listing_submit.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Submit Property for Listing</h2><p class="muted">Send this unit to Admin for approval. Upload photos and an optional lease PDF.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/landlord">Back to Dashboard</a></div></div><a class="ghost-btn" href="/landlord/property/{{property_id}}">Back</a></div>

<form class="card" method="post" action="/landlord/listing/submit" enctype="multipart/form-data">
  <input type="hidden" name="unit_id" value="{{unit_id}}">
  <input type="hidden" name="property_id" value="{{property_id}}">
  <div class="grid2">
    <label>Title<input name="title" required value="{{listing_title}}"></label>
    <label>Monthly Rent (USD)<input name="price" type="number" min="0" required value="{{price}}"></label>
    <label>Location<input name="location" required value="{{location}}"></label>
    <label>Category
      <select name="category" required>
        <option value="Long Term Rental" {{cat_long}}>Long Term Rental</option>
        <option value="Short Term Rental" {{cat_short}}>Short Term Rental</option>
        <option value="Vehicle Rental" {{cat_vehicle}}>Vehicle Rental</option>
        <option value="Sell Your Property to Us" {{cat_sell}}>Sell Your Property to Us</option>
      </select>
    </label>
    <label>Beds<input name="beds" type="number" min="0" required value="{{beds}}"></label>
    <label>Baths<input name="baths" type="number" min="0" required value="{{baths}}"></label>
  </div>
  <label>Description<textarea name="description" rows="5" required>{{description}}</textarea></label>

  <div class="grid2">
    <label>Upload Photos (JPG/PNG/WEBP, up to 5MB each)
      <input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple>
    </label>
    <label>Optional Lease PDF
      <input name="lease_pdf" type="file" accept="application/pdf">
    </label>
  </div>

  <div class="actions">
    <button class="primary-btn" type="submit">Submit for Approval</button>
  </div>
</form>
</div></section>''',

"site/templates/admin_home_legacy.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Admin Console</h2><p class="muted">Full control over AtlasBahamas.</p></div><a class="ghost-btn" href="/">Home</a></div>
<div class="grid2">
  <a class="card" href="/admin/submissions"><h3 style="margin:0;">Listing Submissions</h3><p class="muted">Approve/reject landlord submissions.</p></a>
  <a class="card" href="/manager/listings"><h3 style="margin:0;">Manage Listings</h3><p class="muted">Edit listings, photos, availability.</p></a>
  <a class="card" href="/manager/inquiries"><h3 style="margin:0;">Inquiries</h3><p class="muted">Inbox for listing inquiries.</p></a>
  <a class="card" href="/manager/applications"><h3 style="margin:0;">Applications</h3><p class="muted">Review applications and status.</p></a>
</div>
</div></section>''',

"site/templates/admin_submissions.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Listing Submissions</h2><p class="muted">Pending submissions awaiting approval.</p></div><a class="ghost-btn" href="/admin">Back to Admin</a></div>
<div class="card">
{{filters_form}}
{{bulk_actions}}
<table class="table">
<thead><tr><th>ID</th><th>Title</th><th>Property</th><th>Unit</th><th>Price</th><th>Status</th><th>Checklist</th><th>Review Note</th><th>Actions</th></tr></thead>
<tbody>{{rows}}</tbody>
</table>
{{empty}}
</div>
</div></section>''',

"site/templates/home.html": '''<section class="hero"><div class="container">
<div class="door-scene">
<h1 class="door-heading">AtlasBahamas Property Management</h1>
<p class="door-tagline">An experience from the moment you arrive.</p>
<a href="/login" class="door-link door-photo-link" aria-label="Enter">
<img class="door-photo" src="/static/img/door_hero.svg" fetchpriority="high" loading="eager" decoding="async" width="900" height="1500" onerror="this.onerror=null;this.src='https://upload.wikimedia.org/wikipedia/commons/5/54/A_Doorway.jpg';" alt="Front door entrance">
<span class="door-photo-badge">Enter</span>
</a>
<div style="margin-top:28px;">
<div class="notice" style="max-width:560px;margin:0 auto;text-align:center;">
<b>Secure Access:</b>&ensp;Use your provisioned account credentials.
</div>
<div class="row" style="margin-top:14px;justify-content:center;">
<a class="secondary-btn" href="/listings">Browse Listings</a>
<a class="ghost-btn" href="/about">About AtlasBahamas</a>
</div>
</div>
</div>
</div></section>''',

"site/templates/about.html": '''<section class="public"><div class="public-inner"><div class="card">
<h2>About AtlasBahamas</h2>
<p class="muted">In myth AtlasBahamas bears the heavens. In business AtlasBahamas bears the weight between landlord and tenant&#8212;payments, documentation, maintenance, and property checks&#8212;so both sides can move with confidence.</p>
</div></div></section>''',

"site/templates/contact.html": '''<section class="public"><div class="public-inner"><div class="card">
<h2>Contact AtlasBahamas</h2>
<div class="muted">
<div><b>Phone:</b> (242) 000-0000</div>
<div><b>Email:</b> support@atlasbahamas.example</div>
<div style="margin-top:10px;"><b>Business Hours:</b><br>Mon&#8211;Fri 9&#8211;5 &bull; Sat 10&#8211;2 &bull; Sun Closed</div>
</div></div></div></section>''',

"site/templates/changelog.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Changelog</h2><p class="muted">Recent platform updates and fixes.</p></div></div>
<div class="card">{{changelog_rows}}</div>
</div></section>''',

"site/templates/login.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Log in</h2><p class="muted">Your role controls access.</p></div></div>
<div class="card" style="max-width:520px;">
{{error_box}}
<form method="POST" action="/login" style="margin-top:12px;">
<div class="field"><label>Username</label><input name="username" required autocomplete="username"></div>
<div class="field" style="margin-top:10px;"><label>Password</label><input type="password" name="password" required autocomplete="current-password"></div>
<button class="primary-btn" style="margin-top:12px;width:100%;">Log in</button>
</form>
<p class="muted" style="margin:12px 0 0;">No account? <a href="/register">Register</a></p>
</div></div></section>''',

"site/templates/register.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Register</h2><p class="muted">Account number generated automatically.</p></div></div>
<div class="card" style="max-width:760px;">
{{message_box}}
<form method="POST" action="/register" style="margin-top:12px;">
<div class="row">
<div class="field" style="flex:1;"><label>Full name</label><input name="full_name" required></div>
<div class="field" style="flex:1;"><label>Phone</label><input name="phone" required></div>
</div>
<div class="field" style="margin-top:10px;"><label>Email</label><input type="email" name="email" required></div>
<div class="row" style="margin-top:10px;">
<div class="field" style="flex:1;"><label>Username</label><input name="username" required></div>
<div class="field" style="flex:1;"><label>Password (10+, upper/lower/number/symbol)</label><input type="password" name="password" required></div>
</div>
<div class="field" style="margin-top:10px;"><label>Role</label>
<select name="role" required><option value="tenant">Tenant</option></select>
<div class="muted" style="margin-top:6px;">Property Manager accounts are provisioned by Admin only.</div>
</div>
<button class="primary-btn" style="margin-top:12px;">Create account</button>
</form></div></div></section>''',

"site/templates/listings.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Listings</h2><p class="muted">Refine by price, location, bedrooms, and category.</p></div></div>
<div class="card">
<div class="row" style="align-items:flex-end;">
<div class="field" style="flex:1;"><label>Max Price</label><input id="maxPrice" type="number" min="0" placeholder="2500"></div>
<div class="field" style="flex:1;"><label>Location</label><select id="location"><option value="">Any</option>{{location_options}}</select></div>
<div class="field" style="flex:1;"><label>Bedrooms (min)</label><input id="beds" type="number" min="0" placeholder="2"></div>
<div class="field" style="flex:1;"><label>Category</label>
<select id="category"><option value="">All</option><option>Short Term Rental</option><option>Long Term Rental</option><option>Vehicle Rental</option><option>Sell Your Property to Us</option></select></div>
<button id="applyFilters" class="primary-btn">Search</button>
<button id="openCompare" class="ghost-btn" type="button">Compare</button>
{{save_search_button}}
</div>
<div class="muted" style="margin-top:10px;" id="resultCount"></div>
<div id="compareTray" class="notice" style="margin-top:10px;display:none;"></div>
</div>
<div id="listingResults" style="display:grid;gap:10px;margin-top:12px;"></div>
</div></section>''',

"site/templates/listing_detail.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div>
<h2>{{listing_title}}</h2>
<p class="muted">${{listing_price}} &bull; {{listing_location}} &bull; {{listing_beds}} bed / {{listing_baths}} bath &bull; {{listing_category}}</p>
</div><a class="ghost-btn" href="/listings">Back</a></div>

<div class="card">
{{gallery_html}}
<p class="muted" style="margin-top:12px;line-height:1.6">{{listing_description}}</p>

<div class="row" style="margin-top:14px;gap:10px;flex-wrap:wrap;">
  {{favorite_button}}
  <button class="secondary-btn" type="button" data-share-url="{{share_url}}" data-share-title="{{listing_title}}">Share</button>
  <a class="btn ghost" href="/listings">Browse more</a>
</div>
</div>

<div class="grid2" style="margin-top:18px;">
  <div class="card">
    <h3 style="margin:0 0 10px 0;">Apply for this listing</h3>
    <form method="POST" action="/apply" id="applyForm">
      <input type="hidden" name="listing_id" value="{{listing_id}}" form="applyForm">
      <div class="grid2">
        <div><label>Full name</label><input name="full_name" value="{{prefill_name}}" required form="applyForm"></div>
        <div><label>Email</label><input name="email" value="{{prefill_email}}" required form="applyForm"></div>
        <div><label>Phone</label><input name="phone" value="{{prefill_phone}}" form="applyForm"></div>
        <div><label>Monthly income</label><input name="income" placeholder="$" form="applyForm"></div>
      </div>
      <label style="margin-top:10px;">Notes</label>
      <textarea name="notes" rows="4" placeholder="Any helpful details..." form="applyForm"></textarea>
      <button class="primary-btn" type="submit" style="margin-top:10px;" form="applyForm">Submit application</button>
      <div class="muted" style="margin-top:8px;">Application is reviewed separately from inquiry messages.</div>
    </form>
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px 0;">Have a question?</h3>
    <form method="POST" action="/inquiry" id="inquiryForm">
      <input type="hidden" name="listing_id" value="{{listing_id}}" form="inquiryForm">
      <div class="grid2">
        <div><label>Full name</label><input name="full_name" value="{{prefill_name}}" required form="inquiryForm"></div>
        <div><label>Email</label><input name="email" value="{{prefill_email}}" required form="inquiryForm"></div>
        <div><label>Phone</label><input name="phone" value="{{prefill_phone}}" form="inquiryForm"></div>
        <div><label>Subject</label><input name="subject" placeholder="Viewing / availability / price..." form="inquiryForm"></div>
      </div>
      <label style="margin-top:10px;">Message</label>
      <textarea name="body" rows="4" placeholder="Type your message..." required form="inquiryForm"></textarea>
      <button class="secondary-btn" type="submit" style="margin-top:10px;" form="inquiryForm">Send inquiry</button>
      <div class="muted" style="margin-top:8px;">Inquiry is sent instantly and does not submit an application.</div>
    </form>
  </div>
</div>

</div></section>''',


"site/templates/admin_home.html": '''<section class="dash"><div class="container">
<div class="dash-header">
  <div><h2>Admin Console</h2><p class="muted">Unrestricted access to all dashboards and admin panels.</p></div>
</div>

<div class="grid-2">
  <div class="card">
    <h3>Dashboards</h3>
    <div class="row" style="flex-wrap:wrap;gap:10px;margin-top:10px;">
      <a class="secondary-btn" href="/tenant">Tenant</a>
      <a class="secondary-btn" href="/property-manager">Property Manager</a>
      <a class="secondary-btn" href="/landlord">Legacy Landlord View</a>
      <a class="secondary-btn" href="/manager">Legacy Manager View</a>
    </div>
    <p class="muted" style="margin-top:10px;">Tip: you can open any role view without restrictions.</p>
  </div>

  <div class="card">
    <h3>Admin Panels</h3>
    <div class="row" style="flex-wrap:wrap;gap:10px;margin-top:10px;">
      <a class="secondary-btn" href="/manager/leases">Leases</a>
      <a class="secondary-btn" href="/manager/maintenance">Maintenance</a>
      <a class="secondary-btn" href="/manager/payments">Payments</a>
      <a class="secondary-btn" href="/manager/listings">Listings</a>
      <a class="secondary-btn" href="/manager/applications">Applications</a>
      <a class="secondary-btn" href="/manager/inquiries">Inquiries</a>
      <a class="secondary-btn" href="/manager/inspections">Inspections</a>
      <a class="secondary-btn" href="/manager/preventive">Preventive</a>
      <a class="secondary-btn" href="/admin/users">User Roles</a>
      <a class="secondary-btn" href="/admin/permissions">Role Permissions</a>
      <a class="secondary-btn" href="/admin/audit">Audit Log</a>
      <a class="secondary-btn" href="/property-manager/search">Global Search</a>
      <a class="secondary-btn" href="/notifications">Alerts</a>
      <a class="secondary-btn" href="/favorites">Favorites</a>
    </div>
  </div>
</div>

<div class="card" style="margin-top:18px;">
  <h3>Quick stats</h3>
  <div class="grid-3" style="margin-top:10px;">
    <div class="stat"><div class="muted">Users</div><div class="stat-num">{{stat_users}}</div></div>
    <div class="stat"><div class="muted">Listings</div><div class="stat-num">{{stat_listings}}</div></div>
    <div class="stat"><div class="muted">Properties</div><div class="stat-num">{{stat_properties}}</div></div>
    <div class="stat"><div class="muted">Open Maintenance</div><div class="stat-num">{{stat_open_maint}}</div></div>
    <div class="stat"><div class="muted">Open Inquiries</div><div class="stat-num">{{stat_inq}}</div></div>
    <div class="stat"><div class="muted">Pending Applications</div><div class="stat-num">{{stat_apps}}</div></div>
  </div>
</div>
{{system_health_cards}}
{{pending_actions_cards}}
{{ops_cards}}

</div></section>''',

"site/templates/tenant_home.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Tenant Dashboard</h2><p class="muted">Pay rent, manage payment setup, request maintenance, and review alerts.</p></div></div>
<div class="card"><div class="row">
<a class="primary-btn" href="/tenant/pay-rent">Pay Rent</a>
<a class="secondary-btn" href="/tenant/payment-methods">Payment Methods</a>
<a class="secondary-btn" href="/tenant/autopay">Autopay</a>
<a class="secondary-btn" href="/tenant/pay-bills">Pay Bill</a>
<a class="secondary-btn" href="/tenant/maintenance/new">Request Maintenance</a>
<a class="ghost-btn" href="/tenant/payments">Payment History</a>
<a class="ghost-btn" href="/tenant/ledger">Ledger</a>
<a class="ghost-btn" href="/tenant/maintenance">My Maintenance</a>
<a class="ghost-btn" href="/tenant/lease">My Lease</a>
<a class="secondary-btn" href="/notifications">Alerts</a>
</div></div>
{{rent_due_card}}
{{lease_summary_card}}
{{alerts_widget}}
</div></section>''',

"site/templates/tenant_pay_rent.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Pay Rent</h2><p class="muted">Submit your rent payment.</p></div></div>
<div class="card" style="max-width:760px;">
{{message_box}}
{{lease_box}}
{{saved_method_box}}
<form method="POST" action="/tenant/pay-rent" style="margin-top:12px;">
<div class="field"><label>Amount</label><input type="number" name="amount" min="1" required placeholder="1800" value="{{default_amount}}"></div>
<div class="field" style="margin-top:10px;"><label>Payment Method</label><select name="payment_method_id">{{payment_method_options}}</select></div>
<button class="primary-btn" style="margin-top:12px;">Submit Payment</button>
</form>
<div class="row" style="margin-top:10px;"><a class="ghost-btn" href="/tenant/payment-methods">Manage Payment Methods</a><a class="ghost-btn" href="/tenant/autopay">Autopay Settings</a></div>
</div></div></section>''',

"site/templates/tenant_pay_bills.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Pay Bill</h2><p class="muted">Choose a provider and amount.</p></div></div>
<div class="card" style="max-width:720px;">
{{message_box}}
<form method="POST" action="/tenant/pay-bills">
<div class="field"><label>Provider</label><select name="provider" required>
<option>Cable Bahamas</option><option>Aliv</option><option>BTC</option><option>BPL</option>
</select></div>
<div class="field" style="margin-top:10px;"><label>Amount Depositing</label><input type="number" name="amount" min="1" required></div>
<button class="primary-btn" style="margin-top:12px;">Submit Bill Payment</button>
</form></div></div></section>''',

"site/templates/tenant_payments.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Payment History</h2><p class="muted">Your submitted payments.</p></div><a class="ghost-btn" href="/tenant/ledger">Open Ledger</a></div>
{{filters_form}}
{{summary_cards}}
<div class="card"><table class="table"><thead><tr><th>Date</th><th>Type</th><th>Provider</th><th>Amount</th><th>Status</th><th>Receipt</th></tr></thead><tbody>{{payments_rows}}</tbody></table>{{pager_box}}</div></div></section>''',

"site/templates/tenant_payment_confirmation.html": '''<section class="public"><div class="public-inner">
<div class="card" style="max-width:720px;margin:30px auto;">
  {{message_box}}
  <h2 style="margin-top:0;">Payment Submitted</h2>
  <p class="muted">Your payment request was recorded successfully.</p>
  <div class="grid-3" style="margin-top:12px;">
    <div class="stat"><div class="muted">Payment ID</div><div class="stat-num">#{{payment_id}}</div></div>
    <div class="stat"><div class="muted">Amount</div><div class="stat-num">{{amount}}</div></div>
    <div class="stat"><div class="muted">Status</div><div class="stat-num">{{status_badge}}</div></div>
  </div>
  <div class="row" style="margin-top:12px;">
    <div class="stat" style="flex:1;"><div class="muted">Type</div><div>{{payment_type}}</div></div>
    <div class="stat" style="flex:1;"><div class="muted">Provider</div><div>{{provider}}</div></div>
    <div class="stat" style="flex:1;"><div class="muted">Created</div><div>{{created_at}}</div></div>
  </div>
  <div class="row" style="margin-top:16px;">
    <a class="primary-btn" href="/tenant">Back to Dashboard</a>
    <a class="ghost-btn" href="/tenant/payment/receipt?id={{payment_id}}">View Receipt</a>
    <a class="ghost-btn" href="/tenant/payments">Payment History</a>
  </div>
  <div class="notice" style="margin-top:12px;"><b>Next:</b> You can track status updates from payment history or alerts.</div>
</div>
</div></section>''',

"site/templates/tenant_ledger.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Tenant Ledger</h2><p class="muted">Charges, payments, late fees, and monthly statements.</p></div><a class="ghost-btn" href="/tenant/payments">Back to Payments</a></div>
{{filters_form}}
{{summary_cards}}
{{roommate_box}}
<div class="card">
<table class="table"><thead><tr><th>Date</th><th>Month</th><th>Type</th><th>Category</th><th>Amount</th><th>Status</th><th>Note</th></tr></thead><tbody>{{ledger_rows}}</tbody></table>
{{pager_box}}
</div>
</div></section>''',

"site/templates/tenant_maintenance_new.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Request Maintenance</h2><p class="muted">Describe the issue.</p></div></div>
<div class="card" style="max-width:760px;">
{{message_box}}
<form method="POST" enctype="multipart/form-data" action="/tenant/maintenance/new">
<div class="field"><label>Issue Type</label><select name="issue_type"><option value="">General</option><option>Plumbing</option><option>Electrical</option><option>Appliance</option><option>HVAC</option><option>Security</option></select></div>
<div class="field"><label>Urgency</label><select name="urgency"><option value="normal">Normal</option><option value="high">High</option><option value="emergency">Emergency</option></select></div>
<div class="field"><label>Problem Description</label><textarea name="description" required placeholder="Example: Bathroom sink leaking..."></textarea></div>
<div class="field"><label>Upload Photo (optional)</label><input type="file" name="photo" accept="image/jpeg,image/png,image/webp"></div>
<button class="primary-btn" style="margin-top:12px;">Submit Request</button>
</form></div></div></section>''',

"site/templates/tenant_maintenance_list.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>My Maintenance</h2><p class="muted">Track your requests.</p></div></div>
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Created</th><th>Priority</th><th>Status</th><th>Assigned</th><th>Description</th><th>Details</th></tr></thead><tbody>{{maintenance_rows}}</tbody></table></div></div></section>''',

"site/templates/tenant_maintenance_detail.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Maintenance Request {{request_id}}</h2><p class="muted">Status timeline and assignment details.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/tenant/maintenance">Back to My Maintenance</a></div></div></div>
{{message_box}}
<div class="card" style="max-width:920px;">
{{detail_box}}
</div>
</div></section>''',

"site/templates/tenant_maintenance_confirmation.html": '''<section class="public"><div class="public-inner">
<div class="card" style="max-width:720px;margin:30px auto;">
  {{message_box}}
  <h2 style="margin-top:0;">Maintenance Request Submitted</h2>
  <p class="muted">Your request was delivered to the property manager team.</p>
  <div class="grid-3" style="margin-top:12px;">
    <div class="stat"><div class="muted">Request ID</div><div class="stat-num">#{{request_id}}</div></div>
    <div class="stat"><div class="muted">Priority</div><div class="stat-num">{{urgency_badge}}</div></div>
    <div class="stat"><div class="muted">Status</div><div class="stat-num">{{status_badge}}</div></div>
  </div>
  <div class="row" style="margin-top:12px;">
    <div class="stat" style="flex:1;"><div class="muted">Created</div><div>{{created_at}}</div></div>
    <div class="stat" style="flex:2;"><div class="muted">Summary</div><div>{{description}}</div></div>
  </div>
  <div class="row" style="margin-top:16px;">
    <a class="primary-btn" href="/tenant/maintenance/{{request_id}}">Open Request</a>
    <a class="ghost-btn" href="/tenant/maintenance">My Maintenance</a>
    <a class="ghost-btn" href="/tenant">Back to Dashboard</a>
  </div>
</div>
</div></section>''',

"site/templates/search_results.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Search Results</h2><p class="muted">Query: {{search_query}}</p></div><a class="ghost-btn" href="{{search_back_path}}">Back</a></div>
{{message_box}}
<div class="card">
  {{search_sections}}
</div>
</div></section>''',

"site/templates/tenant_payment_methods.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Payment Methods</h2><p class="muted">Save cards or bank methods for faster rent payments.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/tenant">Back to Dashboard</a></div></div><a class="ghost-btn" href="/tenant/autopay">Autopay Settings</a></div>
{{message_box}}
<div class="card" style="max-width:980px;">
<h3 style="margin-top:0;">Add Method</h3>
<form method="POST" action="/tenant/payment-methods">
<input type="hidden" name="action" value="add">
<div class="row">
<div class="field" style="flex:1;"><label>Type</label><select name="method_type"><option value="card">Card</option><option value="bank">Bank</option></select></div>
<div class="field" style="flex:1;"><label>Label</label><input name="brand_label" required placeholder="Visa Personal"></div>
<div class="field" style="flex:1;"><label>Last 4 Digits</label><input name="last4" maxlength="4" inputmode="numeric" required placeholder="1234"></div>
</div>
<label style="display:flex;gap:8px;align-items:center;margin-top:10px;"><input type="checkbox" name="is_default" value="1"> Set as default</label>
<button class="primary-btn" style="margin-top:12px;">Save Payment Method</button>
</form>
</div>
<div class="card" style="margin-top:12px;">
<h3 style="margin-top:0;">Saved Methods</h3>
<table class="table"><thead><tr><th>Type</th><th>Method</th><th>Default</th><th>Added</th><th>Actions</th></tr></thead><tbody>{{methods_rows}}</tbody></table>
{{empty_box}}
</div>
</div></section>''',

"site/templates/tenant_autopay.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Autopay Settings</h2><p class="muted">Automatically pay your rent every month.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/tenant">Back to Dashboard</a></div></div><a class="ghost-btn" href="/tenant/payment-methods">Payment Methods</a></div>
{{message_box}}
<div class="card" style="max-width:860px;">
{{autopay_notice}}
<form method="POST" action="/tenant/autopay" style="margin-top:10px;">
<div class="row">
<div class="field" style="flex:1;"><label>Status</label><select name="is_enabled"><option value="0" {{autopay_off_selected}}>Off</option><option value="1" {{autopay_on_selected}}>On</option></select></div>
<div class="field" style="flex:1;"><label>Payment Day</label><input type="number" min="1" max="28" name="payment_day" value="{{payment_day}}"></div>
<div class="field" style="flex:1;"><label>Reminder (days before)</label><input type="number" min="0" max="14" name="notify_days_before" value="{{notify_days_before}}"></div>
<div class="field" style="flex:1;"><label>Payment Method</label><select name="payment_method_id">{{autopay_method_options}}</select></div>
</div>
<button class="primary-btn" style="margin-top:12px;">Save Autopay Settings</button>
</form>
</div>
</div></section>''',

"site/templates/tenant_lease.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>My Lease</h2><p class="muted">Assigned by Property Manager.</p></div></div>
<div class="card">{{lease_info}}{{lease_doc_box}}{{esign_box}}{{contact_box}}</div></div></section>''',

"site/templates/landlord_home.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Landlord Dashboard</h2><p class="muted">Register properties, manage units, request checks, and track listing submissions.</p></div></div>
<div class="card"><div class="row">
<a class="primary-btn" href="/landlord/properties">View Properties</a>
<a class="secondary-btn" href="/landlord/property/new">Register Property</a>
<a class="secondary-btn" href="/landlord/check/new">Request Property Check</a>
<a class="ghost-btn" href="/landlord/checks">Check Requests</a>
<a class="secondary-btn" href="/landlord/listing-requests">Listing Submissions</a>
<a class="secondary-btn" href="/landlord/tenants">Tenant Sync</a>
</div></div></div></section>''',

"site/templates/landlord_properties.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>View Properties</h2><p class="muted">Your registered properties.</p></div><div class="row"><a class="primary-btn" href="/landlord/property/new">Register Property</a><a class="ghost-btn" href="/landlord/listing-requests">Listing Submissions</a><a class="ghost-btn" href="/landlord/export/properties">Export CSV</a></div></div>
{{message_box}}
{{portfolio_summary}}
{{filters_form}}
<div style="display:grid;gap:10px;">{{properties_cards}}{{no_properties}}</div></div></section>''',

"site/templates/manager_properties.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>View Properties</h2><p class="muted">Properties registered to your manager account.</p></div><div class="row"><a class="primary-btn" href="/manager/property/new">Register Property</a><a class="ghost-btn" href="/manager/export/properties">Export CSV</a></div></div>
{{message_box}}
{{portfolio_summary}}
{{filters_form}}
<div style="display:grid;gap:10px;">{{properties_cards}}{{no_properties}}</div></div></section>''',

"site/templates/landlord_property.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>{{prop_name}}</h2><p class="muted">{{prop_location}} &bull; {{prop_type}} &bull; {{prop_units}} units</p><div style="margin-top:10px;"><a class="ghost-btn" href="/landlord">Back to Dashboard</a></div></div>
  <div style="display:flex;gap:8px;align-items:center;">
    <a class="ghost-btn" href="/landlord/properties">Back</a>
    <a class="ghost-btn" href="/landlord/export/property_units?property_id={{property_id}}">Export Units CSV</a>
  </div>
</div>
{{message_box}}
{{property_summary}}
{{unit_filters}}
{{bulk_actions}}

<div class="card"><h3 style="margin-top:0;">Units</h3>
<p class="muted" style="margin-top:-6px;">Edit rent and vacancy in real time. Save per unit.</p>
<table class="table"><thead><tr><th>Unit</th><th>Occupied</th><th>Beds</th><th>Baths</th><th>Rent</th><th>Actions</th></tr></thead><tbody>{{units_rows}}</tbody></table>
</div>

<div class="card"><h3 style="margin-top:0;">Submit for Listing</h3>
<p class="muted" style="margin-top:-6px;">Send a unit to Admin for approval (add photos + optional lease PDF).</p>
<form method="POST" action="/landlord/listing/submit_all" class="row" style="margin:8px 0 12px 0;align-items:flex-end;">
  <input type="hidden" name="property_id" value="{{property_id}}">
  <div class="field" style="min-width:260px;flex:1;">
    <label>Category for all units</label>
    <select name="category" required>
      <option value="Long Term Rental">Long Term Rental</option>
      <option value="Short Term Rental">Short Term Rental</option>
      <option value="Vehicle Rental">Vehicle Rental</option>
      <option value="Sell Your Property to Us">Sell Your Property to Us</option>
    </select>
  </div>
  <button class="primary-btn" type="submit">Submit All Units</button>
</form>
<div style="display:flex;gap:10px;flex-wrap:wrap;">{{submit_buttons}}</div>
</div>

</div></section>''',

"site/templates/landlord_property_new.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Register Property</h2><p class="muted">Creates units automatically.</p></div></div>
<div class="card" style="max-width:820px;">{{error_box}}
<form method="POST" action="/landlord/property/new" enctype="multipart/form-data">
<div class="row">
<div class="field" style="flex:1;"><label>Property Name</label><input name="name" required placeholder="AtlasBahamas Sunset Apartments"></div>
<div class="field" style="flex:1;"><label>Location</label><input name="location" required placeholder="Nassau"></div>
</div>
<div class="row" style="margin-top:10px;">
<div class="field" style="flex:1;"><label>Property Type</label><select name="property_type" required><option>House</option><option selected>Apartment</option></select></div>
<div class="field" style="flex:1;"><label>Number of Units</label><input name="units_count" type="number" min="1" required value="4"></div>
</div>
<div class="field" style="margin-top:10px;"><label>Property Photos (optional)</label><input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple></div>
<button class="primary-btn" style="margin-top:12px;">Register Property</button>
</form></div></div></section>''',

"site/templates/manager_property_new.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Register Property</h2><p class="muted">Creates units automatically for manager-managed properties.</p></div></div>
<div class="card" style="max-width:820px;">{{error_box}}
<form method="POST" action="/manager/property/new" enctype="multipart/form-data">
<div class="row">
<div class="field" style="flex:1;"><label>Property Name</label><input name="name" required placeholder="AtlasBahamas Sunset Apartments"></div>
<div class="field" style="flex:1;"><label>Location</label><input name="location" required placeholder="Nassau"></div>
</div>
<div class="row" style="margin-top:10px;">
<div class="field" style="flex:1;"><label>Property Type</label><select name="property_type" required><option>House</option><option selected>Apartment</option></select></div>
<div class="field" style="flex:1;"><label>Number of Units</label><input name="units_count" type="number" min="1" required value="4"></div>
</div>
<div class="field" style="margin-top:10px;"><label>Property Photos (optional)</label><input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple></div>
<button class="primary-btn" style="margin-top:12px;">Register Property</button>
</form></div></div></section>''',

"site/templates/landlord_check_new.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Request Property Check</h2><p class="muted">Request a check for a property you own.</p></div></div>
<div class="card" style="max-width:820px;">{{error_box}}
<form method="POST" action="/landlord/check/new">
<div class="field"><label>Property ID</label><input name="property_id" required placeholder="Copy from View Property"></div>
<div class="field" style="margin-top:10px;"><label>Preferred Date</label><input type="date" name="preferred_date" required></div>
<div class="field" style="margin-top:10px;"><label>Notes</label><textarea name="notes" placeholder="Any specific details..."></textarea></div>
<button class="primary-btn" style="margin-top:12px;">Submit Check Request</button>
</form></div></div></section>''',

"site/templates/landlord_checks.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>My Property Checks</h2><p class="muted">Status of your requests.</p></div></div>
{{message_box}}
{{filters_form}}
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Property</th><th>Date</th><th>Status</th><th>Notes</th><th>Actions</th></tr></thead><tbody>{{checks_rows}}</tbody></table>{{pager_box}}</div></div></section>''',

"site/templates/landlord_listing_requests.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Listing Submissions</h2><p class="muted">Track listing requests you submitted for approval.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/landlord">Back to Dashboard</a></div></div></div>
<div class="row" style="margin-bottom:10px;"><a class="ghost-btn" href="/landlord/export/listing_requests">Export CSV</a><a class="ghost-btn" href="{{export_filtered_url}}">Export Filtered CSV</a></div>
{{message_box}}
{{filters_form}}
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Property</th><th>Unit</th><th>Title</th><th>Price</th><th>Status</th><th>Review Note</th><th>Submitted</th><th>Action</th></tr></thead><tbody>{{requests_rows}}</tbody></table>{{empty_box}}{{pager_box}}</div></div></section>''',

"site/templates/manager_listing_requests.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Listing Submissions</h2><p class="muted">Track listing requests you submitted for approval.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
<div class="row" style="margin-bottom:10px;"><a class="ghost-btn" href="{{export_filtered_url}}">Export Filtered CSV</a></div>
{{message_box}}
{{filters_form}}
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Property</th><th>Unit</th><th>Title</th><th>Price</th><th>Status</th><th>Review Note</th><th>Submitted</th></tr></thead><tbody>{{requests_rows}}</tbody></table>{{empty_box}}{{pager_box}}</div></div></section>''',

"site/templates/manager_home.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Manager Dashboard</h2><p class="muted">Organized operations view for portfolio, tenant, and workflow actions.</p></div></div>
<div class="card" style="margin-bottom:12px;"><div class="row"><a class="primary-btn" href="/manager/queue">Open Task Queue</a><a class="secondary-btn" href="/manager/rent-roll">Rent Roll</a><a class="secondary-btn" href="/manager/analytics">Analytics</a><a class="ghost-btn" href="/manager/calendar">Calendar View</a></div></div>
<div style="display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));">
  <div class="card"><h3 style="margin-top:0;">Operations</h3><div class="row"><a class="secondary-btn" href="/manager/maintenance">Maintenance</a><a class="secondary-btn" href="/manager/payments">Payments</a><a class="secondary-btn" href="/manager/checks">Property Checks</a><a class="secondary-btn" href="/manager/inspections">Inspections</a><a class="secondary-btn" href="/manager/preventive">Preventive</a></div></div>
  <div class="card"><h3 style="margin-top:0;">Properties & Leases</h3><div class="row"><a class="secondary-btn" href="/manager/properties">Properties</a><a class="secondary-btn" href="/manager/property/new">Register Property</a><a class="secondary-btn" href="/manager/leases">Leases</a><a class="secondary-btn" href="/manager/tenants">Tenant Sync</a></div></div>
  <div class="card"><h3 style="margin-top:0;">Listings & People</h3><div class="row"><a class="secondary-btn" href="/manager/listing-requests">Listing Submissions</a><a class="secondary-btn" href="/manager/inquiries">Inquiries</a><a class="secondary-btn" href="/manager/applications">Applications</a><a class="secondary-btn" href="/manager/batch-notify">Mass Notifications</a></div></div>
</div>
{{manager_nav_sections}}
{{today_queue}}
{{activity_feed}}
</div></section>''',

"site/templates/property_manager_home.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Property Manager Dashboard</h2><p class="muted">Unified role for portfolio, leasing, maintenance, listings, and tenant operations.</p></div></div>
{{message_box}}
{{portfolio_kpis}}
<div class="card">
  <h3 style="margin-top:0;">Quick Actions</h3>
  <div class="row" style="flex-wrap:wrap;gap:10px;">
    <a class="primary-btn" href="/manager/queue">Task Queue</a>
    <a class="secondary-btn" href="/manager/rent-roll">Rent Roll</a>
    <a class="secondary-btn" href="/manager/analytics">Analytics</a>
    <a class="primary-btn" href="/manager/leases">Assign Leases</a>
    <a class="secondary-btn" href="/manager/properties">Properties</a>
    <a class="secondary-btn" href="/manager/maintenance">Work Orders</a>
    <a class="secondary-btn" href="/manager/preventive">Preventive Maintenance</a>
    <a class="secondary-btn" href="/manager/inspections">Inspections</a>
    <a class="secondary-btn" href="/manager/tenants">Tenant Sync</a>
    <a class="secondary-btn" href="/manager/listing-requests">Listing Submissions</a>
    <a class="secondary-btn" href="/manager/batch-notify">Mass Notifications</a>
  </div>
</div>
{{manager_nav_sections}}
{{today_queue}}
{{recent_feed}}
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Global Search</h3>
  <form method="GET" action="/property-manager/search" class="row" style="align-items:flex-end;">
    <div class="field" style="flex:1;min-width:260px;"><label>Search all records</label><input name="q" value="{{search_q}}" placeholder="tenant, property, lease, maintenance, listing..."></div>
    <button class="primary-btn" type="submit">Search</button>
    <a class="ghost-btn" href="/property-manager">Reset</a>
  </form>
  {{search_results}}
</div>
</div></section>''',

"site/templates/manager_leases.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Assign Leases</h2><p class="muted">Select tenant, property and unit.</p></div></div>
{{message_box}}
<div class="card" style="max-width:980px;">
<form method="POST" action="/manager/leases" id="leaseForm" enctype="multipart/form-data">
<div class="row">
<div class="field" style="flex:1;"><label>Tenant</label><select name="tenant_account" required>{{tenant_options}}</select></div>
<div class="field" style="flex:1;"><label>Property</label><select name="property_id" id="propertySelect" required><option value="">Select...</option>{{property_options}}</select></div>
</div>
<div class="row" style="margin-top:10px;">
<div class="field" style="flex:1;"><label>Unit</label><select name="unit_label" id="unitSelect" required><option value="">Select...</option></select></div>
<div class="field" style="flex:1;"><label>Start Date</label><input type="date" name="start_date" required></div>
</div>
<div class="field" style="margin-top:10px;"><label>Lease Document (PDF, optional)</label><input type="file" name="lease_pdf" accept="application/pdf"></div>
<button class="primary-btn" style="margin-top:12px;">Assign Lease</button>
</form>
<h3 style="margin-top:18px;">Recent Leases</h3>
{{filters_form}}
<table class="table"><thead><tr><th>Tenant</th><th>Property</th><th>Unit</th><th>Start</th><th>End</th><th>Status</th><th>Split</th><th>E-Sign</th><th>Document</th><th>Actions</th></tr></thead><tbody>{{leases_rows}}</tbody></table>{{pager_box}}
</div>
<div class="card" style="margin-top:12px;max-width:980px;">
<h3 style="margin-top:0;">Roommate Split Payments</h3>
<form method="POST" action="/manager/roommates/add">
  <div class="row">
    <div class="field" style="flex:1;"><label>Lease</label><select name="lease_id" required><option value="">Select active lease...</option>{{roommate_lease_options}}</select></div>
    <div class="field" style="flex:1;"><label>Roommate Tenant</label><select name="roommate_account" required><option value="">Select tenant...</option>{{tenant_options}}</select></div>
    <div class="field" style="flex:1;"><label>Share Percent</label><input type="number" min="1" max="100" name="share_percent" value="50" required></div>
  </div>
  <button class="primary-btn" style="margin-top:12px;">Add Roommate Split</button>
</form>
<table class="table" style="margin-top:12px;"><thead><tr><th>Lease</th><th>Tenant</th><th>Share %</th><th>Status</th><th>Action</th></tr></thead><tbody>{{roommate_rows}}</tbody></table>
</div></div></section>''',

"site/templates/admin_users.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>User Roles</h2><p class="muted">Assign Tenant, Property Manager, or Admin roles. Property Manager is admin-managed only.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/admin">Back to Admin</a></div></div></div>
{{message_box}}
{{filters_form}}
<div class="card"><table class="table"><thead><tr><th>Account</th><th>Name</th><th>Username</th><th>Email</th><th>Role</th><th>Last Login</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>{{rows}}</tbody></table>{{pager_box}}</div></div></section>''',

"site/templates/manager_inspections.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Move-In / Move-Out Inspections</h2><p class="muted">Schedule inspections and submit checklist reports.</p></div><a class="ghost-btn" href="/manager/inspections/export">Export CSV</a></div>
{{message_box}}
<div class="card" style="max-width:980px;">
  <h3 style="margin-top:0;">Schedule Inspection</h3>
  <form method="POST" action="/manager/inspections/new">
    <div class="row">
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" required><option value="">Select...</option>{{property_options}}</select></div>
      <div class="field" style="flex:1;"><label>Unit Label</label><input name="unit_label" required placeholder="Unit 1"></div>
      <div class="field" style="flex:1;"><label>Type</label><select name="inspection_type" required><option value="move_in">move_in</option><option value="move_out">move_out</option></select></div>
    </div>
    <div class="row" style="margin-top:10px;">
      <div class="field" style="flex:1;"><label>Scheduled Date</label><input type="date" name="scheduled_date" required></div>
      <div class="field" style="flex:1;"><label>Tenant Account (optional)</label><input name="tenant_account" placeholder="A12345"></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Schedule Inspection</button>
  </form>
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Inspection Queue</h3>
  {{filters_form}}
  <table class="table"><thead><tr><th>ID</th><th>Type</th><th>Property</th><th>Unit</th><th>Tenant</th><th>Scheduled</th><th>Status</th><th>Checklist/Report</th><th>Update</th></tr></thead><tbody>{{rows}}</tbody></table>{{pager_box}}
</div>
</div></section>''',

"site/templates/manager_preventive.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Preventive Maintenance</h2><p class="muted">Schedule recurring tasks and track overdue work.</p></div></div>
{{message_box}}
<div class="card" style="max-width:980px;">
  <h3 style="margin-top:0;">Create Task</h3>
  <form method="POST" action="/manager/preventive/new">
    <div class="row">
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" required><option value="">Select...</option>{{property_options}}</select></div>
      <div class="field" style="flex:1;"><label>Unit Label (optional)</label><input name="unit_label" placeholder="Unit 1"></div>
      <div class="field" style="flex:1;"><label>Task</label><input name="task" required placeholder="HVAC filter change"></div>
    </div>
    <div class="row" style="margin-top:10px;">
      <div class="field" style="flex:1;"><label>Frequency (days)</label><input type="number" min="1" name="frequency_days" value="30" required></div>
      <div class="field" style="flex:1;"><label>Next Due Date</label><input type="date" name="next_due_date" required></div>
      <div class="field" style="flex:1;"><label>Assign Staff (optional)</label><select name="staff_id"><option value="">Unassigned</option>{{staff_options}}</select></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Create Task</button>
  </form>
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Task Queue</h3>
  {{filters_form}}
  <table class="table"><thead><tr><th>ID</th><th>Property</th><th>Unit</th><th>Task</th><th>Frequency</th><th>Next Due</th><th>Assigned</th><th>Status</th><th>Update</th></tr></thead><tbody>{{rows}}</tbody></table>{{pager_box}}
</div>
</div></section>''',

"site/templates/manager_batch_notify.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Mass Notifications</h2><p class="muted">Send one message to all active tenants for a property.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
{{message_box}}
<div class="card" style="max-width:980px;">
  <form method="POST" action="/manager/batch-notify">
    <div class="row">
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" required><option value="">Select...</option>{{property_options}}</select></div>
      <div class="field" style="flex:1;"><label>Subject</label><input name="subject" required placeholder="Important building update"></div>
    </div>
    <div class="field" style="margin-top:10px;"><label>Message</label><textarea name="body" rows="5" required placeholder="Write your notice..."></textarea></div>
    <button class="primary-btn" style="margin-top:12px;">Send Notification</button>
  </form>
</div>
</div></section>''',

"site/templates/manager_maintenance.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Maintenance Queue</h2><p class="muted">Update status and assign technician.</p></div></div>
{{message_box}}
{{view_links}}
{{staff_tools}}
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Tenant</th><th>Priority</th><th>Age</th><th>Status</th><th>Assigned</th><th>Description</th><th>Update</th></tr></thead><tbody>{{maintenance_rows}}</tbody></table></div></div></section>''',

"site/templates/manager_queue.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Manager Task Queue</h2><p class="muted">Prioritized work waiting for action across maintenance, payments, checks, inquiries, and applications.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
{{message_box}}
{{queue_filters}}
<div class="card">{{queue_rows}}</div>
</div></section>''',

"site/templates/manager_rent_roll.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Rent Roll</h2><p class="muted">Occupancy and rent status by property/unit.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
{{message_box}}
{{filters_form}}
{{summary_cards}}
<div class="card"><table class="table"><thead><tr><th>Property</th><th>Unit</th><th>Tenant</th><th>Rent</th><th>Status</th><th>Days Late</th><th>Last Paid</th><th>Actions</th></tr></thead><tbody>{{rent_roll_rows}}</tbody></table>{{pager_box}}</div>
</div></section>''',

"site/templates/manager_payments.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>All Payments</h2><p class="muted">System-wide payments.</p></div><a class="ghost-btn" href="{{export_filtered_url}}">Export Filtered CSV</a></div>
{{message_box}}
{{filters_form}}
{{summary_cards}}
<div class="card"><table class="table"><thead><tr><th>Date</th><th>Payer</th><th>Role</th><th>Type</th><th>Provider</th><th>Amount</th><th>Status</th><th>Update</th></tr></thead><tbody>{{payments_rows}}</tbody></table>{{pager_box}}</div></div></section>''',

"site/templates/manager_checks.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Property Checks</h2><p class="muted">Schedule and close landlord property-check requests.</p></div></div>
{{message_box}}
{{view_links}}
<div class="card"><table class="table"><thead><tr><th>ID</th><th>Requester</th><th>Property</th><th>Preferred Date</th><th>Notes</th><th>Status</th><th>Update</th></tr></thead><tbody>{{checks_rows}}</tbody></table></div></div></section>''',

"site/templates/manager_calendar.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Calendar View</h2><p class="muted">Checks and lease starts in one timeline.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
<div class="card">{{calendar_rows}}</div></div></section>''',

"site/templates/admin_permissions.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Role Permissions</h2><p class="muted">Current high-level role access matrix.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/admin">Back to Admin</a></div></div></div>
{{message_box}}
<div class="card"><table class="table"><thead><tr><th>Feature</th><th>Tenant</th><th>Property Manager</th><th>Admin</th></tr></thead><tbody>{{matrix_rows}}</tbody></table></div></div></section>''',

"site/templates/admin_audit.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Audit Log</h2><p class="muted">Track role actions and state changes.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/admin">Back to Admin</a></div></div><a class="ghost-btn" href="/admin/audit/export">Export CSV</a></div>
{{filter_form}}
<div class="card"><table class="table"><thead><tr><th>When</th><th>Actor</th><th>Role</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead><tbody>{{audit_rows}}</tbody></table>{{empty}}</div></div></section>''',

"site/templates/compare.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Compare Listings</h2><p class="muted">Side-by-side summary of selected properties.</p></div><a class="ghost-btn" href="/listings">Back to Listings</a></div>
<div class="card"><table class="table"><thead><tr><th>Listing</th><th>Price</th><th>Location</th><th>Beds</th><th>Baths</th><th>Category</th><th>Open</th></tr></thead><tbody>{{compare_rows}}</tbody></table>{{empty}}</div></div></section>''',

# â•â•â• CSS â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"site/static/css/styles.css": ''':root{--bg0:#05070f;--bg1:#0b1225;--text:rgba(255,255,255,.92);--muted:rgba(255,255,255,.68);--shadow:0 20px 60px rgba(0,0,0,.45);--r2:28px}
*{box-sizing:border-box;margin:0;padding:0}html,body{height:100%}
body{color:var(--text);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;
background:radial-gradient(900px 500px at 15% 20%,rgba(90,166,255,.18),transparent 60%),
radial-gradient(900px 500px at 85% 35%,rgba(137,89,255,.18),transparent 60%),
linear-gradient(180deg,var(--bg0),var(--bg1));overflow-x:hidden}
a{color:inherit}.muted{color:var(--muted)}.container{max-width:1100px;margin:0 auto;padding:0 18px}
.header{position:sticky;top:0;z-index:50;backdrop-filter:blur(16px);background:rgba(5,7,15,.55);border-bottom:1px solid rgba(255,255,255,.08);overflow:visible}
.nav{height:72px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;overflow:visible}
.nav-left,.nav-right{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.nav-right{justify-content:flex-end}
.nav-search-form{display:inline-flex;align-items:center}
.nav-search-input{width:170px;padding:9px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:var(--text)}
.nav-search-input::placeholder{color:rgba(255,255,255,.55)}
.pill{display:inline-flex;gap:8px;align-items:center;padding:10px 14px;border-radius:999px;border:1px solid rgba(255,255,255,.12);
background:rgba(255,255,255,.06);text-decoration:none;font-weight:800;font-size:14px;cursor:pointer;color:var(--text)}
.pill:hover{border-color:rgba(255,255,255,.22)}
.pill.is-active{background:rgba(90,166,255,.18);border-color:rgba(137,189,255,.4)}
.brand{justify-self:center;font-weight:1000;letter-spacing:.8px;font-size:20px;text-decoration:none;padding:10px 14px;border-radius:999px;
background:linear-gradient(90deg,rgba(90,166,255,.15),rgba(137,89,255,.15));border:1px solid rgba(255,255,255,.12)}
.brand:hover{border-color:rgba(255,255,255,.22)}
.card{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);border-radius:var(--r2);box-shadow:var(--shadow);padding:18px}
.hero{padding:46px 0 24px}
.row{display:flex;gap:12px;flex-wrap:wrap}
.primary-btn,.secondary-btn,.ghost-btn,button.primary-btn,button.secondary-btn,button.ghost-btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;
padding:12px 14px;border-radius:14px;border:1px solid rgba(255,255,255,.14);font-weight:900;text-decoration:none;cursor:pointer;color:var(--text);font-size:14px}
.primary-btn{background:linear-gradient(90deg,rgba(90,166,255,.95),rgba(137,89,255,.95));border-color:rgba(255,255,255,.18)}
.secondary-btn{background:rgba(255,255,255,.10)}.secondary-btn:hover{background:rgba(255,255,255,.14)}
.ghost-btn{background:transparent}.ghost-btn:hover{background:rgba(255,255,255,.08)}
.field label{display:block;font-size:12px;color:var(--muted);margin:0 0 6px;font-weight:700}
input,select,textarea{width:100%;padding:12px;color:var(--text);background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.12);
border-radius:14px;outline:none;font-size:14px;font-family:inherit}
textarea{resize:vertical;min-height:90px}
.public{padding:26px 0 70px}.public-inner{max-width:1100px;margin:0 auto;padding:0 18px}
.public-header{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin:6px 0 14px}
.prop-item{display:grid;grid-template-columns:68px 1fr auto;gap:12px;align-items:center;padding:12px;border-radius:16px;
border:1px solid rgba(255,255,255,.10);background:rgba(0,0,0,.18)}
.badge{font-size:12px;padding:8px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.08)}
.thumb{width:68px;height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.14);
background:radial-gradient(circle at 30% 30%,rgba(90,166,255,.35),rgba(137,89,255,.18) 55%,rgba(0,0,0,.35))}
.notice{border-left:3px solid rgba(90,166,255,.9);padding:10px 12px;border-radius:14px;background:rgba(90,166,255,.08);border:1px solid rgba(255,255,255,.10)}
.err{border-left-color:rgba(255,80,120,.9);background:rgba(255,80,120,.08)}
.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px;border-bottom:1px solid rgba(255,255,255,.10);text-align:left;font-size:13px;vertical-align:top}

/* â•â•â• DOOR â•â•â• */
.door-scene{display:flex;flex-direction:column;align-items:center;padding:10px 0 36px;text-align:center}
.door-heading{font-size:clamp(26px,5vw,46px);font-weight:1000;letter-spacing:.4px;
background:linear-gradient(135deg,#fff 30%,rgba(90,166,255,.9) 60%,rgba(137,89,255,.85));
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.door-tagline{font-size:clamp(14px,2.2vw,19px);color:var(--muted);font-weight:700;margin-top:6px;margin-bottom:30px}
.door-link{text-decoration:none;display:block}
.door-photo-link{position:relative;display:inline-block;border-radius:20px;overflow:hidden;
border:1px solid rgba(255,255,255,.2);box-shadow:0 30px 80px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.06) inset;
transition:transform .3s ease, box-shadow .3s ease}
.door-photo-link:hover{transform:translateY(-3px) scale(1.01);box-shadow:0 40px 90px rgba(0,0,0,.62),0 0 0 1px rgba(255,255,255,.1) inset}
.door-photo{display:block;width:min(420px,85vw);height:min(560px,70vh);object-fit:cover;object-position:center}
.door-photo-badge{position:absolute;left:50%;bottom:16px;transform:translateX(-50%);
padding:10px 20px;border-radius:999px;border:1px solid rgba(255,255,255,.42);
background:linear-gradient(180deg,rgba(0,0,0,.55),rgba(0,0,0,.74));color:#fff;
font-size:13px;font-weight:900;letter-spacing:2px;text-transform:uppercase;
text-shadow:0 1px 6px rgba(0,0,0,.65)}
@media(max-width:600px){.door-photo{width:88vw;height:62vh}}


/* Responsive top menu */
.desktop-only{display:flex}
.nav-left,.nav-right{flex-wrap:nowrap;min-width:0}
.nav-actions{display:flex;align-items:center;gap:12px;flex-wrap:nowrap}
.menu-wrap{position:relative;display:none;flex:0 0 auto}
.hamburger{width:44px;height:44px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);display:inline-flex;flex-direction:column;justify-content:center;gap:5px;padding:10px;cursor:pointer}
.hamburger .bar{height:2px;width:100%;background:rgba(255,255,255,.9);border-radius:2px}
.menu-panel{position:absolute;right:0;top:54px;min-width:220px;max-width:80vw;max-height:min(560px,calc(100vh - 96px));max-height:min(560px,calc(100dvh - 96px));overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;touch-action:pan-y;background:rgba(10,14,30,.94);border:1px solid rgba(255,255,255,.14);border-radius:16px;box-shadow:var(--shadow);padding:10px;display:none;z-index:50}
.menu-panel.open{display:block}
.menu-item{display:block;padding:10px 12px;border-radius:12px;text-decoration:none;border:1px solid transparent}
.menu-item:hover{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.10)}
.menu-sep{height:1px;background:rgba(255,255,255,.10);margin:8px 0}
.btn-link{background:transparent;text-align:left;width:100%;color:inherit;font:inherit;cursor:pointer}
@media (max-width: 1200px){
  .desktop-only{display:none}
  .menu-wrap{display:block}
  .nav-search-form{display:none}
  .nav{grid-template-columns:auto 1fr auto}
  .brand{justify-self:center}
}
.stat{padding:14px 16px;border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(255,255,255,.04)}
.stat-num{font-size:28px;font-weight:800;margin-top:6px}
.grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media (max-width: 820px){ .grid-3{grid-template-columns:1fr} }
.kpi-trend{margin-top:6px;font-size:12px;color:var(--muted)}
.kpi-trend.up{color:rgba(74,222,128,.95)}
.kpi-trend.down{color:rgba(255,120,120,.95)}

/* Dashboard section navigator */
.ops-nav-wrap{display:grid;gap:10px}
.ops-nav-section{border:1px solid rgba(255,255,255,.10);border-radius:12px;background:rgba(255,255,255,.03)}
.ops-nav-head{width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border:0;border-radius:12px;background:transparent;color:var(--text);font-weight:800;cursor:pointer}
.ops-nav-head:hover{background:rgba(255,255,255,.05)}
.ops-nav-caret{opacity:.85}
.ops-nav-items{display:none;padding:0 8px 8px}
.ops-nav-section.open .ops-nav-items{display:grid;gap:6px}
.ops-nav-link{display:flex;justify-content:space-between;align-items:center;padding:9px 10px;border-radius:10px;border:1px solid transparent;text-decoration:none}
.ops-nav-link:hover{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.08)}
.ops-nav-link.active{background:rgba(90,166,255,.14);border-color:rgba(90,166,255,.30)}
.ops-nav-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;padding:2px 7px;border-radius:999px;background:rgba(255,90,90,.86);border:1px solid rgba(255,255,255,.24);font-size:11px;font-weight:900}


/* Profile dropdown */
.profile,.dropdown{position:relative;display:inline-flex;align-items:center;flex:0 0 auto}
.profile-btn,.dd-trigger{display:inline-flex;align-items:center;gap:10px;padding:8px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.12);
background:rgba(255,255,255,.06);cursor:pointer;color:var(--text);font-weight:900;font-size:14px}
.profile-btn:hover,.dd-trigger:hover{border-color:rgba(255,255,255,.22)}
.avatar{width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
background:linear-gradient(135deg,rgba(90,166,255,.9),rgba(137,89,255,.85));color:#071022;font-weight:1000}
.profile-name{max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.caret{opacity:.8}
.role-badge{background:rgba(255,255,255,.08)}
.admin-badge{background:rgba(255,210,100,.14);border-color:rgba(255,210,100,.22)}
.mini-badge{margin-left:-2px;font-size:12px;padding:6px 9px;border-radius:999px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.08)}
.menu-badge{display:inline-flex;align-items:center;justify-content:center;min-width:20px;padding:2px 7px;border-radius:999px;background:rgba(255,90,90,.86);border:1px solid rgba(255,255,255,.24);font-size:11px;font-weight:900;margin-left:6px}
.menu-title{display:block;padding:8px 12px;color:rgba(255,255,255,.65);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.profile-panel,.dd-menu{position:absolute;right:0;top:54px;min-width:240px;max-width:min(90vw,320px);max-height:min(560px,calc(100vh - 96px));max-height:min(560px,calc(100dvh - 96px));overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;touch-action:pan-y;background:rgba(10,14,30,.94);border:1px solid rgba(255,255,255,.14);
border-radius:16px;box-shadow:var(--shadow);padding:10px;display:none;z-index:60}
.profile-panel.open,.dd-menu.open{display:block}
.dd-menu{margin:0}
.dd-head{padding:10px 12px}
.dd-item{display:block;width:100%;padding:10px 12px;border-radius:12px;text-decoration:none;border:1px solid transparent;background:transparent;text-align:left}
.dd-item:hover{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.10)}
.dd-sep{height:1px;background:rgba(255,255,255,.10);margin:8px 0}
.profile-panel::-webkit-scrollbar,.dd-menu::-webkit-scrollbar,.menu-panel::-webkit-scrollbar{width:8px}
.profile-panel::-webkit-scrollbar-thumb,.dd-menu::-webkit-scrollbar-thumb,.menu-panel::-webkit-scrollbar-thumb{background:rgba(255,255,255,.25);border-radius:999px}
.profile-panel::-webkit-scrollbar-track,.dd-menu::-webkit-scrollbar-track,.menu-panel::-webkit-scrollbar-track{background:rgba(255,255,255,.05);border-radius:999px}

/* Gallery + tables */
.gallery{display:flex;flex-direction:column;gap:10px}
.gallery .main{width:100%;max-height:420px;object-fit:cover;border-radius:18px;border:1px solid rgba(255,255,255,.12)}
.gallery .thumbs{display:flex;gap:8px;flex-wrap:wrap}
.gallery .thumb{display:block;width:84px;height:64px;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,.12)}
.gallery .thumb img{width:100%;height:100%;object-fit:cover;display:block}
.table{width:100%;border-collapse:collapse}
.table th,.table td{padding:10px 8px;border-bottom:1px solid rgba(255,255,255,.10);text-align:left;vertical-align:top}
.table th{font-size:12px;color:rgba(255,255,255,.70);text-transform:uppercase;letter-spacing:.06em}
.badge.ok{background:rgba(0,255,140,.14);border-color:rgba(0,255,140,.30)}
.badge.no{background:rgba(255,90,90,.14);border-color:rgba(255,90,90,.30)}

''',

# â•â•â• JS â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"site/static/js/listings.js": '''function escapeHtml(s){return String(s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#039;"}[c];})}
var COMPARE_KEY="atlasbahamas_compare_ids";
function currentFilters(){
  return {
    maxPrice:document.getElementById("maxPrice").value||"",
    location:document.getElementById("location").value||"",
    beds:document.getElementById("beds").value||"",
    category:document.getElementById("category").value||""
  };
}
function buildParams(f){
  var p=new URLSearchParams();
  if(f.maxPrice)p.set("maxPrice",f.maxPrice);
  if(f.location)p.set("location",f.location);
  if(f.beds)p.set("beds",f.beds);
  if(f.category)p.set("category",f.category);
  return p;
}
function getCompare(){try{return JSON.parse(localStorage.getItem(COMPARE_KEY)||"[]").filter(function(x){return Number(x)>0;});}catch(e){return [];}}
function setCompare(ids){localStorage.setItem(COMPARE_KEY,JSON.stringify(ids.slice(0,3)));}
function toggleCompare(id){
  var ids=getCompare();
  var n=Number(id);
  var i=ids.indexOf(n);
  if(i>=0)ids.splice(i,1);
  else{
    if(ids.length>=3){alert("You can compare up to 3 listings.");return;}
    ids.push(n);
  }
  setCompare(ids);
  renderCompareTray();
}
function renderCompareTray(){
  var tray=document.getElementById("compareTray");
  if(!tray)return;
  var ids=getCompare();
  if(!ids.length){tray.style.display="none";tray.innerHTML="";return;}
  tray.style.display="block";
  tray.innerHTML="<b>Compare:</b> "+ids.length+" selected"
    +' <a class="ghost-btn" href="/compare?ids='+encodeURIComponent(ids.join(","))+'" style="margin-left:8px;">Open Compare</a>'
    +' <button class="ghost-btn" type="button" id="clearCompare" style="margin-left:8px;">Clear</button>';
  var clear=document.getElementById("clearCompare");
  if(clear)clear.onclick=function(){setCompare([]);renderCompareTray();};
}
function syncSaveSearchForm(){
  var f=currentFilters();
  var m=document.getElementById("saveSearchMaxPrice");
  var l=document.getElementById("saveSearchLocation");
  var b=document.getElementById("saveSearchBeds");
  var c=document.getElementById("saveSearchCategory");
  if(m)m.value=f.maxPrice;
  if(l)l.value=f.location;
  if(b)b.value=f.beds;
  if(c)c.value=f.category;
}
function fetchListings(){
var p=buildParams(currentFilters());
fetch("/api/listings?"+p.toString()).then(function(r){return r.json();}).then(function(data){
if(!data.ok)return;
var wrap=document.getElementById("listingResults");wrap.innerHTML="";
var compare=getCompare();
data.listings.forEach(function(l){
var row=document.createElement("div");row.className="prop-item";
var checked=compare.indexOf(Number(l.id))>=0?"checked":"";
row.innerHTML='<img src="'+escapeHtml(l.image_url)+'" alt="" style="width:68px;height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.14);object-fit:cover;background:rgba(0,0,0,.2);">'
+'<div><div style="font-weight:1000;">'+escapeHtml(l.title)+' &bull; $'+Number(l.price).toLocaleString()+'</div>'
+'<div class="muted" style="font-size:12px;margin-top:4px;">'+escapeHtml(l.location)+' &bull; '+l.beds+' bed / '+l.baths+' bath &bull; '+escapeHtml(l.category)+'</div></div>'
+'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">'
+'<label class="badge" style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" data-compare-id="'+l.id+'" '+checked+'>Compare</label>'
+'<button class="badge" type="button" data-share-url="'+escapeHtml(location.origin+"/listing/"+l.id)+'" data-share-title="'+escapeHtml(l.title)+'">Share</button>'
+'<a class="badge" href="/listing/'+l.id+'" style="text-decoration:none;">View</a>'
+'</div>';
wrap.appendChild(row);});
document.getElementById("resultCount").textContent=data.listings.length+" result(s)";
Array.prototype.forEach.call(document.querySelectorAll("input[data-compare-id]"),function(cb){
  cb.addEventListener("change",function(e){toggleCompare(e.target.getAttribute("data-compare-id"));});
});
syncSaveSearchForm();
renderCompareTray();
}).catch(function(e){console.error(e);});}
document.addEventListener("DOMContentLoaded",function(){
var btn=document.getElementById("applyFilters");
if(btn)btn.addEventListener("click",function(e){e.preventDefault();fetchListings();});
var compareBtn=document.getElementById("openCompare");
if(compareBtn)compareBtn.addEventListener("click",function(){
  var ids=getCompare();
  if(!ids.length){alert("Select listing(s) to compare first.");return;}
  location.href="/compare?ids="+encodeURIComponent(ids.join(","));
});
["maxPrice","location","beds","category"].forEach(function(id){
  var el=document.getElementById(id); if(el)el.addEventListener("change",syncSaveSearchForm);
});
syncSaveSearchForm();
fetchListings();});''',

"site/static/js/leases.js": '''function loadUnits(){
var prop=document.getElementById("propertySelect");
var unitSel=document.getElementById("unitSelect");
if(!prop||!unitSel)return;var propId=prop.value;
unitSel.innerHTML='<option value="">Select...</option>';if(!propId)return;
fetch("/api/units?property_id="+encodeURIComponent(propId)).then(function(r){return r.json();}).then(function(data){
if(!data.ok)return;
data.units.forEach(function(u){var opt=document.createElement("option");opt.value=u.unit_label;
opt.textContent=u.unit_label+(u.is_occupied?" (occupied)":"");opt.disabled=!!u.is_occupied;unitSel.appendChild(opt);});
}).catch(function(e){console.error(e);});}
document.addEventListener("DOMContentLoaded",function(){
var prop=document.getElementById("propertySelect");
if(prop)prop.addEventListener("change",loadUnits);loadUnits();});''',

# â•â•â• SVG placeholders â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"site/static/img/listing1.svg": '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1225"/><stop offset="1" stop-color="#5aa6ff"/></linearGradient></defs><rect width="1200" height="800" fill="url(#bg)"/><circle cx="380" cy="420" r="230" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="6"/><text x="70" y="140" font-size="72" font-family="Segoe UI,Arial" fill="white" font-weight="700">Harborview Apartment</text></svg>''',

"site/static/img/listing2.svg": '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1225"/><stop offset="1" stop-color="#8959ff"/></linearGradient></defs><rect width="1200" height="800" fill="url(#bg)"/><circle cx="380" cy="420" r="230" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="6"/><text x="70" y="140" font-size="72" font-family="Segoe UI,Arial" fill="white" font-weight="700">Palm Grove Cottage</text></svg>''',

"site/static/img/listing3.svg": '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1225"/><stop offset="1" stop-color="#2dd4bf"/></linearGradient></defs><rect width="1200" height="800" fill="url(#bg)"/><circle cx="380" cy="420" r="230" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="6"/><text x="70" y="140" font-size="72" font-family="Segoe UI,Arial" fill="white" font-weight="700">Coral Bay Short Stay</text></svg>''',

"site/static/img/door_hero.svg": r'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1500" viewBox="0 0 900 1500">
  <defs>
    <linearGradient id="bgWall" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#101822"/>
      <stop offset="0.5" stop-color="#1a2532"/>
      <stop offset="1" stop-color="#0e151f"/>
    </linearGradient>
    <radialGradient id="vignette" cx="0.5" cy="0.62" r="0.65">
      <stop offset="0" stop-color="rgba(0,0,0,0)"/>
      <stop offset="1" stop-color="rgba(0,0,0,0.72)"/>
    </radialGradient>
    <linearGradient id="ceilingWood" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#27180f"/>
      <stop offset="0.35" stop-color="#5a3722"/>
      <stop offset="0.7" stop-color="#3b2418"/>
      <stop offset="1" stop-color="#21140e"/>
    </linearGradient>
    <linearGradient id="frameDark" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#233140"/>
      <stop offset="1" stop-color="#121d2a"/>
    </linearGradient>
    <linearGradient id="frameEdge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#3a4f65"/>
      <stop offset="0.45" stop-color="#1a2a3a"/>
      <stop offset="1" stop-color="#4d6780"/>
    </linearGradient>
    <linearGradient id="doorWood" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3a281d"/>
      <stop offset="0.4" stop-color="#5d402b"/>
      <stop offset="1" stop-color="#2b1c14"/>
    </linearGradient>
    <linearGradient id="doorSheen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="rgba(255,220,170,0.06)"/>
      <stop offset="0.5" stop-color="rgba(255,245,220,0.2)"/>
      <stop offset="1" stop-color="rgba(255,220,170,0.06)"/>
    </linearGradient>
    <linearGradient id="groove" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#12161d"/>
      <stop offset="1" stop-color="#2a3642"/>
    </linearGradient>
    <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1f2a35"/>
      <stop offset="0.5" stop-color="#5e6e7c"/>
      <stop offset="1" stop-color="#111a24"/>
    </linearGradient>
    <filter id="softShadow" x="-30%" y="-30%" width="160%" height="180%">
      <feGaussianBlur stdDeviation="16"/>
    </filter>
    <pattern id="ceilingLines" width="14" height="14" patternUnits="userSpaceOnUse">
      <rect width="14" height="14" fill="rgba(0,0,0,0)"/>
      <rect x="0" y="0" width="10" height="14" fill="rgba(0,0,0,0.22)"/>
    </pattern>
    <pattern id="woodLines" width="18" height="18" patternUnits="userSpaceOnUse">
      <rect width="18" height="18" fill="rgba(0,0,0,0)"/>
      <rect x="0" y="0" width="2" height="18" fill="rgba(255,255,255,0.06)"/>
      <rect x="9" y="0" width="1" height="18" fill="rgba(0,0,0,0.22)"/>
    </pattern>
  </defs>

  <rect width="900" height="1500" fill="url(#bgWall)"/>
  <rect x="0" y="0" width="900" height="305" fill="url(#ceilingWood)"/>
  <rect x="0" y="0" width="900" height="305" fill="url(#ceilingLines)" opacity="0.45"/>
  <rect x="0" y="1220" width="900" height="280" fill="#303a43"/>
  <rect x="0" y="1220" width="900" height="280" fill="url(#woodLines)" opacity="0.35"/>

  <rect x="122" y="365" width="656" height="900" rx="8" fill="url(#frameDark)"/>
  <rect x="138" y="381" width="624" height="868" rx="8" fill="none" stroke="url(#frameEdge)" stroke-width="6"/>
  <rect x="164" y="407" width="572" height="816" rx="6" fill="#101720"/>
  <rect x="164" y="407" width="572" height="816" rx="6" fill="rgba(255,255,255,0.03)"/>

  <rect x="190" y="432" width="520" height="768" rx="8" fill="url(#doorWood)"/>
  <rect x="190" y="432" width="520" height="768" rx="8" fill="url(#woodLines)" opacity="0.42"/>
  <rect x="190" y="432" width="520" height="768" rx="8" fill="url(#doorSheen)"/>
  <rect x="190" y="432" width="520" height="768" rx="8" fill="none" stroke="#141b24" stroke-width="5"/>

  <rect x="236" y="492" width="428" height="468" rx="6" fill="none" stroke="#111820" stroke-width="6"/>
  <rect x="244" y="500" width="412" height="452" rx="4" fill="none" stroke="#52687d" stroke-opacity="0.42" stroke-width="2"/>
  <rect x="236" y="994" width="428" height="172" rx="6" fill="none" stroke="#111820" stroke-width="6"/>
  <rect x="244" y="1002" width="412" height="156" rx="4" fill="none" stroke="#52687d" stroke-opacity="0.42" stroke-width="2"/>

  <rect x="278" y="525" width="3" height="402" fill="url(#groove)"/>
  <rect x="306" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="334" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="362" y="525" width="3" height="402" fill="url(#groove)"/>
  <rect x="390" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="418" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="446" y="525" width="3" height="402" fill="url(#groove)"/>
  <rect x="474" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="502" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="530" y="525" width="3" height="402" fill="url(#groove)"/>
  <rect x="558" y="525" width="2" height="402" fill="url(#groove)"/>
  <rect x="586" y="525" width="2" height="402" fill="url(#groove)"/>

  <rect x="278" y="1032" width="3" height="120" fill="url(#groove)"/>
  <rect x="314" y="1032" width="2" height="120" fill="url(#groove)"/>
  <rect x="350" y="1032" width="3" height="120" fill="url(#groove)"/>
  <rect x="386" y="1032" width="2" height="120" fill="url(#groove)"/>
  <rect x="422" y="1032" width="3" height="120" fill="url(#groove)"/>
  <rect x="458" y="1032" width="2" height="120" fill="url(#groove)"/>
  <rect x="494" y="1032" width="3" height="120" fill="url(#groove)"/>
  <rect x="530" y="1032" width="2" height="120" fill="url(#groove)"/>
  <rect x="566" y="1032" width="3" height="120" fill="url(#groove)"/>
  <rect x="602" y="1032" width="2" height="120" fill="url(#groove)"/>

  <rect x="300" y="560" width="14" height="245" rx="4" fill="url(#metal)"/>
  <rect x="302" y="565" width="3" height="230" fill="rgba(255,255,255,0.35)"/>
  <circle cx="312" cy="805" r="2.5" fill="#96a5b3"/>

  <ellipse cx="450" cy="1268" rx="330" ry="32" fill="rgba(0,0,0,0.45)" filter="url(#softShadow)"/>
  <rect width="900" height="1500" fill="url(#vignette)"/>
</svg>''',


"site/templates/forgot_password.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Reset password</h2><p class="muted">Enter your email or username to generate a reset link.</p></div></div>
<div class="card" style="max-width:520px;">
{{message_box}}
<form method="POST" action="/forgot">
<label>Email or Username</label>
<input name="ident" placeholder="you@example.com or username" required>
<button class="btn" type="submit" style="margin-top:12px;">Create reset link</button>
</form>
<div class="muted" style="margin-top:10px;"><a href="/login">Back to login</a></div>
</div></div></section>''',

"site/templates/reset_password.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Choose a new password</h2><p class="muted">Use the link you received to set a new password.</p></div></div>
<div class="card" style="max-width:520px;">
{{message_box}}
<form method="POST" action="/reset">
<input type="hidden" name="token" value="{{token_value}}">
<label>New password</label>
<input type="password" name="password" placeholder="10+ chars with upper/lower/number/symbol" required>
<label>Confirm new password</label>
<input type="password" name="password2" required>
<button class="btn" type="submit" style="margin-top:12px;">Update password</button>
</form>
</div></div></section>''',

"site/templates/profile.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Profile</h2><p class="muted">Manage your account details and password.</p></div></div>
<div class="card" style="max-width:760px;">
{{message_box}}
<form method="POST" action="/profile/update" style="margin-top:12px;">
  <div class="row">
    <div class="field" style="flex:1;"><label>Full name</label><input name="full_name" value="{{full_name}}" required></div>
    <div class="field" style="flex:1;"><label>Phone</label><input name="phone" value="{{phone}}" required></div>
  </div>
  <div class="field" style="margin-top:10px;"><label>Email</label><input type="email" name="email" value="{{email}}" required></div>

  <div class="notice" style="margin-top:12px;"><b>Password change (optional)</b><br><span class="muted">Leave blank to keep existing password.</span></div>
  <div class="field" style="margin-top:10px;"><label>Current password</label><input type="password" name="current_password" autocomplete="current-password"></div>
  <div class="row" style="margin-top:10px;">
    <div class="field" style="flex:1;"><label>New password</label><input type="password" name="new_password" autocomplete="new-password"></div>
    <div class="field" style="flex:1;"><label>Confirm new password</label><input type="password" name="new_password2" autocomplete="new-password"></div>
  </div>
  <button class="primary-btn" style="margin-top:12px;">Save changes</button>
</form>
</div></div></section>''',

"site/templates/tenant_invites.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Property Invites</h2><p class="muted">Accept or decline property confirmation requests from your landlord or manager.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/tenant">Back to Dashboard</a></div></div></div>
{{message_box}}
<div class="card">
  <h3 style="margin-top:0;">Pending Invites</h3>
  {{pending_cards}}
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Current Linked Property</h3>
  {{active_box}}
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Invite History</h3>
  <table class="table"><thead><tr><th>ID</th><th>Property</th><th>Unit</th><th>From</th><th>Status</th><th>Sent</th><th>Responded</th></tr></thead><tbody>{{history_rows}}</tbody></table>
  {{history_empty}}
</div>
</div></section>''',

"site/templates/landlord_tenants.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Tenant Sync</h2><p class="muted">Send property confirmation invites to tenants and track active links.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/landlord">Back to Dashboard</a></div></div></div>
{{message_box}}
<div class="card" style="max-width:980px;">
  <h3 style="margin-top:0;">Send Invite</h3>
  <form method="POST" action="/landlord/tenant/invite">
    <div class="row">
      <div class="field" style="flex:1;"><label>Tenant (Account, Username, or Email)</label><input name="tenant_ident" required placeholder="A12345 or username"></div>
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" id="landlordTenantPropertySelect" required><option value="">Select...</option>{{property_options}}</select></div>
    </div>
    <div class="row" style="margin-top:10px;">
      <div class="field" style="flex:1;"><label>Unit Label</label><select name="unit_label" id="landlordTenantUnitSelect" required><option value="">Select property first...</option></select></div>
      <div class="field" style="flex:1;"><label>Message (optional)</label><input name="message" placeholder="Please confirm this property assignment."></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Send Confirmation Invite</button>
  </form>
  <div class="muted" style="margin-top:10px;">Tip: Units are auto-loaded from selected property.</div>
</div>
<div class="card" style="max-width:980px;margin-top:12px;">
  <h3 style="margin-top:0;">Submit All Units for Listing</h3>
  <form method="POST" action="/landlord/listing/submit_all">
    <div class="row">
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" required><option value="">Select...</option>{{property_options}}</select></div>
      <div class="field" style="flex:1;"><label>Category</label><select name="category" required><option value="Long Term Rental">Long Term Rental</option><option value="Short Term Rental">Short Term Rental</option><option value="Vehicle Rental">Vehicle Rental</option><option value="Sell Your Property to Us">Sell Your Property to Us</option></select></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Submit All Units</button>
  </form>
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Active Tenant Links</h3>
  <table class="table"><thead><tr><th>Tenant</th><th>Account</th><th>Property</th><th>Unit</th><th>Start</th><th>Action</th></tr></thead><tbody>{{active_rows}}</tbody></table>
  {{active_empty}}
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Invite Status</h3>
  <table class="table"><thead><tr><th>ID</th><th>Tenant</th><th>Property</th><th>Unit</th><th>Status</th><th>Sent</th><th>Responded</th><th>Actions</th></tr></thead><tbody>{{invite_rows}}</tbody></table>
  {{invite_empty}}
</div>
</div></section>''',

"site/templates/manager_tenants.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Tenant Sync</h2><p class="muted">Invite tenants to properties and remove tenant links when needed.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
{{message_box}}
<div class="card" style="max-width:980px;">
  <h3 style="margin-top:0;">Send Invite</h3>
  <form method="POST" action="/manager/tenant/invite">
    <div class="row">
      <div class="field" style="flex:1;"><label>Tenant (Account, Username, or Email)</label><input name="tenant_ident" required placeholder="A12345 or username"></div>
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" id="managerTenantPropertySelect" required><option value="">Select...</option>{{property_options}}</select></div>
    </div>
    <div class="row" style="margin-top:10px;">
      <div class="field" style="flex:1;"><label>Unit Label</label><select name="unit_label" id="managerTenantUnitSelect" required><option value="">Select property first...</option></select></div>
      <div class="field" style="flex:1;"><label>Message (optional)</label><input name="message" placeholder="Please confirm this property assignment."></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Send Confirmation Invite</button>
  </form>
</div>
<div class="card" style="max-width:980px;margin-top:12px;">
  <h3 style="margin-top:0;">Submit All Units for Listing</h3>
  <form method="POST" action="/manager/listing/submit_all">
    <div class="row">
      <div class="field" style="flex:1;"><label>Property</label><select name="property_id" required><option value="">Select...</option>{{property_options}}</select></div>
      <div class="field" style="flex:1;"><label>Category</label><select name="category" required><option value="Long Term Rental">Long Term Rental</option><option value="Short Term Rental">Short Term Rental</option><option value="Vehicle Rental">Vehicle Rental</option><option value="Sell Your Property to Us">Sell Your Property to Us</option></select></div>
    </div>
    <button class="primary-btn" style="margin-top:12px;">Submit All Units</button>
  </form>
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Active Tenant Links</h3>
  <table class="table"><thead><tr><th>Tenant</th><th>Account</th><th>Property</th><th>Unit</th><th>Start</th><th>Action</th></tr></thead><tbody>{{active_rows}}</tbody></table>
  {{active_empty}}
</div>
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Invite Status</h3>
  <table class="table"><thead><tr><th>ID</th><th>Tenant</th><th>Property</th><th>Unit</th><th>Status</th><th>Sent</th><th>Responded</th><th>Actions</th></tr></thead><tbody>{{invite_rows}}</tbody></table>
  {{invite_empty}}
</div>
</div></section>''',

"site/templates/messages.html": '''<section class="dash"><div class="container">
<div class="dash-top">
<div><h2>Messages</h2><p class="muted">Threaded messages with read state and attachments.</p></div>
<a class="ghost-btn" href="/notifications">View alerts</a>
</div>
<div class="notice"><b>Threaded messages</b> are live. Start a thread or continue an existing one.</div>
{{message_box}}
<div class="grid2" style="margin-top:10px;">
  <div class="card">
    <h3 style="margin-top:0;">Start Thread</h3>
    <form method="POST" action="/messages/new" enctype="multipart/form-data">
      <div class="field"><label>Recipient (username/email/account)</label><input name="recipient" required placeholder="username"></div>
      <div class="field"><label>Subject</label><input name="subject" required placeholder="Lease reminder"></div>
      <div class="row">
        <div class="field" style="flex:1;"><label>Context Type</label><select name="context_type"><option value="">General</option><option value="listing">Listing</option><option value="property">Property</option><option value="maintenance">Maintenance</option></select></div>
        <div class="field" style="flex:1;"><label>Context ID</label><input name="context_id" placeholder="Optional"></div>
      </div>
      <div class="field"><label>Message</label><textarea name="body" required placeholder="Type your message..."></textarea></div>
      <div class="field"><label>Attachment (optional)</label><input type="file" name="attachment" accept=".pdf,.jpg,.jpeg,.png,.webp,.txt"></div>
      <button class="primary-btn" type="submit">Send</button>
    </form>
  </div>
  <div class="card">
    <h3 style="margin-top:0;">My Threads</h3>
    {{threads_rows}}
    {{threads_empty}}
  </div>
</div>
{{thread_view}}
</div></section>''',

"site/templates/error.html": '''<section class="public"><div class="public-inner">
<div class="card" style="max-width:640px;">
  <div class="muted">{{status_code}}</div>
  <h2 style="margin-top:6px;">{{error_title}}</h2>
  <p class="muted" style="margin-top:8px;">{{error_message}}</p>
  <div class="row" style="margin-top:14px;">
    <a class="primary-btn" href="/">Go Home</a>
    <a class="ghost-btn" href="/login">Log in</a>
  </div>
</div></div></section>''',

"site/templates/favorites.html": '''<section class="dash"><div class="container">
<div class="dash-top">
<div><h2>Favorites</h2><p class="muted">Saved listings for quick access.</p></div>
<a class="ghost-btn" href="/listings">Browse listings</a>
</div>
{{favorites_html}}
</div></section>''',

"site/templates/notifications.html": '''<section class="dash"><div class="container">
<div class="dash-top">
<div><h2>Alerts</h2><p class="muted">Updates on applications, maintenance, and account activity.</p></div>
<div class="row" style="margin:0;"><a class="ghost-btn" href="/notifications/preferences">Preferences</a><a class="ghost-btn" href="/onboarding">Onboarding</a><form method="POST" action="/notifications/readall" class="row" style="margin:0;"><button class="ghost-btn" type="submit">Mark all read</button></form></div>
</div>
{{notifications_html}}
</div></section>''',

"site/templates/notifications_preferences.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Notification Preferences</h2><p class="muted">Choose which alerts you want and how they should be delivered.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/notifications">Back to Alerts</a></div></div></div>
{{message_box}}
<div class="card" style="max-width:920px;">
  <form method="POST" action="/notifications/preferences">
    <h3 style="margin-top:0;">Alert Types</h3>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="payment_events" value="1" {{payment_events_checked}}> Payment reminders and payment status updates</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="maintenance_events" value="1" {{maintenance_events_checked}}> Maintenance request and assignment updates</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="lease_events" value="1" {{lease_events_checked}}> Lease changes, signatures, and expiration events</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="invite_events" value="1" {{invite_events_checked}}> Invite and tenant-sync alerts</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="application_events" value="1" {{application_events_checked}}> Application review updates</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="inquiry_events" value="1" {{inquiry_events_checked}}> Listing inquiry updates</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="system_events" value="1" {{system_events_checked}}> System/profile/security notices</label>
    <h3 style="margin-top:14px;">Delivery</h3>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="email_enabled" value="1" {{email_enabled_checked}}> Email notifications (when SMTP is configured)</label>
    <label style="display:flex;gap:8px;align-items:center;margin:6px 0;"><input type="checkbox" name="sms_enabled" value="1" {{sms_enabled_checked}}> SMS notifications (placeholder)</label>
    <button class="primary-btn" style="margin-top:12px;">Save Preferences</button>
  </form>
</div>
</div></section>''',

"site/templates/onboarding.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Onboarding Checklist</h2><p class="muted">Track setup progress for your role and complete the key first-use steps.</p><div style="margin-top:10px;"><a class="ghost-btn" href="{{home_path}}">Back to Dashboard</a></div></div></div>
{{message_box}}
{{summary_box}}
<div class="card" style="max-width:980px;">
  <h3 style="margin-top:0;">Checklist</h3>
  <div style="display:grid;gap:10px;">{{steps_rows}}</div>
</div>
</div></section>''',

"site/templates/manager_analytics.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Manager Analytics</h2><p class="muted">Operational KPIs for maintenance, collections, occupancy, and pipeline backlog.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div></div>
{{message_box}}
{{kpi_cards}}
<div class="card" style="margin-top:12px;">
  <h3 style="margin-top:0;">Quick Notes</h3>
  <div class="muted">Use this page to spot aging tasks, late collections, and response bottlenecks before they become escalations.</div>
</div>
</div></section>''',

"site/templates/inquiry_thanks.html": '''<section class="public"><div class="public-inner">
<div class="card" style="max-width:620px;">
{{message_box}}
<div class="row" style="margin-top:12px;gap:10px;">
{{back_to_listing}}
<a class="btn" href="/listings">Back to Listings</a>
<a class="btn ghost" href="/">Home</a>
</div>
</div></div></section>''',

"site/templates/apply_thanks.html": '''<section class="public"><div class="public-inner">
<div class="card" style="max-width:620px;">
{{message_box}}
<div class="row" style="margin-top:12px;gap:10px;">
{{back_to_listing}}
<a class="btn" href="/listings">Browse more</a>
<a class="btn ghost" href="/notifications">View Alerts</a>
</div>
</div></div></section>''',

"site/templates/manager_inquiries.html": '''<section class="dash"><div class="container">
<div class="dash-top">
<div><h2>Inquiries</h2><p class="muted">Guest/tenant questions from listing pages.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div>
</div>
{{message_box}}
<div class="row" style="margin-bottom:10px;"><a class="ghost-btn" href="{{export_filtered_url}}">Export Filtered CSV</a></div>
{{filters_form}}
{{inquiries_html}}
{{pager_box}}
</div></section>''',

"site/templates/manager_applications.html": '''<section class="dash"><div class="container">
<div class="dash-top">
<div><h2>Applications</h2><p class="muted">Review and update application status.</p><div style="margin-top:10px;"><a class="ghost-btn" href="/manager">Back to Dashboard</a></div></div>
</div>
{{message_box}}
<div class="row" style="margin-bottom:10px;"><a class="ghost-btn" href="{{export_filtered_url}}">Export Filtered CSV</a></div>
{{filters_form}}
{{applications_html}}
{{pager_box}}
</div></section>''',


"site/templates/manager_listings.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Manage Listings</h2><p class="muted">Approve/reject, edit, and mark listings as available or rented.</p></div></div>
<div class="card">
<div style="overflow:auto">
<table class="table">
<thead><tr><th>ID</th><th>Title</th><th>Location</th><th>Price</th><th>Approved</th><th>Available</th><th>Actions</th></tr></thead>
<tbody>
{{listings_rows}}
</tbody>
</table>
</div>
</div>
</div></section>''',

"site/templates/manager_listing_edit.html": '''<section class="public"><div class="public-inner">
<div class="public-header"><div><h2>Edit Listing #{{listing_id}}</h2><p class="muted">Update details and manage photos.</p></div><a class="ghost-btn" href="/manager/listings">Back</a></div>

<div class="grid2">
  <div class="card">
    <h3 style="margin-top:0;">Details</h3>
    <form method="POST" action="/manager/listings/edit">
      <input type="hidden" name="listing_id" value="{{listing_id}}">
      <div><label>Title</label><input name="title" value="{{listing_title}}" required></div>
      <div class="grid2">
        <div><label>Price</label><input name="price" value="{{price}}" required></div>
        <div><label>Location</label><input name="location" value="{{location}}" required></div>
      </div>
      <div class="grid2">
        <div><label>Beds</label><input name="beds" value="{{beds}}" required></div>
        <div><label>Baths</label><input name="baths" value="{{baths}}" required></div>
      </div>
      <div><label>Category</label>
        <select name="category">
          <option {{cat_short}}>Short Term Rental</option>
          <option {{cat_long}}>Long Term Rental</option>
          <option {{cat_vehicle}}>Vehicle Rental</option>
          <option {{cat_sell}}>Sell Your Property to Us</option>
        </select>
      </div>
      <div><label>Description</label><textarea name="description" rows="5" required>{{description}}</textarea></div>
      <div class="row" style="margin-top:12px;gap:10px;flex-wrap:wrap;">
        <button class="btn" type="submit">Save changes</button>
        <a class="btn ghost" href="/manager/listings">Cancel</a>
      </div>
    </form>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">Photos</h3>
    <p class="muted">Upload up to 5 images at a time (JPG/PNG/WEBP, max 5MB each). Set one as thumbnail.</p>
    <form method="POST" action="/manager/listings/photos" enctype="multipart/form-data">
      <input type="hidden" name="listing_id" value="{{listing_id}}">
      <div class="grid2">
        <div><input type="file" name="photo1" accept="image/*"></div>
        <div><input type="file" name="photo2" accept="image/*"></div>
        <div><input type="file" name="photo3" accept="image/*"></div>
        <div><input type="file" name="photo4" accept="image/*"></div>
        <div><input type="file" name="photo5" accept="image/*"></div>
      </div>
      <div class="row" style="margin-top:10px;">
        <button class="btn" type="submit">Upload</button>
      </div>
    </form>

    <div style="margin-top:14px;">
      {{photos_admin}}
    </div>
  </div>
</div>
</div></section>''',

}  # end EMBEDDED_FILES


def bootstrap_files():
    overwrite = str(os.getenv("BOOTSTRAP_OVERWRITE", "0")).strip().lower() in ("1", "true", "yes", "on")
    n_written = 0
    n_skipped = 0
    for rel, content in EMBEDDED_FILES.items():
        fp = BASE_DIR / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        if fp.exists() and not overwrite:
            n_skipped += 1
            continue
        fp.write_text(content, encoding="utf-8")
        n_written += 1
    log_event(
        logging.INFO,
        "bootstrap_files",
        written=n_written,
        skipped=n_skipped,
        overwrite=overwrite,
        site_dir=str(SITE_DIR),
    )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  DATABASE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
SCHEMA = """PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,phone TEXT NOT NULL,email TEXT NOT NULL,username TEXT NOT NULL UNIQUE,password_salt TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN('tenant','property_manager','admin')),account_number TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at TEXT NOT NULL,ip_hash TEXT,user_agent_hash TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS listings(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,price INTEGER NOT NULL,location TEXT NOT NULL,beds INTEGER NOT NULL,baths INTEGER NOT NULL,category TEXT NOT NULL CHECK(category IN('Short Term Rental','Long Term Rental','Vehicle Rental','Sell Your Property to Us')),image_url TEXT NOT NULL,description TEXT NOT NULL,is_approved INTEGER NOT NULL DEFAULT 1,is_available INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS listing_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_id INTEGER,title TEXT NOT NULL,price INTEGER NOT NULL,location TEXT NOT NULL,beds INTEGER NOT NULL,baths INTEGER NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('pending','approved','rejected')) DEFAULT 'pending',submitted_by_user_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),approval_note TEXT,review_state TEXT NOT NULL DEFAULT 'initial',checklist_photos INTEGER NOT NULL DEFAULT 0,checklist_price INTEGER NOT NULL DEFAULT 0,checklist_description INTEGER NOT NULL DEFAULT 0,checklist_docs INTEGER NOT NULL DEFAULT 0,reviewed_at TEXT,resubmission_count INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(unit_id)REFERENCES units(id)ON DELETE SET NULL,FOREIGN KEY(submitted_by_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS properties(id TEXT PRIMARY KEY,owner_account TEXT NOT NULL,name TEXT NOT NULL,property_type TEXT NOT NULL CHECK(property_type IN('House','Apartment')),units_count INTEGER NOT NULL,location TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(owner_account)REFERENCES users(account_number)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_label TEXT NOT NULL,beds INTEGER NOT NULL DEFAULT 1,baths INTEGER NOT NULL DEFAULT 1,rent INTEGER NOT NULL DEFAULT 0,is_occupied INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tenant_leases(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_account TEXT NOT NULL,property_id TEXT NOT NULL,unit_label TEXT NOT NULL,start_date TEXT NOT NULL DEFAULT(date('now')),end_date TEXT,is_active INTEGER NOT NULL DEFAULT 1,manager_signed_at TEXT,tenant_signed_at TEXT,esign_ip TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE,FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,payer_account TEXT NOT NULL,payer_role TEXT NOT NULL CHECK(payer_role IN('tenant','property_manager','landlord','manager')),payment_type TEXT NOT NULL CHECK(payment_type IN('rent','bill')),provider TEXT,amount INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN('submitted','paid','failed')),created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(payer_account)REFERENCES users(account_number)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS payment_methods(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_user_id INTEGER NOT NULL,method_type TEXT NOT NULL CHECK(method_type IN('card','bank')),brand_label TEXT NOT NULL,last4 TEXT NOT NULL,is_default INTEGER NOT NULL DEFAULT 0,is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(tenant_user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tenant_autopay(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_user_id INTEGER NOT NULL UNIQUE,payment_method_id INTEGER,is_enabled INTEGER NOT NULL DEFAULT 0,payment_day INTEGER NOT NULL DEFAULT 1,notify_days_before INTEGER NOT NULL DEFAULT 3,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(tenant_user_id)REFERENCES users(id)ON DELETE CASCADE,FOREIGN KEY(payment_method_id)REFERENCES payment_methods(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS maintenance_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_account TEXT NOT NULL,tenant_name TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','in_progress','closed')),assigned_to TEXT,urgency TEXT NOT NULL DEFAULT 'normal',created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS maintenance_staff(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT,phone TEXT,is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS property_checks(id INTEGER PRIMARY KEY AUTOINCREMENT,requester_account TEXT NOT NULL,property_id TEXT NOT NULL,preferred_date TEXT NOT NULL,notes TEXT,status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN('requested','scheduled','completed','cancelled')),created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(requester_account)REFERENCES users(account_number)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS inspections(id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_label TEXT NOT NULL,tenant_account TEXT,inspection_type TEXT NOT NULL CHECK(inspection_type IN('move_in','move_out')),scheduled_date TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN('scheduled','completed','cancelled')),checklist_json TEXT,report_notes TEXT,completed_at TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE,FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE SET NULL,FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS preventive_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_label TEXT,task TEXT NOT NULL,frequency_days INTEGER NOT NULL,next_due_date TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','completed','cancelled')),assigned_staff_id INTEGER,last_completed_at TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE,FOREIGN KEY(assigned_staff_id)REFERENCES maintenance_staff(id)ON DELETE SET NULL,FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS tenant_property_invites(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_user_id INTEGER NOT NULL,tenant_user_id INTEGER NOT NULL,tenant_account TEXT NOT NULL,property_id TEXT NOT NULL,unit_label TEXT NOT NULL,message TEXT,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','accepted','declined','cancelled')),created_at TEXT NOT NULL DEFAULT(datetime('now')),responded_at TEXT,FOREIGN KEY(sender_user_id)REFERENCES users(id)ON DELETE CASCADE,FOREIGN KEY(tenant_user_id)REFERENCES users(id)ON DELETE CASCADE,FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS lease_roommates(id INTEGER PRIMARY KEY AUTOINCREMENT,lease_id INTEGER NOT NULL,tenant_account TEXT NOT NULL,share_percent INTEGER NOT NULL CHECK(share_percent>0 AND share_percent<=100),status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','removed')),created_at TEXT NOT NULL DEFAULT(datetime('now')),UNIQUE(lease_id,tenant_account),FOREIGN KEY(lease_id)REFERENCES tenant_leases(id)ON DELETE CASCADE,FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS password_resets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,token TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,used INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER NOT NULL,listing_id INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(user_id,listing_id),FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE,FOREIGN KEY(listing_id)REFERENCES listings(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS inquiries(id INTEGER PRIMARY KEY AUTOINCREMENT,listing_id INTEGER,full_name TEXT NOT NULL,email TEXT NOT NULL,phone TEXT,subject TEXT,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'new' CHECK(status IN('new','open','closed')),created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(listing_id)REFERENCES listings(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT,listing_id INTEGER NOT NULL,applicant_user_id INTEGER,full_name TEXT NOT NULL,email TEXT NOT NULL,phone TEXT,income TEXT,notes TEXT,status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN('submitted','under_review','approved','denied')),created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(listing_id)REFERENCES listings(id)ON DELETE CASCADE,FOREIGN KEY(applicant_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS uploads(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_user_id INTEGER,kind TEXT NOT NULL,related_table TEXT,related_id INTEGER,related_key TEXT,path TEXT NOT NULL,mime TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(owner_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,text TEXT NOT NULL,link TEXT,is_read INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_user_id INTEGER,actor_role TEXT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,details TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(actor_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS saved_searches(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT,query_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS role_permissions(role TEXT NOT NULL,action TEXT NOT NULL,allowed INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(role,action));
CREATE TABLE IF NOT EXISTS message_threads(id INTEGER PRIMARY KEY AUTOINCREMENT,subject TEXT NOT NULL,context_type TEXT,context_id TEXT,created_by_user_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS message_participants(thread_id INTEGER NOT NULL,user_id INTEGER NOT NULL,last_read_at TEXT,is_archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(thread_id,user_id),FOREIGN KEY(thread_id)REFERENCES message_threads(id)ON DELETE CASCADE,FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS message_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,thread_id INTEGER NOT NULL,sender_user_id INTEGER NOT NULL,body TEXT NOT NULL,attachment_path TEXT,attachment_name TEXT,attachment_mime TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),FOREIGN KEY(thread_id)REFERENCES message_threads(id)ON DELETE CASCADE,FOREIGN KEY(sender_user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tenant_ledger_entries(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_account TEXT NOT NULL,property_id TEXT,unit_label TEXT,lease_id INTEGER,entry_type TEXT NOT NULL CHECK(entry_type IN('charge','payment','late_fee','adjustment')),category TEXT NOT NULL,amount INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN('open','paid','void','submitted','failed')) DEFAULT 'open',due_date TEXT,statement_month TEXT,note TEXT,source_payment_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE,FOREIGN KEY(lease_id)REFERENCES tenant_leases(id)ON DELETE SET NULL,FOREIGN KEY(source_payment_id)REFERENCES payments(id)ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS notification_preferences(user_id INTEGER PRIMARY KEY,payment_events INTEGER NOT NULL DEFAULT 1,maintenance_events INTEGER NOT NULL DEFAULT 1,lease_events INTEGER NOT NULL DEFAULT 1,invite_events INTEGER NOT NULL DEFAULT 1,application_events INTEGER NOT NULL DEFAULT 1,inquiry_events INTEGER NOT NULL DEFAULT 1,system_events INTEGER NOT NULL DEFAULT 1,email_enabled INTEGER NOT NULL DEFAULT 1,sms_enabled INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS user_onboarding(user_id INTEGER PRIMARY KEY,role TEXT NOT NULL,checklist_json TEXT NOT NULL DEFAULT '{}',completed_at TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_tp_invites_tenant_status ON tenant_property_invites(tenant_account,status,created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_user_id,created_at);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches(user_id,created_at);
CREATE INDEX IF NOT EXISTS idx_role_permissions_action ON role_permissions(action,role);
CREATE INDEX IF NOT EXISTS idx_listing_requests_status_created ON listing_requests(status,created_at,id);
CREATE INDEX IF NOT EXISTS idx_payments_payer_created ON payments(payer_account,created_at,id);
CREATE INDEX IF NOT EXISTS idx_payments_status_created ON payments(status,created_at,id);
CREATE INDEX IF NOT EXISTS idx_payment_methods_user_default ON payment_methods(tenant_user_id,is_default,id);
CREATE INDEX IF NOT EXISTS idx_tenant_autopay_enabled ON tenant_autopay(is_enabled,payment_day,id);
CREATE INDEX IF NOT EXISTS idx_msg_participants_user ON message_participants(user_id,thread_id);
CREATE INDEX IF NOT EXISTS idx_msg_posts_thread_created ON message_posts(thread_id,created_at,id);
CREATE INDEX IF NOT EXISTS idx_ledger_tenant_created ON tenant_ledger_entries(tenant_account,created_at,id);
CREATE INDEX IF NOT EXISTS idx_ledger_tenant_month ON tenant_ledger_entries(tenant_account,statement_month,entry_type,id);
CREATE INDEX IF NOT EXISTS idx_ledger_payment_src ON tenant_ledger_entries(source_payment_id);
CREATE INDEX IF NOT EXISTS idx_notification_prefs_email ON notification_preferences(email_enabled,user_id);
CREATE INDEX IF NOT EXISTS idx_user_onboarding_role ON user_onboarding(role,user_id);
CREATE INDEX IF NOT EXISTS idx_inspections_property_date ON inspections(property_id,scheduled_date,id);
CREATE INDEX IF NOT EXISTS idx_preventive_due_status ON preventive_tasks(next_due_date,status,id);
CREATE INDEX IF NOT EXISTS idx_roommates_tenant_status ON lease_roommates(tenant_account,status,id);
"""

def db():
    # SQLite remains default; if POSTGRES_DSN is set, db.py routes to PostgreSQL.
    if connect_db is not None:
        return connect_db(DATABASE_PATH)
    c = sqlite3.connect(DATABASE_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c

def db_write_retry(fn, retries=5, delay=0.15):
    last = None
    for i in range(retries):
        c = db()
        try:
            result = fn(c)
            c.commit()
            return result
        except DBOperationalError as e:
            last = e
            if "locked" in str(e).lower() and i < (retries - 1):
                time.sleep(delay * (i + 1))
                continue
            raise
        finally:
            try:
                c.close()
            except Exception:
                pass
    if last:
        raise last

def pw_hash(password,salt):
    return hashlib.pbkdf2_hmac("sha256",password.encode(),salt,200000).hex()

NOTIFICATION_PREF_KEYS = (
    "payment_events",
    "maintenance_events",
    "lease_events",
    "invite_events",
    "application_events",
    "inquiry_events",
    "system_events",
    "email_enabled",
    "sms_enabled",
)

ONBOARDING_STEPS = {
    "tenant": [
        ("profile", "Complete profile details", "/profile"),
        ("pay_rent", "Submit first rent payment", "/tenant/pay-rent"),
        ("maintenance", "Submit a maintenance request", "/tenant/maintenance/new"),
        ("lease", "Review lease details", "/tenant/lease"),
        ("alerts", "Review alerts and preferences", "/notifications/preferences"),
    ],
    "property_manager": [
        ("profile", "Complete profile details", "/profile"),
        ("property", "Register first property", "/manager/property/new"),
        ("leases", "Assign a lease", "/manager/leases"),
        ("queue", "Review manager queue", "/manager/queue"),
        ("listing_submit", "Submit a listing request", "/manager/listing-requests"),
    ],
    "admin": [
        ("profile", "Complete profile details", "/profile"),
        ("permissions", "Review role permissions", "/admin/permissions"),
        ("submissions", "Process pending submissions", "/admin/submissions"),
        ("audit", "Review audit log", "/admin/audit"),
        ("users", "Review user roles", "/admin/users"),
    ],
}

def password_policy_errors(password):
    pw = str(password or "")
    errs = []
    if len(pw) < 10:
        errs.append("minimum 10 characters")
    if not re.search(r"[A-Z]", pw):
        errs.append("at least one uppercase letter")
    if not re.search(r"[a-z]", pw):
        errs.append("at least one lowercase letter")
    if not re.search(r"[0-9]", pw):
        errs.append("at least one number")
    if not re.search(r"[^A-Za-z0-9]", pw):
        errs.append("at least one symbol")
    return errs


def _salt_bytes(v):
    # Backwards-compatible: old DBs might store salt as BLOB/bytes or non-hex strings.
    if v is None:
        return b""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v)
    if isinstance(v, str):
        s = v.strip()
        # Prefer hex decoding when it looks like hex; otherwise treat as utf-8.
        try:
            if len(s) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", s or ""):
                return bytes.fromhex(s)
        except Exception:
            pass
        return s.encode("utf-8", "replace")
    return str(v).encode("utf-8", "replace")


def make_acct(c):
    import random
    while True:
        a=f"A{random.randint(0,99999):05d}"
        if not c.execute("SELECT 1 FROM users WHERE account_number=?",(a,)).fetchone():return a

def create_user(c,fn,ph,em,un,pw,rl):
    s=secrets.token_bytes(16);h=pw_hash(pw,s);a=make_acct(c)
    c.execute("INSERT INTO users(full_name,phone,email,username,password_salt,password_hash,role,account_number)VALUES(?,?,?,?,?,?,?,?)",(fn,ph,em,un,s.hex(),h,rl,a));c.commit();return a

def seed_demo_users_for_local_testing(c):
    demo_users = [
        ("AtlasBahamas Admin", "2420000001", "admin@atlasbahamas.local", "admin1", "AtlasAdmin!1", "admin"),
        ("AtlasBahamas Manager", "2420000002", "manager@atlasbahamas.local", "manager1", "AtlasManager!1", "property_manager"),
        ("AtlasBahamas Landlord", "2420000003", "landlord@atlasbahamas.local", "landlord1", "AtlasLandlord!1", "property_manager"),
        ("AtlasBahamas Tenant", "2420000004", "tenant@atlasbahamas.local", "tenant1", "AtlasTenant!1", "tenant"),
    ]
    for full_name, phone, email, username, password, role in demo_users:
        exists = c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            continue
        create_user(c, full_name, phone, email, username, password, role)

    listing_exists = c.execute("SELECT 1 FROM listings LIMIT 1").fetchone()
    if not listing_exists:
        c.execute(
            "INSERT INTO listings(title,price,location,beds,baths,category,image_url,description,is_approved,is_available)VALUES(?,?,?,?,?,?,?,?,1,1)",
            (
                "Nassau Harbor Condo",
                2500,
                "Nassau",
                2,
                2,
                "Long Term Rental",
                "/static/img/door_hero.svg",
                "Demo listing for local validation.",
            ),
        )
        c.commit()

def seed(c):
    if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        pw_errs = password_policy_errors(BOOTSTRAP_ADMIN_PASSWORD)
        if BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PHONE and not pw_errs:
            create_user(
                c,
                BOOTSTRAP_ADMIN_FULL_NAME,
                BOOTSTRAP_ADMIN_PHONE,
                BOOTSTRAP_ADMIN_EMAIL,
                BOOTSTRAP_ADMIN_USERNAME,
                BOOTSTRAP_ADMIN_PASSWORD,
                "admin",
            )
            log_event(logging.INFO, "bootstrap_admin_created", username=BOOTSTRAP_ADMIN_USERNAME)
        elif SEED_DEMO_DATA and not PROD_MODE:
            seed_demo_users_for_local_testing(c)
            log_event(logging.WARNING, "demo_seed_enabled", detail="Seeded local demo users; disable SEED_DEMO_DATA outside local test runs.")
        elif SEED_DEMO_DATA and PROD_MODE:
            log_event(logging.WARNING, "demo_seed_blocked", detail="Refusing demo seed while PROD_MODE=1.")
        else:
            log_event(logging.WARNING, "no_admin_seeded", detail="Set BOOTSTRAP_ADMIN_* env vars to create initial admin account.")

def _ensure_postgres_schema(c):
    statements = []
    for raw in SCHEMA.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        if stmt.upper().startswith("PRAGMA "):
            continue
        statements.append(stmt)

    pending = list(statements)
    passes = 0
    max_passes = 8

    while pending:
        passes += 1
        progressed = False
        remaining = []

        for stmt in pending:
            try:
                c.execute(stmt)
                c.commit()
                progressed = True
            except Exception as e:
                try:
                    c.rollback()
                except Exception:
                    pass

                msg = str(e).lower()
                dependency_missing = (
                    ("does not exist" in msg and ("relation" in msg or "table" in msg))
                    or "undefined_table" in msg
                )

                if dependency_missing and passes < max_passes:
                    remaining.append(stmt)
                    continue

                raise RuntimeError(f"postgres_schema_stmt_failed: {stmt} | error={e}") from e

        if not remaining:
            return
        if not progressed:
            raise RuntimeError("postgres_schema_init_failed_unresolved_dependencies")

        pending = remaining


def _postgres_migrations_dir():
    candidates = [
        BASE_DIR.joinpath(*POSTGRES_MIGRATIONS_REL),
        BASE_DIR.parent.joinpath(*POSTGRES_MIGRATIONS_REL),
    ]
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            return cand
    # Default to project-root location when creating new migrations.
    return candidates[-1]


def _split_sql_statements(sql_text):
    text = str(sql_text or "")
    out = []
    buf = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                buf.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not in_single and not in_double:
            if ch == "-" and nxt == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

        if ch == "'" and not in_double:
            buf.append(ch)
            if in_single and nxt == "'":
                buf.append(nxt)
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _load_postgres_migrations():
    mig_dir = _postgres_migrations_dir()
    files = []
    if not mig_dir.exists():
        return mig_dir, files
    for fp in mig_dir.glob("*.sql"):
        prefix = fp.name.split("_", 1)[0].split("-", 1)[0]
        if not prefix.isdigit():
            continue
        files.append((int(prefix), fp))
    files.sort(key=lambda item: (item[0], item[1].name.lower()))
    seen = {}
    for ver, fp in files:
        if ver in seen:
            raise RuntimeError(
                f"postgres_migration_duplicate_version={ver} files={seen[ver].name},{fp.name}"
            )
        seen[ver] = fp
    return mig_dir, files


def _ensure_schema_meta(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta("
        "key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT(datetime('now')))"
    )


def _set_schema_version(c, version):
    ver = str(to_int(version, 0))
    c.execute(
        "INSERT INTO schema_meta(key,value,updated_at)VALUES('schema_version',?,datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=datetime('now')",
        (ver,),
    )


def _get_schema_version(c):
    _ensure_schema_meta(c)
    row = c.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    if not row:
        return 0
    try:
        return to_int(row["value"], 0)
    except Exception:
        try:
            return to_int(row[0], 0)
        except Exception:
            return 0


def _apply_postgres_migrations(c):
    _ensure_schema_meta(c)
    current = _get_schema_version(c)
    mig_dir, files = _load_postgres_migrations()
    if not files:
        # Keep compatibility with older deployments that bootstrap purely from SCHEMA.
        if current < to_int(SCHEMA_VERSION, 0):
            _set_schema_version(c, SCHEMA_VERSION)
        log_event(
            logging.INFO,
            "postgres_migrations_skipped",
            reason="no_sql_migrations_found",
            directory=str(mig_dir),
            version=_get_schema_version(c),
        )
        return

    for ver, fp in files:
        if ver <= current:
            continue
        sql_text = fp.read_text(encoding="utf-8")
        statements = _split_sql_statements(sql_text)
        for stmt in statements:
            c.execute(stmt)
        _set_schema_version(c, ver)
        current = ver
        log_event(logging.INFO, "postgres_migration_applied", version=ver, file=fp.name)

    if current < to_int(SCHEMA_VERSION, 0):
        _set_schema_version(c, SCHEMA_VERSION)
        log_event(
            logging.INFO,
            "postgres_schema_version_synced",
            version=to_int(SCHEMA_VERSION, 0),
            reason="schema_bootstrap_without_targeted_sql",
        )


def ensure_db():
    DATA_DIR.mkdir(parents=True,exist_ok=True);UPLOAD_DIR.mkdir(parents=True,exist_ok=True);
    c = db()
    pg_lock_acquired = False
    try:
        if postgres_enabled():
            # Prevent concurrent worker bootstrap races when Gunicorn forks multiple workers.
            try:
                c.execute("SELECT pg_advisory_lock(67002131)")
                c.commit()
                pg_lock_acquired = True
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass

            _ensure_postgres_schema(c);c.commit();
            _apply_postgres_migrations(c);c.commit();
            seed(c);c.commit();
            return
        c.executescript(SCHEMA);c.commit();
        migrate_users_role_constraint(c);c.commit();
        migrate_tenant_leases_signatures(c);c.commit();
        migrate_listings_columns(c);c.commit();
        migrate_uploads_related_key(c);c.commit();
        migrate_listing_requests_table(c);c.commit();
        migrate_tenant_invites_table(c);c.commit();
        migrate_role_permissions_table(c);c.commit();
        migrate_message_tables(c);c.commit();
        migrate_tenant_ledger_table(c);c.commit();
        migrate_roommates_table(c);c.commit();
        migrate_tenant_payment_tools(c);c.commit();
        migrate_notifications_and_onboarding(c);c.commit();
        migrate_maintenance_staff_table(c);c.commit();
        migrate_inspections_table(c);c.commit();
        migrate_preventive_tasks_table(c);c.commit();
        migrate_core_indexes(c);c.commit();
        migrate_sessions_security(c);c.commit();
        migrate_schema_version(c);c.commit();
        repair_foreign_keys_old_table_refs(c);c.commit();
        seed(c)
    finally:
        if pg_lock_acquired:
            try:
                c.execute("SELECT pg_advisory_unlock(67002131)")
                c.commit()
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass
        try:c.close()
        except Exception:pass

def clear_active_sessions():
    def _clear(c):
        c.execute("DELETE FROM sessions")
    db_write_retry(_clear)
    removed = clear_redis_sessions()
    if removed:
        log_event(logging.INFO, "redis_sessions_cleared_on_startup", removed=removed)


def migrate_uploads_related_key(c):
    try:
        cols=[r[1] for r in c.execute("PRAGMA table_info(uploads)").fetchall()]
        if "related_key" not in cols:
            c.execute("ALTER TABLE uploads ADD COLUMN related_key TEXT")
    except Exception:
        pass

def migrate_listing_requests_table(c):
    row=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listing_requests'").fetchone()
    if not row:
        c.execute("""CREATE TABLE IF NOT EXISTS listing_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT NOT NULL,
            unit_id INTEGER,
            title TEXT NOT NULL,
            price INTEGER NOT NULL,
            location TEXT NOT NULL,
            beds INTEGER NOT NULL,
            baths INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN('pending','approved','rejected')) DEFAULT 'pending',
            submitted_by_user_id INTEGER,
            created_at TEXT NOT NULL DEFAULT(datetime('now')),
            FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL,
            FOREIGN KEY(submitted_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        )""")
    cols=[r["name"] for r in c.execute("PRAGMA table_info(listing_requests)").fetchall()]
    if "approval_note" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN approval_note TEXT")
    if "review_state" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN review_state TEXT NOT NULL DEFAULT 'initial'")
    if "checklist_photos" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN checklist_photos INTEGER NOT NULL DEFAULT 0")
    if "checklist_price" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN checklist_price INTEGER NOT NULL DEFAULT 0")
    if "checklist_description" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN checklist_description INTEGER NOT NULL DEFAULT 0")
    if "checklist_docs" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN checklist_docs INTEGER NOT NULL DEFAULT 0")
    if "reviewed_at" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN reviewed_at TEXT")
    if "resubmission_count" not in cols:
        c.execute("ALTER TABLE listing_requests ADD COLUMN resubmission_count INTEGER NOT NULL DEFAULT 0")
    c.execute("CREATE INDEX IF NOT EXISTS idx_listing_requests_status_created ON listing_requests(status,created_at,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_listing_requests_prop_status ON listing_requests(property_id,status,id)")

def migrate_tenant_invites_table(c):
    cols=[r["name"] for r in c.execute("PRAGMA table_info(tenant_property_invites)").fetchall()]
    if "expires_at" not in cols:
        c.execute("ALTER TABLE tenant_property_invites ADD COLUMN expires_at TEXT")
    if "revoke_reason" not in cols:
        c.execute("ALTER TABLE tenant_property_invites ADD COLUMN revoke_reason TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tp_invites_pending_expiry ON tenant_property_invites(status,expires_at,created_at)")

def migrate_role_permissions_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS role_permissions("
        "role TEXT NOT NULL,action TEXT NOT NULL,allowed INTEGER NOT NULL DEFAULT 0,"
        "updated_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(role,action))"
    )
    roles=("tenant","property_manager","admin")
    for action, allowed_roles in PERMISSION_DEFAULTS.items():
        for role in roles:
            c.execute(
                "INSERT OR IGNORE INTO role_permissions(role,action,allowed)VALUES(?,?,?)",
                (role, action, 1 if role in allowed_roles else 0),
            )

def migrate_message_tables(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS message_threads("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,subject TEXT NOT NULL,context_type TEXT,context_id TEXT,"
        "created_by_user_id INTEGER,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS message_participants("
        "thread_id INTEGER NOT NULL,user_id INTEGER NOT NULL,last_read_at TEXT,is_archived INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(thread_id,user_id),"
        "FOREIGN KEY(thread_id)REFERENCES message_threads(id)ON DELETE CASCADE,"
        "FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS message_posts("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,thread_id INTEGER NOT NULL,sender_user_id INTEGER NOT NULL,"
        "body TEXT NOT NULL,attachment_path TEXT,attachment_name TEXT,attachment_mime TEXT,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),"
        "FOREIGN KEY(thread_id)REFERENCES message_threads(id)ON DELETE CASCADE,"
        "FOREIGN KEY(sender_user_id)REFERENCES users(id)ON DELETE CASCADE)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_msg_participants_user ON message_participants(user_id,thread_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_msg_posts_thread_created ON message_posts(thread_id,created_at,id)")

def migrate_tenant_ledger_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS tenant_ledger_entries("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_account TEXT NOT NULL,property_id TEXT,unit_label TEXT,lease_id INTEGER,"
        "entry_type TEXT NOT NULL CHECK(entry_type IN('charge','payment','late_fee','adjustment')),"
        "category TEXT NOT NULL,amount INTEGER NOT NULL,"
        "status TEXT NOT NULL CHECK(status IN('open','paid','void','submitted','failed')) DEFAULT 'open',"
        "due_date TEXT,statement_month TEXT,note TEXT,source_payment_id INTEGER,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE,"
        "FOREIGN KEY(lease_id)REFERENCES tenant_leases(id)ON DELETE SET NULL,"
        "FOREIGN KEY(source_payment_id)REFERENCES payments(id)ON DELETE SET NULL)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant_created ON tenant_ledger_entries(tenant_account,created_at,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant_month ON tenant_ledger_entries(tenant_account,statement_month,entry_type,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_payment_src ON tenant_ledger_entries(source_payment_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payments_payer_created ON payments(payer_account,created_at,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payments_status_created ON payments(status,created_at,id)")

def migrate_tenant_payment_tools(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS payment_methods("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_user_id INTEGER NOT NULL,"
        "method_type TEXT NOT NULL CHECK(method_type IN('card','bank')),"
        "brand_label TEXT NOT NULL,last4 TEXT NOT NULL,"
        "is_default INTEGER NOT NULL DEFAULT 0,is_active INTEGER NOT NULL DEFAULT 1,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(tenant_user_id)REFERENCES users(id)ON DELETE CASCADE)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS tenant_autopay("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_user_id INTEGER NOT NULL UNIQUE,"
        "payment_method_id INTEGER,is_enabled INTEGER NOT NULL DEFAULT 0,"
        "payment_day INTEGER NOT NULL DEFAULT 1,notify_days_before INTEGER NOT NULL DEFAULT 3,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(tenant_user_id)REFERENCES users(id)ON DELETE CASCADE,"
        "FOREIGN KEY(payment_method_id)REFERENCES payment_methods(id)ON DELETE SET NULL)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_payment_methods_user_default ON payment_methods(tenant_user_id,is_default,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tenant_autopay_enabled ON tenant_autopay(is_enabled,payment_day,id)")
    cols = [r["name"] for r in c.execute("PRAGMA table_info(maintenance_requests)").fetchall()]
    if "urgency" not in cols:
        c.execute("ALTER TABLE maintenance_requests ADD COLUMN urgency TEXT NOT NULL DEFAULT 'normal'")
    c.execute("UPDATE maintenance_requests SET urgency='normal' WHERE COALESCE(urgency,'')=''")

def migrate_notifications_and_onboarding(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS notification_preferences("
        "user_id INTEGER PRIMARY KEY,payment_events INTEGER NOT NULL DEFAULT 1,"
        "maintenance_events INTEGER NOT NULL DEFAULT 1,lease_events INTEGER NOT NULL DEFAULT 1,"
        "invite_events INTEGER NOT NULL DEFAULT 1,application_events INTEGER NOT NULL DEFAULT 1,"
        "inquiry_events INTEGER NOT NULL DEFAULT 1,system_events INTEGER NOT NULL DEFAULT 1,"
        "email_enabled INTEGER NOT NULL DEFAULT 1,sms_enabled INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS user_onboarding("
        "user_id INTEGER PRIMARY KEY,role TEXT NOT NULL,checklist_json TEXT NOT NULL DEFAULT '{}',"
        "completed_at TEXT,created_at TEXT NOT NULL DEFAULT(datetime('now')),updated_at TEXT,"
        "FOREIGN KEY(user_id)REFERENCES users(id)ON DELETE CASCADE)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_notification_prefs_email ON notification_preferences(email_enabled,user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_user_onboarding_role ON user_onboarding(role,user_id)")
    users = c.execute("SELECT id,role FROM users").fetchall()
    for u in users:
        uid = to_int(u["id"], 0)
        if uid <= 0:
            continue
        c.execute(
            "INSERT OR IGNORE INTO notification_preferences(user_id)VALUES(?)",
            (uid,),
        )
        c.execute(
            "INSERT OR IGNORE INTO user_onboarding(user_id,role,checklist_json)VALUES(?,?,?)",
            (uid, normalize_role(u["role"]), "{}"),
        )

def migrate_tenant_leases_signatures(c):
    cols=[r["name"] for r in c.execute("PRAGMA table_info(tenant_leases)").fetchall()]
    if "manager_signed_at" not in cols:
        c.execute("ALTER TABLE tenant_leases ADD COLUMN manager_signed_at TEXT")
    if "tenant_signed_at" not in cols:
        c.execute("ALTER TABLE tenant_leases ADD COLUMN tenant_signed_at TEXT")
    if "esign_ip" not in cols:
        c.execute("ALTER TABLE tenant_leases ADD COLUMN esign_ip TEXT")

def migrate_roommates_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS lease_roommates("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,lease_id INTEGER NOT NULL,tenant_account TEXT NOT NULL,"
        "share_percent INTEGER NOT NULL CHECK(share_percent>0 AND share_percent<=100),"
        "status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','removed')),"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),"
        "UNIQUE(lease_id,tenant_account),"
        "FOREIGN KEY(lease_id)REFERENCES tenant_leases(id)ON DELETE CASCADE,"
        "FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE CASCADE)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_roommates_tenant_status ON lease_roommates(tenant_account,status,id)")

def migrate_maintenance_staff_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS maintenance_staff("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT,phone TEXT,"
        "is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT(datetime('now')))"
    )

def migrate_inspections_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS inspections("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_label TEXT NOT NULL,tenant_account TEXT,"
        "inspection_type TEXT NOT NULL CHECK(inspection_type IN('move_in','move_out')),"
        "scheduled_date TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN('scheduled','completed','cancelled')),"
        "checklist_json TEXT,report_notes TEXT,completed_at TEXT,created_by_user_id INTEGER,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),"
        "FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE,"
        "FOREIGN KEY(tenant_account)REFERENCES users(account_number)ON DELETE SET NULL,"
        "FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_inspections_property_date ON inspections(property_id,scheduled_date,id)")

def migrate_preventive_tasks_table(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS preventive_tasks("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,property_id TEXT NOT NULL,unit_label TEXT,task TEXT NOT NULL,"
        "frequency_days INTEGER NOT NULL,next_due_date TEXT NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','completed','cancelled')),"
        "assigned_staff_id INTEGER,last_completed_at TEXT,created_by_user_id INTEGER,"
        "created_at TEXT NOT NULL DEFAULT(datetime('now')),"
        "FOREIGN KEY(property_id)REFERENCES properties(id)ON DELETE CASCADE,"
        "FOREIGN KEY(assigned_staff_id)REFERENCES maintenance_staff(id)ON DELETE SET NULL,"
        "FOREIGN KEY(created_by_user_id)REFERENCES users(id)ON DELETE SET NULL)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_preventive_due_status ON preventive_tasks(next_due_date,status,id)")

def migrate_core_indexes(c):
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_expires ON sessions(user_id,expires_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_properties_owner ON properties(owner_account,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_units_property ON units(property_id,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leases_tenant_active ON tenant_leases(tenant_account,is_active,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leases_property_active ON tenant_leases(property_id,is_active,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_status_created ON maintenance_requests(status,created_at,id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_password_resets_user_expires ON password_resets(user_id,expires_at,used)")

def migrate_sessions_security(c):
    cols = [r["name"] for r in c.execute("PRAGMA table_info(sessions)").fetchall()]
    if "ip_hash" not in cols:
        c.execute("ALTER TABLE sessions ADD COLUMN ip_hash TEXT")
    if "user_agent_hash" not in cols:
        c.execute("ALTER TABLE sessions ADD COLUMN user_agent_hash TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_ip_hash ON sessions(ip_hash)")

def migrate_schema_version(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta("
        "key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT(datetime('now')))"
    )
    c.execute(
        "INSERT INTO schema_meta(key,value,updated_at)VALUES('schema_version',?,datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=datetime('now')",
        (str(to_int(SCHEMA_VERSION, 1)),),
    )
    c.execute(f"PRAGMA user_version={to_int(SCHEMA_VERSION, 1)}")

def migrate_users_role_constraint(c):
    row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not row or not row["sql"]:
        return
    sql = row["sql"]
    needs_rebuild = ("property_manager" not in sql)
    if needs_rebuild:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("ALTER TABLE users RENAME TO users_old")
        c.execute("""CREATE TABLE users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN('tenant','property_manager','admin')),
            account_number TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT(datetime('now'))
        );""")
        c.execute("""INSERT INTO users(id,full_name,phone,email,username,password_salt,password_hash,role,account_number,created_at)
                     SELECT id,full_name,phone,email,username,password_salt,password_hash,
                            CASE WHEN role IN('manager','landlord') THEN 'property_manager' ELSE role END,
                            account_number,created_at
                     FROM users_old;""")
        c.execute("DROP TABLE users_old")
        c.execute("PRAGMA foreign_keys=ON")
    # Ensure legacy role values are normalized even when a rebuild was not required.
    c.execute("UPDATE users SET role='property_manager' WHERE role IN('manager','landlord')")




def migrate_listings_columns(c):
    # Ensure newer columns exist on listings without breaking existing DBs.
    cols = [r["name"] for r in c.execute("PRAGMA table_info(listings)").fetchall()]
    if "is_approved" not in cols:
        c.execute("ALTER TABLE listings ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 1")
    if "is_available" not in cols:
        c.execute("ALTER TABLE listings ADD COLUMN is_available INTEGER NOT NULL DEFAULT 1")


def _quote_sql_ident(name):
    ident = str(name or "").strip()
    if (not ident) or ("\x00" in ident):
        raise ValueError("invalid_sql_identifier")
    return '"' + ident.replace('"', '""') + '"'

def repair_foreign_keys_old_table_refs(c):
    """Repair broken foreign-key references caused by prior migrations that temporarily renamed tables.

    Common failure modes:
      - users -> users_old (then users_old dropped) leaving FKs pointing at users_old
      - tables rebuilt with temp names like <table>__oldfk leaving other tables' FKs pointing there
    When a FK target table does not exist but a likely 'original' table does, rebuild the referencing
    table so the FK points to the correct target. Data is preserved.
    """
    tbls = [r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    tbl_set = set(tbls)

    fixes = {}  # {table_name: {bad_target: good_target}}

    for t in tbls:
        if t.startswith("sqlite_"):
            continue
        try:
            fks = c.execute(f"PRAGMA foreign_key_list({_quote_sql_ident(t)})").fetchall()
        except Exception:
            continue
        for fk in fks:
            bad = fk["table"]
            good = None

            if bad.lower() == "users_old" and "users" in tbl_set and "users_old" not in tbl_set:
                good = "users"
            elif bad.endswith("__oldfk"):
                candidate = bad[:-7]
                if candidate in tbl_set and bad not in tbl_set:
                    good = candidate
            elif bad.endswith("_old"):
                candidate = bad[:-4]
                if candidate in tbl_set and bad not in tbl_set:
                    good = candidate

            if good and (bad not in tbl_set) and (good in tbl_set):
                fixes.setdefault(t, {})[bad] = good

    if not fixes:
        return

    c.execute("PRAGMA foreign_keys=OFF")
    try:
        for t, mapping in fixes.items():
            row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
            if not row or not row["sql"]:
                continue
            create_sql = row["sql"]
            for bad, good in mapping.items():
                # Replace REFERENCES bad with REFERENCES good (also handles quoted identifiers)
                # Replace REFERENCES bad with REFERENCES good (handles ", ', `, and [brackets])
                # We only target the token right after REFERENCES, leaving column lists intact.
                for ql, qr in [('', ''), ('"', '"'), ("'", "'"), ('`', '`'), ('[', ']')]:
                    create_sql = re.sub(
                        rf'REFERENCES\s+{re.escape(ql)}{re.escape(bad)}{re.escape(qr)}\b',
                        f"REFERENCES {ql}{good}{qr}",
                        create_sql,
                        flags=re.IGNORECASE
                    )


            tmp = f"{t}__oldfk_repair"
            c.execute(f"ALTER TABLE {_quote_sql_ident(t)} RENAME TO {_quote_sql_ident(tmp)}")
            c.execute(create_sql)

            old_cols = [r["name"] for r in c.execute(f"PRAGMA table_info({_quote_sql_ident(tmp)})").fetchall()]
            new_cols = [r["name"] for r in c.execute(f"PRAGMA table_info({_quote_sql_ident(t)})").fetchall()]
            common = [col for col in old_cols if col in new_cols]
            if common:
                cols_csv = ",".join(_quote_sql_ident(col) for col in common)
                c.execute(
                    f"INSERT INTO {_quote_sql_ident(t)}({cols_csv}) "
                    f"SELECT {cols_csv} FROM {_quote_sql_ident(tmp)}"
                )
            c.execute(f"DROP TABLE {_quote_sql_ident(tmp)}")
    finally:
        c.execute("PRAGMA foreign_keys=ON")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  EXTRA FEATURES (favorites, applications, inquiries, uploads, notifications, password reset)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def _classify_notification_category(link=None, text="", category="general"):
    cat = (category or "general").strip().lower()
    if cat != "general":
        return cat
    l = (link or "").strip().lower()
    t = (text or "").strip().lower()
    if any(x in l for x in ("/pay", "/payments")) or "rent" in t or "payment" in t:
        return "payment"
    if "/maintenance" in l or "maintenance" in t:
        return "maintenance"
    if "/lease" in l or "lease" in t:
        return "lease"
    if "/invite" in l or "/tenants" in l or "invite" in t or "sync" in t:
        return "invite"
    if "/applications" in l or "application" in t:
        return "application"
    if "/inquiries" in l or "inquiry" in t:
        return "inquiry"
    return "system"

def _pref_key_for_category(category):
    return {
        "payment": "payment_events",
        "maintenance": "maintenance_events",
        "lease": "lease_events",
        "invite": "invite_events",
        "application": "application_events",
        "inquiry": "inquiry_events",
        "system": "system_events",
    }.get((category or "").strip().lower(), "system_events")

def ensure_notification_preferences(c, user_id):
    uid = to_int(user_id, 0)
    if uid <= 0:
        return None
    c.execute(
        "INSERT OR IGNORE INTO notification_preferences(user_id)VALUES(?)",
        (uid,),
    )
    return c.execute(
        "SELECT * FROM notification_preferences WHERE user_id=?",
        (uid,),
    ).fetchone()

def notification_allowed_for_user(c, user_id, category):
    row = ensure_notification_preferences(c, user_id)
    if not row:
        return False
    key = _pref_key_for_category(category)
    return bool(to_int(row[key], 1))

def onboarding_state_for_user(c, user):
    if not user:
        return {"role": "tenant", "checklist": {}, "completed_at": ""}
    uid = to_int(user.get("id"), 0)
    role = normalize_role(user.get("role"))
    if uid <= 0:
        return {"role": role, "checklist": {}, "completed_at": ""}
    c.execute(
        "INSERT OR IGNORE INTO user_onboarding(user_id,role,checklist_json)VALUES(?,?,?)",
        (uid, role, "{}"),
    )
    row = c.execute(
        "SELECT * FROM user_onboarding WHERE user_id=?",
        (uid,),
    ).fetchone()
    raw = (row["checklist_json"] or "{}") if row else "{}"
    checklist = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            checklist = {str(k): 1 if to_int(v, 0) else 0 for k, v in parsed.items()}
    except Exception:
        checklist = {}
    return {"role": role, "checklist": checklist, "completed_at": (row["completed_at"] if row else "")}

def create_notification(c, user_id, text, link=None, category="general"):
    uid = to_int(user_id, 0)
    if uid <= 0:
        return False
    cat = _classify_notification_category(link, text, category)
    if not notification_allowed_for_user(c, uid, cat):
        return False
    c.execute("INSERT INTO notifications(user_id,text,link)VALUES(?,?,?)",(uid,text,link))
    pref = ensure_notification_preferences(c, uid)
    email_ok = bool(pref and to_int(pref["email_enabled"], 1))
    # Best-effort email delivery for critical notifications when SMTP is configured.
    if SMTP_HOST and SMTP_FROM and email_ok:
        try:
            row = c.execute("SELECT email,full_name FROM users WHERE id=?",(uid,)).fetchone()
            if row and (row["email"] or "").strip():
                subj = "AtlasBahamas Notification"
                body = f"{text}\n\nOpen AtlasBahamas to view details."
                if link:
                    body += f"\nPath: {link}"
                send_email((row["email"] or "").strip(), subj, body)
        except Exception:
            pass
    return True

def send_email(to_email, subject, body_text):
    to_addr = (to_email or "").strip()
    if not to_addr or not SMTP_HOST or not SMTP_FROM:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = str(subject or "AtlasBahamas Notification")[:200]
        msg["From"] = SMTP_FROM
        msg["To"] = to_addr
        msg.set_content(str(body_text or ""))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=12) as s:
            if SMTP_USE_TLS:
                s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log_event(logging.INFO, "email_sent", to=to_addr, subject=(subject or "")[:120])
        return True
    except Exception as e:
        log_event(logging.ERROR, "email_send_failed", to=to_addr, subject=(subject or "")[:120], error=str(e))
        return False

def audit_log(c, actor_user, action, entity_type="", entity_id="", details=""):
    uid = None
    role = ""
    if actor_user:
        uid = actor_user.get("id")
        role = actor_user.get("role") or ""
    c.execute(
        "INSERT INTO audit_logs(actor_user_id,actor_role,action,entity_type,entity_id,details)VALUES(?,?,?,?,?,?)",
        (uid, role, action, str(entity_type or ""), str(entity_id or ""), str(details or "")[:1000]),
    )

def permission_allowed(c, role, action):
    rr = normalize_role(role)
    row = c.execute("SELECT allowed FROM role_permissions WHERE role=? AND action=?", (rr, action)).fetchone()
    if row is not None:
        return bool(to_int(row["allowed"], 0))
    defaults = PERMISSION_DEFAULTS.get(action)
    if defaults is not None:
        return rr in defaults
    return rr == "admin"

def user_permission_allowed(c, user, action):
    if not user:
        return False
    role = normalize_role(user.get("role"))
    if not role:
        return False
    return permission_allowed(c, role, action)

def parse_page_params(q, default_per=25, max_per=100):
    page = to_int((q.get("page") or ["1"])[0], 1)
    per = to_int((q.get("per") or [str(default_per)])[0], default_per)
    if page < 1:
        page = 1
    if per < 5:
        per = 5
    if per > max_per:
        per = max_per
    return page, per, (page - 1) * per

def pager_html(path, q, page, per, total):
    total = max(0, to_int(total, 0))
    pages = max(1, (total + per - 1) // per)
    page = min(max(1, page), pages)
    if pages <= 1 and total <= per:
        return ""
    keep = {}
    for k, vals in (q or {}).items():
        if not vals:
            continue
        if k in ("page",):
            continue
        keep[k] = vals[0]
    def _url(target_page):
        params = dict(keep)
        params["page"] = str(target_page)
        params["per"] = str(per)
        return f"{path}?{urlencode(params)}"
    prev_btn = f"<a class='ghost-btn' href='{_url(page-1)}'>Prev</a>" if page > 1 else "<span class='badge'>Prev</span>"
    next_btn = f"<a class='ghost-btn' href='{_url(page+1)}'>Next</a>" if page < pages else "<span class='badge'>Next</span>"
    return (
        "<div class='row' style='margin:10px 0;align-items:center;gap:8px;'>"
        f"{prev_btn}{next_btn}"
        f"<span class='muted'>Page {page} of {pages} ({total} total)</span>"
        "</div>"
    )

def cleanup_expired_invites(c):
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    legacy_cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, INVITE_EXPIRY_HOURS))).isoformat(timespec="seconds")
    c.execute(
        "UPDATE tenant_property_invites "
        "SET status='cancelled', responded_at=?, revoke_reason=COALESCE(NULLIF(revoke_reason,''),'expired') "
        "WHERE status='pending' AND ("
        "(expires_at IS NOT NULL AND expires_at<=?) OR "
        "(expires_at IS NULL AND created_at<=?)"
        ")",
        (now_iso, now_iso, legacy_cutoff),
    )

def run_housekeeping_if_due():
    global _LAST_HOUSEKEEPING_TS, _LAST_DAILY_AUTOMATION_DATE
    now = time.time()
    if (now - _LAST_HOUSEKEEPING_TS) < HOUSEKEEPING_INTERVAL_SECONDS:
        return
    with _HOUSEKEEPING_LOCK:
        now2 = time.time()
        if (now2 - _LAST_HOUSEKEEPING_TS) < HOUSEKEEPING_INTERVAL_SECONDS:
            return
        _LAST_HOUSEKEEPING_TS = now2
        try:
            def _housekeep(c):
                global _LAST_DAILY_AUTOMATION_DATE
                now_dt = datetime.now(timezone.utc)
                cleanup_expired_invites(c)
                now_iso = now_dt.isoformat(timespec="seconds")
                expired_sessions = c.execute(
                    "SELECT session_id,user_id FROM sessions WHERE expires_at<=?",
                    (now_iso,),
                ).fetchall()
                c.execute("DELETE FROM sessions WHERE expires_at<=?", (now_iso,))
                for s in expired_sessions:
                    sid = (s["session_id"] or "").strip()
                    if sid:
                        delete_session_redis(sid, user_id=s["user_id"])
                reset_cutoff = (now_dt - timedelta(days=max(1, PASSWORD_RESET_RETENTION_DAYS))).strftime("%Y-%m-%d %H:%M:%S")
                c.execute(
                    "DELETE FROM password_resets WHERE used=1 OR expires_at<=?",
                    (reset_cutoff,),
                )
                today = now_dt.strftime("%Y-%m-%d")
                # Run automated rent/autopay once per day in early-morning UTC window.
                if _LAST_DAILY_AUTOMATION_DATE != today and 7 <= now_dt.hour <= 9:
                    run_automated_rent_notifications(c)
                    _LAST_DAILY_AUTOMATION_DATE = today
            db_write_retry(_housekeep, retries=2, delay=0.05)
            # Trim in-memory abuse-protection buckets to prevent unbounded growth.
            with _LOGIN_GUARD_LOCK:
                stale_login = []
                for k, rec in _LOGIN_GUARD.items():
                    fail_count, first_ts, lock_until = rec
                    if (now2 - first_ts) > max(LOGIN_TRACK_SECONDS, LOGIN_LOCK_SECONDS * 2):
                        stale_login.append(k)
                for k in stale_login:
                    _LOGIN_GUARD.pop(k, None)
            with _RATE_LIMIT_LOCK:
                stale_rl = []
                for k, items in _RATE_LIMIT_BUCKETS.items():
                    if not items:
                        stale_rl.append(k)
                        continue
                    if (now2 - max(items)) > 3600:
                        stale_rl.append(k)
                for k in stale_rl:
                    _RATE_LIMIT_BUCKETS.pop(k, None)
        except Exception:
            # Housekeeping should never break user requests.
            log_exception("housekeeping_failed", scope="housekeeping", alert_key="housekeeping_error")

def add_upload(c, owner_user_id, kind, related_table, related_id, rel_path, mime, related_key=None):
    try:
        c.execute("INSERT INTO uploads(owner_user_id,kind,related_table,related_id,related_key,path,mime)VALUES(?,?,?,?,?,?,?)",
                  (owner_user_id,kind,related_table,related_id,related_key,rel_path,mime))
    except Exception as e:
        msg = str(e).lower()
        if ("related_key" not in msg) and ("undefined column" not in msg) and ("no such column" not in msg):
            raise
        c.execute("INSERT INTO uploads(owner_user_id,kind,related_table,related_id,path,mime)VALUES(?,?,?,?,?,?)",
                  (owner_user_id,kind,related_table,related_id,rel_path,mime))


ALLOWED_IMAGE_MIME = {"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}

def detect_image_type(content):
    if not content:
        return (None, None)
    if content.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", ".jpg")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", ".png")
    if len(content) >= 12 and content[0:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ("image/webp", ".webp")
    return (None, None)

def is_probably_pdf(content):
    if not content or not content.startswith(b"%PDF-"):
        return False
    # Keep this lightweight: EOF marker may be near end but is optional in edge-case generators.
    tail = content[-2048:] if len(content) > 2048 else content
    return (b"%%EOF" in tail) or len(content) > 32

def _sanitize_upload_name(name, fallback):
    base = os.path.basename((name or "").strip())
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120]
    return clean or fallback

def save_image_upload(c, owner_user_id, related_table, related_id, kind, up, related_key=None):
    if not up or not up.get("content"): return None
    content=up["content"]
    if len(content)>MAX_IMAGE_UPLOAD_BYTES: return None
    sniff_mime, sniff_ext = detect_image_type(content)
    if not sniff_ext:
        return None
    mime=(up.get("content_type") or "").split(";")[0].strip().lower()
    declared_ext=os.path.splitext(up.get("filename") or "")[1].lower()
    if declared_ext in (".jpeg",):
        declared_ext = ".jpg"
    if mime in ALLOWED_IMAGE_MIME and ALLOWED_IMAGE_MIME[mime] != sniff_ext:
        return None
    if declared_ext and declared_ext in (".jpg", ".png", ".webp") and declared_ext != sniff_ext:
        return None
    mime = sniff_mime
    ext = sniff_ext
    safe=secrets.token_hex(16)+ext
    out=UPLOAD_DIR / safe
    out.write_bytes(content)
    rel_path=f"/uploads/{safe}"
    add_upload(c, owner_user_id, kind, related_table, related_id, rel_path, mime, related_key=related_key)
    return rel_path

def save_pdf_upload(c, owner_user_id, related_table, related_id, kind, up, related_key=None):
    if not up or not up.get("content"): return None
    content=up["content"]
    if len(content)>MAX_PDF_UPLOAD_BYTES: return None
    if not is_probably_pdf(content):
        return None
    mime=(up.get("content_type") or "").split(";")[0].strip().lower()
    ext2=os.path.splitext(up.get("filename") or "")[1].lower()
    if mime and mime!="application/pdf":
        return None
    if ext2 and ext2!=".pdf":
        return None
    mime="application/pdf"
    safe=secrets.token_hex(16)+".pdf"
    out=UPLOAD_DIR / safe
    out.write_bytes(content)
    rel_path=f"/uploads/{safe}"
    add_upload(c, owner_user_id, kind, related_table, related_id, rel_path, mime, related_key=related_key)
    return rel_path

ALLOWED_MESSAGE_ATTACH_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "text/plain": ".txt",
}

def save_message_attachment(c, owner_user_id, thread_id, up):
    if not up or not up.get("content"):
        return (None, "", "")
    content = up["content"]
    if len(content) > MAX_ATTACHMENT_UPLOAD_BYTES:
        return (None, "", "")
    mime = (up.get("content_type") or "").split(";")[0].strip().lower()
    ext = ALLOWED_MESSAGE_ATTACH_MIME.get(mime)
    if not ext:
        ext2 = os.path.splitext(up.get("filename") or "")[1].lower()
        if ext2 in (".jpg", ".jpeg"):
            ext, mime = ".jpg", "image/jpeg"
        elif ext2 in (".png",):
            ext, mime = ".png", "image/png"
        elif ext2 in (".webp",):
            ext, mime = ".webp", "image/webp"
        elif ext2 in (".txt",):
            ext, mime = ".txt", "text/plain"
        elif ext2 in (".pdf",):
            ext, mime = ".pdf", "application/pdf"
        else:
            return (None, "", "")
    # Validate by file signature/content when possible.
    if ext in (".jpg", ".png", ".webp"):
        _, sniff_ext = detect_image_type(content)
        if sniff_ext != ext:
            return (None, "", "")
    elif ext == ".pdf":
        if not is_probably_pdf(content):
            return (None, "", "")
    elif ext == ".txt":
        if b"\x00" in content:
            return (None, "", "")
        try:
            content.decode("utf-8")
        except Exception:
            return (None, "", "")
    subdir = UPLOAD_DIR / "messages"
    subdir.mkdir(parents=True, exist_ok=True)
    safe = secrets.token_hex(16) + ext
    (subdir / safe).write_bytes(content)
    rel_path = f"/uploads/messages/{safe}"
    fname = _sanitize_upload_name(up.get("filename"), f"attachment{ext}")
    add_upload(c, owner_user_id, "message_attachment", "message_threads", int(thread_id), rel_path, mime)
    return (rel_path, fname, mime)


def save_listing_photo(c, owner_user_id, listing_id, up):
    # Validate and persist a listing photo upload.
    if not up or not up.get("content"):
        return None
    content = up["content"]
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        return None  # too large
    mime, ext = detect_image_type(content)
    if not ext:
        return None
    safe = secrets.token_hex(10) + ext
    subdir = UPLOAD_DIR / "listings" / str(int(listing_id))
    subdir.mkdir(parents=True, exist_ok=True)
    rel_path = f"/uploads/listings/{int(listing_id)}/{safe}"
    (subdir / safe).write_bytes(content)
    add_upload(c, owner_user_id, "listing_photo", "listings", int(listing_id), rel_path, mime)
    return rel_path

def listing_photos(c, listing_id):
    return c.execute("SELECT * FROM uploads WHERE kind='listing_photo' AND related_table='listings' AND related_id=? ORDER BY created_at DESC, id DESC",(int(listing_id),)).fetchall()

def property_photos(c, property_id):
    pid = (property_id or "").strip()
    if not pid:
        return []
    return c.execute(
        "SELECT * FROM uploads WHERE kind='property_photo' AND related_table='properties' AND related_key=? "
        "ORDER BY created_at DESC,id DESC",
        (pid,),
    ).fetchall()

def lease_doc_for_lease(c, lease_id):
    lid = to_int(lease_id, 0)
    if lid <= 0:
        return None
    return c.execute(
        "SELECT * FROM uploads WHERE kind='lease_doc' AND related_table='tenant_leases' AND related_id=? "
        "ORDER BY id DESC LIMIT 1",
        (lid,),
    ).fetchone()

def get_user_by_email_or_username(c, ident):
    ident = (ident or "").strip()
    if "@" in ident:
        return c.execute("SELECT * FROM users WHERE email=?",(ident,)).fetchone()
    return c.execute("SELECT * FROM users WHERE username=?",(ident,)).fetchone()

def get_user_by_identifier(c, ident):
    ident = (ident or "").strip()
    if not ident:
        return None
    return c.execute(
        "SELECT * FROM users WHERE account_number=? OR username=? OR email=? LIMIT 1",
        (ident, ident, ident),
    ).fetchone()

def user_in_message_thread(c, user_id, thread_id):
    row = c.execute(
        "SELECT 1 FROM message_participants WHERE thread_id=? AND user_id=?",
        (int(thread_id), int(user_id)),
    ).fetchone()
    return bool(row)

def message_thread_summary_for_user(c, user_id, limit=100):
    return c.execute(
        "SELECT t.id,t.subject,t.context_type,t.context_id,t.created_at,t.updated_at,"
        "mp.last_read_at,"
        "(SELECT body FROM message_posts pp WHERE pp.thread_id=t.id ORDER BY pp.id DESC LIMIT 1) AS last_body,"
        "(SELECT created_at FROM message_posts pp WHERE pp.thread_id=t.id ORDER BY pp.id DESC LIMIT 1) AS last_post_at,"
        "(SELECT full_name FROM users uu WHERE uu.id=(SELECT sender_user_id FROM message_posts pp WHERE pp.thread_id=t.id ORDER BY pp.id DESC LIMIT 1)) AS last_sender,"
        "(SELECT COUNT(1) FROM message_posts pp WHERE pp.thread_id=t.id "
        "   AND (mp.last_read_at IS NULL OR pp.created_at>mp.last_read_at) AND pp.sender_user_id!=?) AS unread_count "
        "FROM message_participants mp "
        "JOIN message_threads t ON t.id=mp.thread_id "
        "WHERE mp.user_id=? AND COALESCE(mp.is_archived,0)=0 "
        "ORDER BY COALESCE(t.updated_at,t.created_at) DESC,t.id DESC LIMIT ?",
        (int(user_id), int(user_id), int(limit)),
    ).fetchall()

def create_message_thread(c, actor_user, recipient_ident, subject, body, context_type="", context_id="", attachment=None):
    subj = (subject or "").strip()[:140]
    msg = (body or "").strip()[:4000]
    recipient = get_user_by_identifier(c, recipient_ident)
    if not subj or not msg:
        return False, "Subject and message are required.", 0
    if not recipient:
        return False, "Recipient was not found.", 0
    if int(recipient["id"]) == int(actor_user["id"]):
        return False, "Send to another account.", 0
    ctx_t = (context_type or "").strip().lower()
    if ctx_t not in ("", "listing", "property", "maintenance"):
        ctx_t = ""
    ctx_id = (context_id or "").strip()[:80]
    c.execute(
        "INSERT INTO message_threads(subject,context_type,context_id,created_by_user_id,updated_at)VALUES(?,?,?,?,datetime('now'))",
        (subj, ctx_t, ctx_id, actor_user["id"]),
    )
    thread_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT INTO message_participants(thread_id,user_id,last_read_at,is_archived)VALUES(?,?,datetime('now'),0)",
        (thread_id, actor_user["id"]),
    )
    c.execute(
        "INSERT INTO message_participants(thread_id,user_id,last_read_at,is_archived)VALUES(?,?,NULL,0)",
        (thread_id, recipient["id"]),
    )
    apath = ""
    aname = ""
    amime = ""
    if attachment:
        apath, aname, amime = save_message_attachment(c, actor_user["id"], thread_id, attachment)
    c.execute(
        "INSERT INTO message_posts(thread_id,sender_user_id,body,attachment_path,attachment_name,attachment_mime)VALUES(?,?,?,?,?,?)",
        (thread_id, actor_user["id"], msg, apath, aname, amime),
    )
    c.execute("UPDATE message_threads SET updated_at=datetime('now') WHERE id=?", (thread_id,))
    create_notification(c, recipient["id"], f"New message from {actor_user['full_name']}: {subj}", f"/messages?thread={thread_id}")
    audit_log(c, actor_user, "message_thread_created", "message_threads", thread_id, f"to={recipient['account_number']};subject={subj}")
    return True, "Message thread started.", int(thread_id)

def send_message_reply(c, actor_user, thread_id, body, attachment=None):
    tid = to_int(thread_id, 0)
    msg = (body or "").strip()[:4000]
    if tid <= 0 or not msg:
        return False, "Message body is required."
    if not user_in_message_thread(c, actor_user["id"], tid):
        return False, "Thread not found."
    apath = ""
    aname = ""
    amime = ""
    if attachment:
        apath, aname, amime = save_message_attachment(c, actor_user["id"], tid, attachment)
    c.execute(
        "INSERT INTO message_posts(thread_id,sender_user_id,body,attachment_path,attachment_name,attachment_mime)VALUES(?,?,?,?,?,?)",
        (tid, actor_user["id"], msg, apath, aname, amime),
    )
    c.execute("UPDATE message_threads SET updated_at=datetime('now') WHERE id=?", (tid,))
    c.execute(
        "UPDATE message_participants SET last_read_at=datetime('now') WHERE thread_id=? AND user_id=?",
        (tid, actor_user["id"]),
    )
    others = c.execute(
        "SELECT user_id FROM message_participants WHERE thread_id=? AND user_id!=?",
        (tid, actor_user["id"]),
    ).fetchall()
    for r in others:
        create_notification(c, r["user_id"], f"New reply from {actor_user['full_name']}", f"/messages?thread={tid}")
    audit_log(c, actor_user, "message_reply_sent", "message_threads", tid, f"len={len(msg)}")
    return True, "Reply sent."

def maintenance_manager_user(c, req_row):
    if not req_row:
        return None
    tenant_account = (req_row["tenant_account"] or "").strip()
    prop = c.execute(
        "SELECT p.owner_account FROM tenant_leases l "
        "JOIN properties p ON p.id=l.property_id "
        "WHERE l.tenant_account=? AND l.is_active=1 ORDER BY l.id DESC LIMIT 1",
        (tenant_account,),
    ).fetchone()
    if prop and (prop["owner_account"] or "").strip():
        owner = c.execute(
            "SELECT * FROM users WHERE account_number=? LIMIT 1",
            ((prop["owner_account"] or "").strip(),),
        ).fetchone()
        if owner:
            return owner
    return c.execute("SELECT * FROM users WHERE role='property_manager' ORDER BY id LIMIT 1").fetchone()

def ensure_maintenance_message_thread(c, actor_user, maintenance_id):
    mid = to_int(maintenance_id, 0)
    if mid <= 0 or not actor_user:
        return 0
    req = c.execute("SELECT * FROM maintenance_requests WHERE id=?", (mid,)).fetchone()
    if not req:
        return 0
    existing = c.execute(
        "SELECT t.id FROM message_threads t "
        "JOIN message_participants mp ON mp.thread_id=t.id "
        "WHERE t.context_type='maintenance' AND t.context_id=? AND mp.user_id=? "
        "ORDER BY t.id DESC LIMIT 1",
        (str(mid), actor_user["id"]),
    ).fetchone()
    if existing:
        return to_int(existing["id"], 0)
    mgr = maintenance_manager_user(c, req)
    if not mgr:
        return 0
    recipient = (mgr["account_number"] or "").strip()
    if not recipient:
        return 0
    if to_int(mgr["id"], 0) == to_int(actor_user["id"], 0):
        tenant = c.execute("SELECT * FROM users WHERE account_number=? LIMIT 1", ((req["tenant_account"] or "").strip(),)).fetchone()
        if not tenant:
            return 0
        recipient = (tenant["account_number"] or "").strip()
    subject = f"Maintenance #{mid}"
    body = f"Request thread started for maintenance #{mid}."
    ok, _note, tid = create_message_thread(
        c,
        actor_user,
        recipient,
        subject,
        body,
        context_type="maintenance",
        context_id=str(mid),
        attachment=None,
    )
    return tid if ok else 0

def mark_message_thread_read(c, user_id, thread_id):
    c.execute(
        "UPDATE message_participants SET last_read_at=datetime('now') WHERE thread_id=? AND user_id=?",
        (int(thread_id), int(user_id)),
    )

def get_tenant_by_identifier(c, ident):
    ident = (ident or "").strip()
    if not ident:
        return None
    return c.execute(
        "SELECT id,account_number,full_name,username,email FROM users "
        "WHERE role='tenant' AND (account_number=? OR username=? OR email=?) "
        "LIMIT 1",
        (ident, ident, ident),
    ).fetchone()

def create_tenant_property_invite(c, sender_user, tenant_ident, property_id, unit_label, message="", owner_account=None):
    cleanup_expired_invites(c)
    tid = (tenant_ident or "").strip()
    pid = (property_id or "").strip()
    ul = (unit_label or "").strip()
    msg = (message or "").strip()[:280]
    if len(tid) < 2 or len(pid) < 5 or len(ul) < 2:
        return False, "Tenant, property, and unit are required."

    tenant = get_tenant_by_identifier(c, tid)
    if not tenant:
        return False, "Tenant account was not found."

    if owner_account:
        prop = c.execute("SELECT id,name FROM properties WHERE id=? AND owner_account=?",(pid, owner_account)).fetchone()
    else:
        prop = c.execute("SELECT id,name FROM properties WHERE id=?",(pid,)).fetchone()
    if not prop:
        return False, "Property was not found for your account."

    unit = c.execute("SELECT unit_label,is_occupied FROM units WHERE property_id=? AND unit_label=?",(pid, ul)).fetchone()
    if not unit:
        return False, "Unit label does not exist for that property."

    busy = c.execute("SELECT 1 FROM tenant_leases WHERE property_id=? AND unit_label=? AND is_active=1",(pid, ul)).fetchone()
    if busy or to_int(unit["is_occupied"], 0):
        return False, "That unit is already occupied."

    dup = c.execute(
        "SELECT id FROM tenant_property_invites WHERE tenant_account=? AND property_id=? AND unit_label=? AND status='pending'",
        (tenant["account_number"], pid, ul),
    ).fetchone()
    if dup:
        return False, "A pending invite already exists for this tenant and unit."

    cooldown_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, INVITE_RESEND_COOLDOWN_MIN))).isoformat(timespec="seconds")
    cooldown_hit = c.execute(
        "SELECT id,created_at FROM tenant_property_invites "
        "WHERE tenant_account=? AND property_id=? AND unit_label=? AND created_at>=? "
        "ORDER BY id DESC LIMIT 1",
        (tenant["account_number"], pid, ul, cooldown_cutoff),
    ).fetchone()
    if cooldown_hit:
        return False, f"Resend cooldown active. Try again in about {INVITE_RESEND_COOLDOWN_MIN} minute(s)."

    invite_expires_at = (datetime.now(timezone.utc) + timedelta(hours=max(1, INVITE_EXPIRY_HOURS))).isoformat(timespec="seconds")
    c.execute(
        "INSERT INTO tenant_property_invites("
        "sender_user_id,tenant_user_id,tenant_account,property_id,unit_label,message,status,expires_at,revoke_reason"
        ") VALUES(?,?,?,?,?,?,'pending',?,NULL)",
        (sender_user["id"], tenant["id"], tenant["account_number"], pid, ul, msg, invite_expires_at),
    )

    sender_name = sender_user.get("full_name") or sender_user.get("username") or "AtlasBahamas"
    preview = f" Note: {msg}" if msg else ""
    create_notification(
        c,
        tenant["id"],
        f"Property sync invite from {sender_name}: {prop['name']} / {ul}. Tap to accept or decline.{preview}",
        "/tenant/invites",
    )
    audit_log(c, sender_user, "tenant_invite_sent", "tenant_property_invites", "", f"{tenant['account_number']} -> {pid}/{ul};expires={INVITE_EXPIRY_HOURS}h")
    return True, "Confirmation invite sent to tenant."

def create_bulk_listing_requests(c, actor_user, property_id, category, owner_account=None, unit_overrides=None):
    pid = (property_id or "").strip()
    cat = (category or "Long Term Rental").strip()
    valid_categories = ("Long Term Rental", "Short Term Rental", "Vehicle Rental", "Sell Your Property to Us")
    if cat not in valid_categories:
        cat = "Long Term Rental"
    if len(pid) < 5:
        return 0, 0, "Property is required."

    if owner_account:
        pr = c.execute("SELECT * FROM properties WHERE id=? AND owner_account=?",(pid, owner_account)).fetchone()
    else:
        pr = c.execute("SELECT * FROM properties WHERE id=?",(pid,)).fetchone()
    if not pr:
        return 0, 0, "Property not found."

    units = c.execute("SELECT * FROM units WHERE property_id=? ORDER BY id",(pid,)).fetchall()
    if not units:
        return 0, 0, "No units found for this property."

    overrides = {}
    if isinstance(unit_overrides, dict):
        for k, raw in unit_overrides.items():
            uid = to_int(k, 0)
            if uid <= 0 or not isinstance(raw, dict):
                continue
            rec = {}
            if "selected" in raw:
                vv = raw.get("selected")
                if isinstance(vv, str):
                    rec["selected"] = vv.strip().lower() in ("1", "true", "yes", "on")
                else:
                    rec["selected"] = bool(vv)
            if "title" in raw:
                rec["title"] = (raw.get("title") or "").strip()[:180]
            if "location" in raw:
                rec["location"] = (raw.get("location") or "").strip()[:160]
            if "description" in raw:
                rec["description"] = (raw.get("description") or "").strip()[:2000]
            if "category" in raw:
                cc = (raw.get("category") or "").strip()
                if cc in valid_categories:
                    rec["category"] = cc
            if "price" in raw:
                rec["price"] = max(0, to_int(raw.get("price"), 0))
            if "beds" in raw:
                rec["beds"] = max(0, to_int(raw.get("beds"), 0))
            if "baths" in raw:
                rec["baths"] = max(0, to_int(raw.get("baths"), 0))
            if rec:
                overrides[uid] = rec

    prop_photo_paths = [r["path"] for r in property_photos(c, pid)[:8]]
    created = 0
    skipped = 0
    for u in units:
        unit_id = to_int(u["id"], 0)
        ul = (u["unit_label"] or "").strip()
        ov = overrides.get(unit_id, {})
        if ov and ("selected" in ov) and (not ov["selected"]):
            skipped += 1
            continue
        if not ul:
            skipped += 1
            continue

        price = max(0, to_int(ov.get("price"), to_int(u["rent"], 0)))
        beds = max(0, to_int(ov.get("beds"), to_int(u["beds"], 0)))
        baths = max(0, to_int(ov.get("baths"), to_int(u["baths"], 0)))
        if ov:
            c.execute(
                "UPDATE units SET rent=?,beds=?,baths=? WHERE id=? AND property_id=?",
                (price, beds, baths, unit_id, pid),
            )

        if to_int(u["is_occupied"], 0):
            skipped += 1
            continue
        exists_pending = c.execute(
            "SELECT 1 FROM listing_requests WHERE property_id=? AND unit_id=? AND status='pending'",
            (pid, unit_id),
        ).fetchone()
        if exists_pending:
            skipped += 1
            continue

        title = (ov.get("title") or "").strip() or f"{pr['name']} - {ul}"
        location = (ov.get("location") or "").strip() or (pr["location"] or "")
        description = (ov.get("description") or "").strip() or f"{ul} at {pr['name']} ({pr['location']})."
        row_cat = (ov.get("category") or "").strip() or cat
        if row_cat not in valid_categories:
            row_cat = cat
        c.execute(
            "INSERT INTO listing_requests(property_id,unit_id,title,price,location,beds,baths,category,description,status,submitted_by_user_id)"
            "VALUES(?,?,?,?,?,?,?,?,?,'pending',?)",
            (pid, unit_id, title, price, location, beds, baths, row_cat, description, actor_user["id"]),
        )
        req_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Reuse property photos as initial listing photos for bulk submissions.
        for pth in prop_photo_paths:
            ext = os.path.splitext((pth or "").lower())[1]
            mime = "image/jpeg"
            if ext == ".png":
                mime = "image/png"
            elif ext == ".webp":
                mime = "image/webp"
            c.execute(
                "INSERT INTO uploads(owner_user_id,kind,related_table,related_id,path,mime,related_key)"
                "VALUES(?,?,?,?,?,?,NULL)",
                (actor_user["id"], "listing_photo", "listing_requests", req_id, pth, mime),
            )
        created += 1

    if created:
        for r in c.execute("SELECT id FROM users WHERE role='admin'").fetchall():
            create_notification(c, r["id"], f"{created} new listing submissions: {pr['name']}", "/admin/submissions")
    return created, skipped, ""

def _parse_ymd(text):
    v = (text or "").strip()
    if len(v) >= 10:
        v = v[:10]
    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except Exception:
        return None

def _statement_month(due_date, created_at):
    d = _parse_ymd(due_date)
    if d:
        return d.strftime("%Y-%m")
    created = (created_at or "").strip()
    if len(created) >= 7 and re.fullmatch(r"\d{4}-\d{2}", created[:7]):
        return created[:7]
    return datetime.now(timezone.utc).strftime("%Y-%m")

def active_lease_with_rent(c, tenant_account):
    acct = (tenant_account or "").strip()
    if not acct:
        return None
    base = c.execute(
        "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.start_date,l.end_date,l.is_active,"
        "COALESCE(u.rent,0) AS rent "
        "FROM tenant_leases l "
        "LEFT JOIN units u ON u.property_id=l.property_id AND u.unit_label=l.unit_label "
        "WHERE l.tenant_account=? AND l.is_active=1 "
        "ORDER BY l.id DESC LIMIT 1",
        (acct,),
    ).fetchone()
    is_roommate = False
    if not base:
        base = c.execute(
            "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.start_date,l.end_date,l.is_active,"
            "COALESCE(u.rent,0) AS rent "
            "FROM lease_roommates rm "
            "JOIN tenant_leases l ON l.id=rm.lease_id AND l.is_active=1 "
            "LEFT JOIN units u ON u.property_id=l.property_id AND u.unit_label=l.unit_label "
            "WHERE rm.tenant_account=? AND rm.status='active' "
            "ORDER BY l.id DESC LIMIT 1",
            (acct,),
        ).fetchone()
        is_roommate = bool(base)
    if not base:
        return None
    lease = dict(base)
    share = 100
    if is_roommate:
        rm = c.execute(
            "SELECT share_percent FROM lease_roommates WHERE lease_id=? AND tenant_account=? AND status='active' ORDER BY id DESC LIMIT 1",
            (lease["id"], acct),
        ).fetchone()
        share = max(1, min(100, to_int(rm["share_percent"], 100) if rm else 100))
    else:
        rm_total = to_int(c.execute(
            "SELECT COALESCE(SUM(share_percent),0) AS n FROM lease_roommates WHERE lease_id=? AND status='active'",
            (lease["id"],),
        ).fetchone()["n"], 0)
        share = max(1, min(100, 100 - max(0, rm_total)))
    lease["share_percent"] = share
    lease["rent"] = max(0, int(round(max(0, to_int(lease.get("rent"), 0)) * (share / 100.0))))
    lease["is_roommate"] = 1 if is_roommate else 0
    lease["effective_tenant_account"] = acct
    return lease

def format_payment_method_label(row):
    if not row:
        return "Saved method"
    typ = "Card" if (row["method_type"] or "").strip().lower() == "card" else "Bank"
    label = (row["brand_label"] or "").strip() or typ
    last4 = re.sub(r"\D", "", str(row["last4"] or ""))[-4:]
    if not last4:
        last4 = "0000"
    return f"{label} ({typ} ****{last4})"

def tenant_saved_methods(c, tenant_user_id):
    return c.execute(
        "SELECT * FROM payment_methods WHERE tenant_user_id=? AND is_active=1 ORDER BY is_default DESC,id DESC",
        (int(tenant_user_id),),
    ).fetchall()

def tenant_method_by_id(c, tenant_user_id, method_id):
    mid = to_int(method_id, 0)
    if mid <= 0:
        return None
    return c.execute(
        "SELECT * FROM payment_methods WHERE id=? AND tenant_user_id=? AND is_active=1",
        (mid, int(tenant_user_id)),
    ).fetchone()

def set_default_payment_method(c, tenant_user_id, method_id):
    uid = int(tenant_user_id)
    mid = to_int(method_id, 0)
    c.execute("UPDATE payment_methods SET is_default=0,updated_at=datetime('now') WHERE tenant_user_id=?", (uid,))
    if mid > 0:
        c.execute(
            "UPDATE payment_methods SET is_default=1,updated_at=datetime('now') WHERE id=? AND tenant_user_id=? AND is_active=1",
            (mid, uid),
        )

def _next_autopay_date(today_dt, payment_day):
    day = max(1, min(28, to_int(payment_day, 1)))
    today = today_dt.date()
    if today.day <= day:
        return today.replace(day=day)
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt.replace(day=day)

def send_tenant_autopay_reminders(c, now_dt=None):
    now_dt = now_dt or datetime.now(timezone.utc)
    today = now_dt.date()
    today_key = today.strftime("%Y-%m-%d")
    rows = c.execute(
        "SELECT a.id,a.tenant_user_id,a.payment_method_id,a.payment_day,a.notify_days_before,"
        "u.account_number,u.full_name "
        "FROM tenant_autopay a JOIN users u ON u.id=a.tenant_user_id "
        "WHERE a.is_enabled=1 ORDER BY a.id"
    ).fetchall()
    sent = 0
    for row in rows:
        acct = (row["account_number"] or "").strip()
        if not acct:
            continue
        lease = active_lease_with_rent(c, acct)
        if not lease:
            continue
        rent_amt = max(0, to_int(lease.get("rent"), 0))
        if rent_amt <= 0:
            continue
        reminder_days = max(0, min(14, to_int(row["notify_days_before"], 3)))
        due_dt = _next_autopay_date(now_dt, row["payment_day"])
        days_until = (due_dt - today).days
        if days_until != reminder_days:
            continue
        pm = tenant_method_by_id(c, row["tenant_user_id"], row["payment_method_id"])
        if not pm:
            pm = c.execute(
                "SELECT * FROM payment_methods WHERE tenant_user_id=? AND is_active=1 "
                "ORDER BY is_default DESC,id DESC LIMIT 1",
                (row["tenant_user_id"],),
            ).fetchone()
        method_label = format_payment_method_label(pm) if pm else "No saved method"
        text = (
            f"Autopay reminder: ${rent_amt:,} for {lease['property_id']} / {lease['unit_label']} "
            f"will run on {due_dt.strftime('%Y-%m-%d')}."
        )
        already = c.execute(
            "SELECT 1 FROM notifications WHERE user_id=? AND text=? AND substr(created_at,1,10)=?",
            (row["tenant_user_id"], text, today_key),
        ).fetchone()
        if already:
            continue
        create_notification(c, row["tenant_user_id"], text, "/tenant/autopay", category="payment")
        if SMTP_HOST and SMTP_FROM:
            urow = c.execute("SELECT email FROM users WHERE id=?", (row["tenant_user_id"],)).fetchone()
            to_addr = (urow["email"] or "").strip() if urow else ""
            if to_addr:
                send_email(
                    to_addr,
                    "AtlasBahamas Autopay Reminder",
                    (
                        f"Hi {row['full_name']},\n\n"
                        f"This is a reminder that autopay will process your rent on {due_dt.strftime('%Y-%m-%d')}.\n"
                        f"Amount: ${rent_amt:,}\n"
                        f"Property: {lease['property_id']} / {lease['unit_label']}\n"
                        f"Payment method: {method_label}\n\n"
                        f"Review settings at /tenant/autopay"
                    ),
                )
        sent += 1
    return sent

def run_tenant_autopay(c, now_dt=None):
    now_dt = now_dt or datetime.now(timezone.utc)
    today = now_dt.date()
    month = now_dt.strftime("%Y-%m")
    rows = c.execute(
        "SELECT a.id,a.tenant_user_id,a.payment_method_id,a.payment_day,"
        "u.account_number,u.full_name "
        "FROM tenant_autopay a JOIN users u ON u.id=a.tenant_user_id "
        "WHERE a.is_enabled=1 ORDER BY a.id"
    ).fetchall()
    for row in rows:
        day = max(1, min(28, to_int(row["payment_day"], 1)))
        if today.day < day:
            continue
        acct = (row["account_number"] or "").strip()
        if not acct:
            continue
        lease = active_lease_with_rent(c, acct)
        if not lease:
            continue
        rent_amt = max(0, to_int(lease.get("rent"), 0))
        if rent_amt <= 0:
            continue
        ensure_monthly_rent_charge(c, acct, now_dt=now_dt)
        already = c.execute(
            "SELECT id FROM payments WHERE payer_role='tenant' AND payer_account=? "
            "AND payment_type='rent' AND status IN('submitted','paid') "
            "AND LOWER(COALESCE(provider,'')) LIKE 'autopay%' AND substr(created_at,1,7)=? "
            "ORDER BY id DESC LIMIT 1",
            (acct, month),
        ).fetchone()
        if already:
            continue
        pm = tenant_method_by_id(c, row["tenant_user_id"], row["payment_method_id"])
        if not pm:
            pm = c.execute(
                "SELECT * FROM payment_methods WHERE tenant_user_id=? AND is_active=1 "
                "ORDER BY is_default DESC,id DESC LIMIT 1",
                (row["tenant_user_id"],),
            ).fetchone()
        if not pm:
            create_notification(c, row["tenant_user_id"], "Autopay skipped: add an active payment method.", "/tenant/payment-methods")
            continue
        provider = "Autopay - " + format_payment_method_label(pm)
        c.execute(
            "INSERT INTO payments(payer_account,payer_role,payment_type,provider,amount,status)VALUES(?,?,?,?,?,?)",
            (acct, "tenant", "rent", provider, rent_amt, "paid"),
        )
        pay_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        sync_ledger_from_payments(c, payment_id=pay_id)
        reconcile_tenant_ledger(c, acct)
        create_notification(
            c,
            row["tenant_user_id"],
            f"Autopay processed: ${rent_amt:,} for {lease['property_id']} / {lease['unit_label']}.",
            f"/tenant/payment/receipt?id={pay_id}",
        )
        owner = c.execute(
            "SELECT u.id FROM properties p JOIN users u ON u.account_number=p.owner_account WHERE p.id=? LIMIT 1",
            (lease["property_id"],),
        ).fetchone()
        if owner:
            create_notification(
                c,
                owner["id"],
                f"Autopay received: {acct} paid ${rent_amt:,} for {lease['property_id']} / {lease['unit_label']}.",
                "/manager/payments",
            )
        audit_log(
            c,
            None,
            "tenant_autopay_processed",
            "payments",
            pay_id,
            f"tenant={acct};property={lease['property_id']};unit={lease['unit_label']};method={pm['id']}",
        )

def sync_ledger_from_payments(c, tenant_account=None, payment_id=None):
    sql = "SELECT * FROM payments WHERE payer_role='tenant' "
    args = []
    if tenant_account:
        sql += "AND payer_account=? "
        args.append(tenant_account)
    if payment_id:
        sql += "AND id=? "
        args.append(int(payment_id))
    pays = c.execute(sql + "ORDER BY id", tuple(args)).fetchall()
    lease_cache = {}
    for p in pays:
        acct = p["payer_account"]
        if acct not in lease_cache:
            lease_cache[acct] = active_lease_with_rent(c, acct)
        lease = lease_cache[acct]
        amount = max(0, to_int(p["amount"], 0))
        if amount <= 0:
            continue
        st = (p["status"] or "submitted").strip().lower()
        if st not in ("submitted", "paid", "failed"):
            st = "submitted"
        sm = _statement_month("", p["created_at"])
        cat = "rent_payment" if (p["payment_type"] or "") == "rent" else "bill_payment"
        note = (p["provider"] or "").strip()[:200]
        existing = c.execute(
            "SELECT id FROM tenant_ledger_entries WHERE source_payment_id=?",
            (p["id"],),
        ).fetchone()
        params = (
            acct,
            lease["property_id"] if lease else None,
            lease["unit_label"] if lease else None,
            lease["id"] if lease else None,
            cat,
            -amount,
            st,
            sm,
            note,
            p["id"],
        )
        if existing:
            c.execute(
                "UPDATE tenant_ledger_entries SET tenant_account=?,property_id=?,unit_label=?,lease_id=?,category=?,"
                "amount=?,status=?,statement_month=?,note=?,updated_at=datetime('now') WHERE source_payment_id=?",
                params,
            )
        else:
            c.execute(
                "INSERT INTO tenant_ledger_entries(tenant_account,property_id,unit_label,lease_id,entry_type,category,amount,status,statement_month,note,source_payment_id)"
                "VALUES(?,?,?,?, 'payment',?,?,?,?,?,?)",
                params,
            )

def ensure_monthly_rent_charge(c, tenant_account, now_dt=None):
    now_dt = now_dt or datetime.now(timezone.utc)
    lease = active_lease_with_rent(c, tenant_account)
    if not lease:
        return
    rent = max(0, to_int(lease["rent"], 0))
    if rent <= 0:
        return
    month = now_dt.strftime("%Y-%m")
    start = _parse_ymd(lease["start_date"])
    due_day = start.day if start else 5
    due_day = max(1, min(28, due_day))
    due_date = f"{month}-{due_day:02d}"
    has_charge = c.execute(
        "SELECT 1 FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND statement_month=? AND entry_type='charge' AND category='rent' AND status!='void'",
        (tenant_account, month),
    ).fetchone()
    if not has_charge:
        c.execute(
            "INSERT INTO tenant_ledger_entries(tenant_account,property_id,unit_label,lease_id,entry_type,category,amount,status,due_date,statement_month,note)"
            "VALUES(?,?,?,?, 'charge','rent',?,'open',?,?,?)",
            (tenant_account, lease["property_id"], lease["unit_label"], lease["id"], rent, due_date, month, "Monthly rent charge"),
        )
    due_dt = _parse_ymd(due_date)
    if not due_dt:
        return
    if now_dt.date() <= (due_dt + timedelta(days=5)).date():
        return
    has_late = c.execute(
        "SELECT 1 FROM tenant_ledger_entries WHERE tenant_account=? AND statement_month=? AND entry_type='late_fee' AND status!='void'",
        (tenant_account, month),
    ).fetchone()
    if has_late:
        return
    month_charges = to_int(c.execute(
        "SELECT COALESCE(SUM(amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND statement_month=? AND entry_type IN('charge','late_fee','adjustment') AND status!='void'",
        (tenant_account, month),
    ).fetchone()["n"], 0)
    month_paid = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND statement_month=? AND entry_type='payment' AND status='paid'",
        (tenant_account, month),
    ).fetchone()["n"], 0)
    if month_paid < month_charges:
        fee = max(25, int(round(rent * 0.05)))
        c.execute(
            "INSERT INTO tenant_ledger_entries(tenant_account,property_id,unit_label,lease_id,entry_type,category,amount,status,due_date,statement_month,note)"
            "VALUES(?,?,?,?, 'late_fee','rent_late_fee',?,'open',?,?,?)",
            (tenant_account, lease["property_id"], lease["unit_label"], lease["id"], fee, now_dt.strftime("%Y-%m-%d"), month, "Late fee"),
        )

def reconcile_tenant_ledger(c, tenant_account):
    c.execute(
        "UPDATE tenant_ledger_entries SET status='open',updated_at=datetime('now') "
        "WHERE tenant_account=? AND entry_type IN('charge','late_fee','adjustment') AND status!='void'",
        (tenant_account,),
    )
    paid_credit = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type='payment' AND status='paid'",
        (tenant_account,),
    ).fetchone()["n"], 0)
    charges = c.execute(
        "SELECT id,amount FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type IN('charge','late_fee','adjustment') AND status='open' "
        "ORDER BY COALESCE(due_date,created_at) ASC,id ASC",
        (tenant_account,),
    ).fetchall()
    rem = paid_credit
    for row in charges:
        amt = max(0, to_int(row["amount"], 0))
        if rem >= amt and amt > 0:
            c.execute(
                "UPDATE tenant_ledger_entries SET status='paid',updated_at=datetime('now') WHERE id=?",
                (row["id"],),
            )
            rem -= amt
        else:
            break
    charge_total = to_int(c.execute(
        "SELECT COALESCE(SUM(amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type IN('charge','late_fee','adjustment') AND status!='void'",
        (tenant_account,),
    ).fetchone()["n"], 0)
    paid_total = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type='payment' AND status='paid'",
        (tenant_account,),
    ).fetchone()["n"], 0)
    submitted_total = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type='payment' AND status='submitted'",
        (tenant_account,),
    ).fetchone()["n"], 0)
    failed_total = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND entry_type='payment' AND status='failed'",
        (tenant_account,),
    ).fetchone()["n"], 0)
    return {
        "charges": max(0, charge_total),
        "paid": max(0, paid_total),
        "submitted": max(0, submitted_total),
        "failed": max(0, failed_total),
        "balance": max(0, charge_total - paid_total),
    }

def ensure_tenant_ledger_current(c, tenant_account):
    acct = (tenant_account or "").strip()
    if not acct:
        return {"charges": 0, "paid": 0, "submitted": 0, "failed": 0, "balance": 0}
    sync_ledger_from_payments(c, tenant_account=acct)
    ensure_monthly_rent_charge(c, acct)
    return reconcile_tenant_ledger(c, acct)

def approve_listing_request(c, req_row):
    req_id = req_row["id"]
    ups = c.execute(
        "SELECT * FROM uploads WHERE related_table='listing_requests' AND related_id=? AND kind='listing_photo' ORDER BY id",
        (req_id,),
    ).fetchall()
    thumb = ups[0]["path"] if ups else "/static/img/placeholder.jpg"
    c.execute(
        "INSERT INTO listings(title,price,location,beds,baths,category,image_url,description,is_approved,is_available)VALUES(?,?,?,?,?,?,?,?,1,1)",
        (
            req_row["title"],
            req_row["price"],
            req_row["location"],
            req_row["beds"],
            req_row["baths"],
            req_row["category"],
            thumb,
            req_row["description"],
        ),
    )
    listing_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "UPDATE uploads SET related_table='listings', related_id=? WHERE related_table='listing_requests' AND related_id=?",
        (listing_id, req_id),
    )
    c.execute("UPDATE listing_requests SET status='approved' WHERE id=?", (req_id,))
    if req_row["submitted_by_user_id"]:
        create_notification(c, req_row["submitted_by_user_id"], f"Your listing was approved: {req_row['title']}", f"/listing/{listing_id}")
    return listing_id

def tenant_rent_due(c, tenant_account):
    lease = active_lease_with_rent(c, tenant_account)
    if not lease:
        return None
    now_dt = datetime.now(timezone.utc)
    now = now_dt.date()
    due_date = now.replace(day=1)
    ensure_tenant_ledger_current(c, tenant_account)
    month = now_dt.strftime("%Y-%m")
    charge_total = to_int(c.execute(
        "SELECT COALESCE(SUM(amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND statement_month=? "
        "AND entry_type IN('charge','late_fee','adjustment') AND status!='void'",
        (tenant_account, month),
    ).fetchone()["n"], 0)
    paid_total = to_int(c.execute(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
        "WHERE tenant_account=? AND statement_month=? AND entry_type='payment' AND status='paid'",
        (tenant_account, month),
    ).fetchone()["n"], 0)
    balance = max(0, charge_total - paid_total)
    status = "paid" if balance <= 0 else ("late" if now > due_date else "due")
    return {
        "property_id": lease["property_id"],
        "unit_label": lease["unit_label"],
        "share_percent": to_int(lease.get("share_percent"), 100),
        "amount": balance,
        "due_date": due_date.isoformat(),
        "status": status,
    }

def run_automated_rent_notifications(c):
    now_dt = datetime.now(timezone.utc)
    send_tenant_autopay_reminders(c, now_dt=now_dt)
    run_tenant_autopay(c, now_dt=now_dt)
    rows = c.execute(
        "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,p.owner_account,u.id AS tenant_user_id "
        "FROM tenant_leases l "
        "JOIN properties p ON p.id=l.property_id "
        "JOIN users u ON u.account_number=l.tenant_account "
        "WHERE l.is_active=1"
    ).fetchall()
    today = now_dt.strftime("%Y-%m-%d")
    for r in rows:
        payers = [(r["tenant_account"], r["tenant_user_id"])]
        roommates = c.execute(
            "SELECT rm.tenant_account,u.id AS user_id,rm.share_percent "
            "FROM lease_roommates rm "
            "JOIN users u ON u.account_number=rm.tenant_account "
            "WHERE rm.lease_id=? AND rm.status='active'",
            (r["id"],),
        ).fetchall()
        for rm in roommates:
            payers.append((rm["tenant_account"], rm["user_id"]))

        for acct, user_id in payers:
            due = tenant_rent_due(c, acct)
            if not due or to_int(due.get("amount"), 0) <= 0:
                continue
            tag = "late" if due["status"] == "late" else "due"
            share = max(1, min(100, to_int(due.get("share_percent"), 100)))
            share_text = f" ({share}% share)" if share < 100 else ""
            text = f"Rent {tag}: ${to_int(due['amount'],0):,}{share_text} for {r['property_id']} / {r['unit_label']}"
            already = c.execute(
                "SELECT 1 FROM notifications WHERE user_id=? AND text=? AND substr(created_at,1,10)=?",
                (user_id, text, today),
            ).fetchone()
            if not already:
                create_notification(c, user_id, text, "/tenant/pay-rent")
        owner = c.execute("SELECT id FROM users WHERE account_number=?", (r["owner_account"],)).fetchone()
        if owner:
            for acct, _ in payers:
                due = tenant_rent_due(c, acct)
                if not due or to_int(due.get("amount"), 0) <= 0:
                    continue
                tag = "late" if due["status"] == "late" else "due"
                share = max(1, min(100, to_int(due.get("share_percent"), 100)))
                share_text = f" ({share}% share)" if share < 100 else ""
                note = f"Tenant rent {tag}: {acct}{share_text} - {r['property_id']} / {r['unit_label']}"
                owner_already = c.execute(
                    "SELECT 1 FROM notifications WHERE user_id=? AND text=? AND substr(created_at,1,10)=?",
                    (owner["id"], note, today),
                ).fetchone()
                if not owner_already:
                    create_notification(c, owner["id"], note, "/manager/payments")

def new_reset_token(c, user_id, minutes=30):
    tok = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO password_resets(user_id,token,expires_at)VALUES(?,?,?)",(user_id,tok,exp))
    return tok, exp

def valid_reset(c, tok):
    row = c.execute("SELECT * FROM password_resets WHERE token=?",(tok,)).fetchone()
    if not row or row["used"]:
        return None
    if row["expires_at"] < datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
        return None
    return row

def parse_multipart(body_bytes, boundary):
    res = {"fields": {}, "files": {}}
    delim = b"--" + boundary
    parts = body_bytes.split(delim)
    part_count = 0
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        part_count += 1
        if part_count > MAX_MULTIPART_PARTS:
            break
        if part.endswith(b"--"):
            part = part[:-2]
        header_blob, _, content = part.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", "replace").split("\r\n")
        h = {}
        for line in headers:
            if ":" in line:
                k,v=line.split(":",1)
                h[k.strip().lower()] = v.strip()
        cd = h.get("content-disposition","")
        m = re.search(r'name="([^"]+)"', cd)
        if not m:
            continue
        name = m.group(1)
        fm = re.search(r'filename="([^"]*)"', cd)
        if fm and fm.group(1):
            filename = fm.group(1)
            entry = {
                "filename": filename,
                "content": content.rstrip(b"\r\n"),
                "content_type": h.get("content-type","application/octet-stream"),
            }
            cur = res["files"].get(name)
            if cur is None:
                res["files"][name] = entry
            elif isinstance(cur, list):
                cur.append(entry)
            else:
                res["files"][name] = [cur, entry]
        else:
            val = content.decode("utf-8","replace").rstrip("\r\n")
            if len(val) > 20000:
                val = val[:20000]
            res["fields"][name] = val
    return res




# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  TEMPLATE ENGINE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def to_int(v, default=0):
    try:
        return int(str(v).strip())
    except Exception:
        return default


def esc(s):
    return(str(s)if s is not None else"").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#039;")

_ph=re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

def render(tpl,**ctx):
    base=(TEMPLATES_DIR/"base.html").read_text(encoding="utf-8")
    content=(TEMPLATES_DIR/tpl).read_text(encoding="utf-8")
    merged=base.replace("{{content}}",content)
    ctx.setdefault("scripts","")
    ctx.setdefault("nav_menu","")
    return _ph.sub(lambda m:str(ctx.get(m.group(1),"")),merged).encode("utf-8")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  SESSION / AUTH
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def sign(v):
    return v+"."+hmac.new(SECRET_KEY.encode(),v.encode(),hashlib.sha256).hexdigest()

def unsign(s):
    if not s or"."not in s:return None
    v,m=s.rsplit(".",1);exp=hmac.new(SECRET_KEY.encode(),v.encode(),hashlib.sha256).hexdigest()
    return v if hmac.compare_digest(exp,m) else None

def get_cookie(cookies,name):
    if not cookies:return None
    for p in cookies.split(";"):
        p=p.strip()
        if p.startswith(name+"="):return p.split("=",1)[1]
    return None

def client_ip(headers):
    xff = (headers.get("X-Forwarded-For") or "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return (headers.get("X-Real-IP") or "").strip() or "0.0.0.0"

_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(?::\d{1,5})?$")

def _fallback_public_host():
    host = _normalize_host_value(DEFAULT_PUBLIC_HOST)
    if host:
        return host
    bind = _normalize_host_value(HOST)
    if bind and bind not in ("0.0.0.0", "::"):
        return bind
    return "localhost"

def request_is_secure(headers=None):
    if not headers:
        return False
    proto = (headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return proto == "https"

def safe_request_host(headers=None):
    fallback = _fallback_public_host()
    if not headers:
        return fallback
    raw = (headers.get("X-Forwarded-Host") or headers.get("Host") or "").split(",")[0].strip().lower()
    if not _HOST_RE.fullmatch(raw or ""):
        return fallback
    host_only = raw
    if host_only.count(":") == 1:
        host_only = host_only.split(":", 1)[0]
    if ALLOWED_HOSTS and host_only not in ALLOWED_HOSTS and raw not in ALLOWED_HOSTS:
        return fallback
    return raw

def request_is_local(headers=None):
    return _is_local_host_value(safe_request_host(headers))

def hash_client_value(tag, value):
    txt = (value or "").strip()
    if not txt:
        return ""
    payload = f"{tag}:{txt}".encode("utf-8", "replace")
    return hmac.new(SECRET_KEY.encode("utf-8", "replace"), payload, hashlib.sha256).hexdigest()

def session_ip_hash(headers=None):
    return hash_client_value("ip", client_ip(headers or {}))

def session_user_agent_hash(headers=None):
    ua = (headers.get("User-Agent") or "") if headers else ""
    return hash_client_value("ua", ua[:512])

def cookie_secure(headers=None):
    v = (os.getenv("COOKIE_SECURE","") or "").strip().lower()
    if v in ("1","true","yes","on"):
        return True
    if v in ("0","false","no","off"):
        return False
    if FORCE_SECURE_COOKIES:
        return True
    return request_is_secure(headers)

def session_cookie_attrs(headers=None):
    attrs = f"Path=/; HttpOnly; SameSite={SESSION_COOKIE_SAMESITE}"
    if cookie_secure(headers):
        attrs += "; Secure"
    return attrs

def csrf_cookie_attrs(headers=None):
    attrs = f"Path=/; SameSite={CSRF_COOKIE_SAMESITE}"
    if cookie_secure(headers):
        attrs += "; Secure"
    return attrs

def new_csrf_token():
    return secrets.token_urlsafe(24)

def valid_csrf_token(v):
    return bool(v) and bool(re.fullmatch(r"[A-Za-z0-9_-]{20,120}", str(v)))

def extract_session_raw(headers):
    signed = get_cookie(headers.get("Cookie",""), SESSION_COOKIE)
    return unsign(signed) if signed else None

def ensure_csrf_cookie(headers):
    cur = get_cookie(headers.get("Cookie",""), CSRF_COOKIE)
    if valid_csrf_token(cur):
        return cur, None
    tok = new_csrf_token()
    return tok, f"{CSRF_COOKIE}={tok}; {csrf_cookie_attrs(headers)}"

def csrf_ok(headers, form):
    c = get_cookie(headers.get("Cookie",""), CSRF_COOKIE)
    f = (form.get("csrf_token") or "").strip()
    return valid_csrf_token(c) and valid_csrf_token(f) and hmac.compare_digest(c, f)

def same_origin_ok(headers):
    host = safe_request_host(headers)
    if not host:
        return True
    origin = (headers.get("Origin") or "").strip()
    if origin:
        try:
            oh = (urlparse(origin).netloc or "").lower()
            return oh == host
        except Exception:
            return False
    ref = (headers.get("Referer") or "").strip()
    if ref:
        try:
            rh = (urlparse(ref).netloc or "").lower()
            return rh == host
        except Exception:
            return False
    return True

def add_security_headers(h):
    if not SECURITY_HEADERS_ENABLED:
        return
    h.send_header("X-Content-Type-Options", "nosniff")
    h.send_header("X-Frame-Options", "DENY")
    h.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    h.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    h.send_header("Cross-Origin-Opener-Policy", "same-origin")
    h.send_header("Cross-Origin-Resource-Policy", "same-origin")
    csp = (
        "default-src 'self'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; connect-src 'self'"
    )
    h.send_header("Content-Security-Policy", csp)
    if request_is_secure(getattr(h, "headers", None)) and HSTS_MAX_AGE > 0:
        hsts = f"max-age={HSTS_MAX_AGE}"
        if HSTS_INCLUDE_SUBDOMAINS:
            hsts += "; includeSubDomains"
        if HSTS_PRELOAD:
            hsts += "; preload"
        h.send_header("Strict-Transport-Security", hsts)

def _login_guard_key(ip, username):
    return f"{ip}|{(username or '').strip().lower()}"

def login_guard_check(ip, username):
    key = _login_guard_key(ip, username)
    now = time.time()
    with _LOGIN_GUARD_LOCK:
        rec = _LOGIN_GUARD.get(key)
        if not rec:
            return False, 0
        fail_count, first_ts, lock_until = rec
        if lock_until and lock_until > now:
            return True, int(lock_until - now)
        if now - first_ts > LOGIN_TRACK_SECONDS:
            _LOGIN_GUARD.pop(key, None)
            return False, 0
        return False, 0

def login_guard_fail(ip, username):
    key = _login_guard_key(ip, username)
    now = time.time()
    with _LOGIN_GUARD_LOCK:
        fail_count, first_ts, lock_until = _LOGIN_GUARD.get(key, (0, now, 0.0))
        if now - first_ts > LOGIN_TRACK_SECONDS:
            fail_count, first_ts, lock_until = (0, now, 0.0)
        fail_count += 1
        if fail_count >= LOGIN_MAX_ATTEMPTS:
            lock_until = now + LOGIN_LOCK_SECONDS
        _LOGIN_GUARD[key] = (fail_count, first_ts, lock_until)

def login_guard_clear(ip, username):
    key = _login_guard_key(ip, username)
    with _LOGIN_GUARD_LOCK:
        _LOGIN_GUARD.pop(key, None)

def login_guard_status_for_username(username):
    uname = (username or "").strip().lower()
    if not uname:
        return (False, 0, 0)
    suffix = "|" + uname
    now = time.time()
    locked_until = 0.0
    fail_total = 0
    stale = []
    with _LOGIN_GUARD_LOCK:
        for key, rec in _LOGIN_GUARD.items():
            if not key.endswith(suffix):
                continue
            fail_count, first_ts, lock_until = rec
            if now - first_ts > LOGIN_TRACK_SECONDS and (not lock_until or lock_until <= now):
                stale.append(key)
                continue
            fail_total += to_int(fail_count, 0)
            if lock_until and lock_until > locked_until:
                locked_until = lock_until
        for key in stale:
            _LOGIN_GUARD.pop(key, None)
    wait_s = max(0, int(locked_until - now))
    return (wait_s > 0, wait_s, fail_total)

def login_guard_unlock_username(username):
    uname = (username or "").strip().lower()
    if not uname:
        return 0
    suffix = "|" + uname
    removed = 0
    with _LOGIN_GUARD_LOCK:
        keys = [k for k in _LOGIN_GUARD.keys() if k.endswith(suffix)]
        for k in keys:
            if k in _LOGIN_GUARD:
                _LOGIN_GUARD.pop(k, None)
                removed += 1
    return removed

def login_guard_snapshot():
    now = time.time()
    tracked = 0
    locked = 0
    fail_total = 0
    stale = []
    with _LOGIN_GUARD_LOCK:
        for key, rec in _LOGIN_GUARD.items():
            fail_count, first_ts, lock_until = rec
            if now - first_ts > LOGIN_TRACK_SECONDS and (not lock_until or lock_until <= now):
                stale.append(key)
                continue
            tracked += 1
            fail_total += to_int(fail_count, 0)
            if lock_until and lock_until > now:
                locked += 1
        for key in stale:
            _LOGIN_GUARD.pop(key, None)
    return {"tracked": tracked, "locked": locked, "fail_total": fail_total}

def rate_limit_check(key, limit, window_seconds):
    cli = redis_runtime_client()
    if cli:
        allowed, retry_after = cli.rate_limit(key, max(1, int(limit)), max(1, int(window_seconds)))
        if not allowed:
            return True, max(1, int(retry_after))
        return False, 0
    now = time.time()
    with _RATE_LIMIT_LOCK:
        items = _RATE_LIMIT_BUCKETS.get(key) or []
        items = [ts for ts in items if (now - ts) < window_seconds]
        if len(items) >= max(1, int(limit)):
            retry = max(1, int(window_seconds - (now - items[0])))
            _RATE_LIMIT_BUCKETS[key] = items
            return True, retry
        items.append(now)
        _RATE_LIMIT_BUCKETS[key] = items
    return False, 0

def route_rate_limit(path, headers, user, form):
    rule = RATE_LIMIT_RULES.get(path)
    if not rule:
        return False, 0
    limit, window = rule
    ip = client_ip(headers)
    if path == "/login":
        uname = (form.get("username") or "").strip().lower()
        key = f"login:{ip}:{uname}"
    elif path in ("/inquiry", "/apply"):
        key = f"{path}:{ip}"
    elif user:
        key = f"{path}:{user.get('account_number') or ip}"
    else:
        key = f"{path}:{ip}"
    return rate_limit_check(key, limit, window)

def create_session(c,uid,headers=None):
    raw=secrets.token_urlsafe(32);exp=(datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    iph = session_ip_hash(headers or {})
    uah = session_user_agent_hash(headers or {})
    # Session rotation: replace older sessions on successful login.
    invalidate_user_sessions(c, uid)
    try:
        c.execute("INSERT INTO sessions(session_id,user_id,expires_at,ip_hash,user_agent_hash)VALUES(?,?,?,?,?)",(raw,uid,exp,iph,uah))
    except DBOperationalError:
        # Backward compatibility if migration has not yet run.
        c.execute("INSERT INTO sessions(session_id,user_id,expires_at)VALUES(?,?,?)",(raw,uid,exp))
    c.commit()
    cache_session_redis(raw, uid, exp, iph, uah)
    return sign(raw)

def cur_user(headers):
    try:
        signed=get_cookie(headers.get("Cookie",""),SESSION_COOKIE)
        raw=unsign(signed)if signed else None
        if not raw:return None
        req_ip = session_ip_hash(headers or {})
        req_ua = session_user_agent_hash(headers or {})
        rs = get_session_redis(raw)
        if rs:
            expected_ip = (rs.get("ip_hash") or "")
            expected_ua = (rs.get("user_agent_hash") or "")
            if expected_ip and not hmac.compare_digest(expected_ip, req_ip):
                invalidate_session_raw(raw)
                return None
            if expected_ua and not hmac.compare_digest(expected_ua, req_ua):
                invalidate_session_raw(raw)
                return None
            c=db()
            r=c.execute("SELECT * FROM users WHERE id=?", (rs["user_id"],)).fetchone()
            c.close()
            if not r:
                invalidate_session_raw(raw)
                return None
            return _user_row_to_dict(r)
        c=db()
        try:
            r=c.execute(
                "SELECT u.*,s.ip_hash,s.user_agent_hash,s.expires_at FROM sessions s "
                "JOIN users u ON u.id=s.user_id WHERE s.session_id=? AND s.expires_at>?",
                (raw,datetime.now(timezone.utc).isoformat(timespec="seconds"))
            ).fetchone()
        except DBOperationalError:
            r=c.execute(
                "SELECT u.*,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.session_id=? AND s.expires_at>?",
                (raw,datetime.now(timezone.utc).isoformat(timespec="seconds"))
            ).fetchone()
        if not r:
            c.close()
            return None
        expected_ip = (r["ip_hash"] if "ip_hash" in r.keys() else "") or ""
        expected_ua = (r["user_agent_hash"] if "user_agent_hash" in r.keys() else "") or ""
        if expected_ip and not hmac.compare_digest(expected_ip, req_ip):
            c.execute("DELETE FROM sessions WHERE session_id=?", (raw,))
            c.commit()
            c.close()
            delete_session_redis(raw, user_id=r["id"])
            return None
        if expected_ua and not hmac.compare_digest(expected_ua, req_ua):
            c.execute("DELETE FROM sessions WHERE session_id=?", (raw,))
            c.commit()
            c.close()
            delete_session_redis(raw, user_id=r["id"])
            return None
        cache_session_redis(raw, r["id"], (r["expires_at"] if "expires_at" in r.keys() else ""), expected_ip, expected_ua)
        c.close()
        return _user_row_to_dict(r)
    except:return None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HTTP HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def send_html(h,body,status=200,cookies=None):
    set_cookies = list(cookies or [])
    try:
        signed = get_cookie(h.headers.get("Cookie",""), SESSION_COOKIE)
        if signed and not valid_csrf_token(get_cookie(h.headers.get("Cookie",""), CSRF_COOKIE)):
            _, cset = ensure_csrf_cookie(h.headers)
            if cset:
                set_cookies.append(cset)
    except Exception:
        pass
    h.send_response(status)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Content-Length",str(len(body)))
    if get_cookie(h.headers.get("Cookie",""), SESSION_COOKIE):
        h.send_header("Cache-Control", "no-store")
    add_security_headers(h)
    for c in set_cookies:
        h.send_header("Set-Cookie",c)
    h.end_headers();h.wfile.write(body)

def send_json(h,obj,status=200):
    b=json.dumps(obj).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.send_header("Content-Length",str(len(b)))
    h.send_header("Cache-Control", "no-store")
    add_security_headers(h)
    h.end_headers()
    h.wfile.write(b)

def _csv_cell(v):
    s = str(v if v is not None else "")
    if any(ch in s for ch in [",", "\"", "\n", "\r"]):
        s = "\"" + s.replace("\"", "\"\"") + "\""
    return s

def send_csv(h, filename, rows):
    data = "\n".join([",".join(_csv_cell(col) for col in row) for row in rows]).encode("utf-8", "replace")
    h.send_response(200)
    h.send_header("Content-Type", "text/csv; charset=utf-8")
    h.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    h.send_header("Content-Length", str(len(data)))
    h.send_header("Cache-Control", "no-store")
    add_security_headers(h)
    h.end_headers()
    h.wfile.write(data)

def with_msg(path, msg, err=False):
    q = urlencode({"msg": str(msg), "err": "1" if err else "0"})
    return f"{path}{'&' if '?' in path else '?'}{q}"

def query_message_box(q):
    msg = ((q or {}).get("msg") or [""])[0].strip()
    if not msg:
        return ""
    err = (((q or {}).get("err") or ["0"])[0] == "1")
    cls = "notice err" if err else "notice"
    return f"<div class='{cls}' style='margin-bottom:10px;'>{esc(msg)}</div>"

def handle_user_error(h, message, redirect_path):
    return redir(h, with_msg(redirect_path, message, True))

def status_badge(status, kind="general"):
    st = (status or "").strip().lower()
    if kind == "payment":
        if st == "paid":
            return "<span class='badge ok'>paid</span>"
        if st == "failed":
            return "<span class='badge no'>failed</span>"
        return "<span class='badge'>submitted</span>"
    if kind == "maintenance":
        if st == "closed":
            return "<span class='badge ok'>completed</span>"
        if st == "in_progress":
            return "<span class='badge'>in progress</span>"
        return "<span class='badge no'>open</span>"
    if kind == "priority":
        if st == "emergency":
            return "<span class='badge no'>emergency</span>"
        if st in ("high", "medium"):
            return f"<span class='badge'>{esc(st)}</span>"
        return f"<span class='badge ok'>{esc(st or 'normal')}</span>"
    if kind == "review":
        if st in ("approved", "active", "current"):
            return f"<span class='badge ok'>{esc(st)}</span>"
        if st in ("rejected", "denied", "late", "closed", "failed", "cancelled", "expired"):
            return f"<span class='badge no'>{esc(st)}</span>"
        return f"<span class='badge'>{esc(st or 'pending')}</span>"
    if st in ("approved", "active", "current", "paid"):
        return f"<span class='badge ok'>{esc(st)}</span>"
    if st in ("rejected", "denied", "late", "closed", "failed", "cancelled", "expired"):
        return f"<span class='badge no'>{esc(st)}</span>"
    return f"<span class='badge'>{esc(st or 'pending')}</span>"

def empty_state(icon, title, message, action_text="", action_link=""):
    action = ""
    if action_text and action_link:
        action = f"<div style='margin-top:10px;'><a class='primary-btn' href='{esc(action_link)}'>{esc(action_text)}</a></div>"
    return (
        "<div style='text-align:center;padding:36px 14px;'>"
        f"<div style='font-size:38px;margin-bottom:10px;'>{esc(icon)}</div>"
        f"<h3 style='margin:0 0 6px 0;'>{esc(title)}</h3>"
        f"<div class='muted'>{esc(message)}</div>"
        f"{action}"
        "</div>"
    )

def _menu_badge(n):
    n2 = to_int(n, 0)
    return f"<span class='menu-badge'>{n2}</span>" if n2 > 0 else ""

def menu_counts_for_user(user):
    counts = {
        "alerts": 0,
        "invites_pending": 0,
        "maintenance_open": 0,
        "payments_submitted": 0,
        "checks_pending": 0,
        "inquiries_open": 0,
        "applications_pending": 0,
        "listing_reviews": 0,
        "queue_total": 0,
    }
    if not user:
        return counts
    role = normalize_role(user.get("role"))
    c = db()
    try:
        counts["alerts"] = to_int(
            c.execute("SELECT COUNT(1) AS n FROM notifications WHERE user_id=? AND is_read=0", (user["id"],)).fetchone()["n"],
            0,
        )
        if role == "tenant":
            counts["invites_pending"] = to_int(
                c.execute(
                    "SELECT COUNT(1) AS n FROM tenant_property_invites WHERE tenant_account=? AND status='pending'",
                    (user["account_number"],),
                ).fetchone()["n"],
                0,
            )
            return counts
        if role in ("property_manager", "admin"):
            if role == "admin":
                counts["maintenance_open"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM maintenance_requests WHERE status IN('open','in_progress')"
                ).fetchone()["n"], 0)
                counts["checks_pending"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM property_checks WHERE status IN('requested','scheduled')"
                ).fetchone()["n"], 0)
                counts["listing_reviews"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests WHERE status='pending'"
                ).fetchone()["n"], 0)
                counts["payments_submitted"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM payments WHERE status='submitted'"
                ).fetchone()["n"], 0)
            else:
                acct = (user.get("account_number") or "").strip()
                counts["maintenance_open"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM maintenance_requests m "
                    "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "JOIN properties p ON p.id=l.property_id "
                    "WHERE p.owner_account=? AND m.status IN('open','in_progress')",
                    (acct,),
                ).fetchone()["n"], 0)
                counts["checks_pending"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM property_checks pc JOIN properties p ON p.id=pc.property_id "
                    "WHERE p.owner_account=? AND pc.status IN('requested','scheduled')",
                    (acct,),
                ).fetchone()["n"], 0)
                counts["listing_reviews"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests lr JOIN properties p ON p.id=lr.property_id "
                    "WHERE p.owner_account=? AND lr.status='pending'",
                    (acct,),
                ).fetchone()["n"], 0)
                counts["payments_submitted"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM payments p WHERE p.status='submitted' AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id "
                    "WHERE l.tenant_account=p.payer_account AND l.is_active=1 AND pp.owner_account=?"
                    ")",
                    (acct,),
                ).fetchone()["n"], 0)
                counts["invites_pending"] = to_int(c.execute(
                    "SELECT COUNT(1) AS n FROM tenant_property_invites i JOIN properties p ON p.id=i.property_id "
                    "WHERE p.owner_account=? AND i.status='pending'",
                    (acct,),
                ).fetchone()["n"], 0)
            counts["applications_pending"] = to_int(
                c.execute("SELECT COUNT(1) AS n FROM applications WHERE status IN('submitted','under_review')").fetchone()["n"],
                0,
            )
            counts["inquiries_open"] = to_int(
                c.execute("SELECT COUNT(1) AS n FROM inquiries WHERE status IN('new','open')").fetchone()["n"],
                0,
            )
            counts["queue_total"] = (
                counts["maintenance_open"] + counts["payments_submitted"] + counts["checks_pending"] +
                counts["applications_pending"] + counts["inquiries_open"] + counts["invites_pending"]
            )
    finally:
        c.close()
    return counts

def manager_dashboard_sections(user, current_path="/manager"):
    role = normalize_role((user or {}).get("role"))
    if role not in ("property_manager", "admin"):
        return ""
    counts = menu_counts_for_user(user)
    sections = [
        {
            "id": "ops",
            "title": "Operations",
            "items": [
                ("Task Queue", "/manager/queue", counts.get("queue_total", 0)),
                ("Maintenance", "/manager/maintenance", counts.get("maintenance_open", 0)),
                ("Payments", "/manager/payments", counts.get("payments_submitted", 0)),
                ("Property Checks", "/manager/checks", counts.get("checks_pending", 0)),
            ],
        },
        {
            "id": "portfolio",
            "title": "Portfolio",
            "items": [
                ("Properties", "/manager/properties", 0),
                ("Register Property", "/manager/property/new", 0),
                ("Leases", "/manager/leases", 0),
                ("Rent Roll", "/manager/rent-roll", 0),
                ("Analytics", "/manager/analytics", 0),
            ],
        },
        {
            "id": "leasing",
            "title": "Listings & Tenant",
            "items": [
                ("Listing Submissions", "/manager/listing-requests", counts.get("listing_reviews", 0)),
                ("Tenant Sync", "/manager/tenants", counts.get("invites_pending", 0)),
                ("Applications", "/manager/applications", counts.get("applications_pending", 0)),
                ("Inquiries", "/manager/inquiries", counts.get("inquiries_open", 0)),
            ],
        },
        {
            "id": "opsplus",
            "title": "Field Operations",
            "items": [
                ("Inspections", "/manager/inspections", 0),
                ("Preventive", "/manager/preventive", 0),
                ("Calendar", "/manager/calendar", 0),
                ("Mass Notifications", "/manager/batch-notify", 0),
            ],
        },
    ]
    html = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Operations Navigator</h3><div class='ops-nav-wrap'>"
    for idx, sec in enumerate(sections):
        expanded = "open" if idx == 0 or any(str(current_path).startswith(link) for _, link, _ in sec["items"]) else ""
        html += f"<div class='ops-nav-section {expanded}'>"
        html += (
            "<button type='button' class='ops-nav-head' data-toggle='ops-nav'>"
            f"<span>{esc(sec['title'])}</span><span class='ops-nav-caret'>{'▾' if expanded else '▸'}</span>"
            "</button>"
        )
        html += "<div class='ops-nav-items'>"
        for label, href, count in sec["items"]:
            active = " active" if str(current_path) == href else ""
            badge = f"<span class='ops-nav-count'>{to_int(count, 0)}</span>" if to_int(count, 0) > 0 else ""
            html += f"<a class='ops-nav-link{active}' href='{href}'>{esc(label)}{badge}</a>"
        html += "</div></div>"
    html += "</div></div>"
    return html

def query_without_page(q):
    keep = {}
    for k, vals in (q or {}).items():
        if not vals or k in ("page", "per"):
            continue
        keep[k] = vals[0]
    return keep

def redir(h,loc,cookies=None,status=302):
    h.send_response(status);h.send_header("Location",loc)
    add_security_headers(h)
    if cookies:
        for c in cookies:h.send_header("Set-Cookie",c)
    h.end_headers()

def render_error(status, title, message):
    body = render(
        "error.html",
        title=title,
        nav_right=nav(None, "/"),
        nav_menu=nav_menu(None, "/"),
        status_code=str(status),
        error_title=esc(title),
        error_message=esc(message),
    )
    return status, body

def e404(h):
    status, body = render_error(404, "Not Found", "The page you requested does not exist.")
    send_html(h, body, status)

def e403(h):
    status, body = render_error(403, "Forbidden", "You do not have permission to access this page.")
    send_html(h, body, status)

def e500(h):
    status, body = render_error(500, "Server Error", "An unexpected error occurred. Please try again.")
    send_html(h, body, status)

def e400(h, message="The request could not be processed."):
    status, body = render_error(400, "Bad Request", message)
    send_html(h, body, status)

def e429(h, message="Too many requests. Please wait and try again."):
    status, body = render_error(429, "Too Many Requests", message)
    send_html(h, body, status)

def normalize_role(role):
    r = (role or "").strip().lower()
    if r in ("manager", "landlord", "property_manager"):
        return "property_manager"
    if r in ("admin", "tenant"):
        return r
    return "tenant"

def role_home(r):
    rr = normalize_role(r)
    return {"tenant":"/tenant","property_manager":"/property-manager","admin":"/admin"}.get(rr,"/")

def role_label(role):
    rr = normalize_role(role)
    if rr == "property_manager":
        return "Property Manager"
    if rr == "admin":
        return "Admin Mode"
    return "Tenant"

def user_has_role(user, *roles):
    if not user:
        return False
    ur = normalize_role(user.get("role"))
    allowed = {normalize_role(r) for r in roles}
    return ur in allowed

def render_page(tpl, title, user=None, path="/", **ctx):
    ctx.setdefault("nav_right", nav(user, path))
    ctx.setdefault("nav_menu", nav_menu(user, path))
    return render(tpl, title=title, **ctx)

def nav(user, path="/"):
    # Desktop top-right UI: profile dropdown when logged in; pills when logged out.
    if not user:
        return '<a class="pill" href="/register">Register</a><a class="pill" href="/login">Log in</a>'

    role = normalize_role(user.get("role"))
    d = role_home(role)
    counts = menu_counts_for_user(user)
    unread = to_int(counts.get("alerts"), 0)

    name = esc(user.get("full_name") or user.get("username") or "Account")
    initial = esc((name[:1] or "A").upper())
    mode = role_label(role)
    mode_class = "admin-badge" if role == "admin" else "role-badge"
    alert_badge = f'<span class="mini-badge">{unread}</span>' if unread else ""

    owner_items = ""
    if role == "admin":
        owner_items = (
            '<div class="dd-sep"></div>'
            '<div class="menu-title">Admin</div>'
            '<a class="dd-item" href="/admin">Admin Console</a>'
            f'<a class="dd-item" href="/admin/submissions">Submissions {_menu_badge(counts.get("listing_reviews",0))}</a>'
            '<a class="dd-item" href="/admin/users">User Roles</a>'
            '<a class="dd-item" href="/admin/permissions">Permissions</a>'
            '<a class="dd-item" href="/admin/audit">Audit Log</a>'
            '<a class="dd-item" href="/property-manager/search">Global Search</a>'
        )

    pm_items = ""
    if role in ("property_manager","admin"):
        pm_items = (
            '<div class="dd-sep"></div>'
            '<div class="menu-title">Operations</div>'
            f'<a class="dd-item" href="/manager/queue">Task Queue {_menu_badge(counts.get("queue_total",0))}</a>'
            '<a class="dd-item" href="/property-manager/search">Global Search</a>'
            f'<a class="dd-item" href="/manager/maintenance">Maintenance {_menu_badge(counts.get("maintenance_open",0))}</a>'
            f'<a class="dd-item" href="/manager/payments">Payments {_menu_badge(counts.get("payments_submitted",0))}</a>'
            f'<a class="dd-item" href="/manager/checks">Property Checks {_menu_badge(counts.get("checks_pending",0))}</a>'
            f'<a class="dd-item" href="/manager/inquiries">Inquiries {_menu_badge(counts.get("inquiries_open",0))}</a>'
            f'<a class="dd-item" href="/manager/applications">Applications {_menu_badge(counts.get("applications_pending",0))}</a>'
            '<div class="menu-title">Portfolio</div>'
            '<a class="dd-item" href="/manager/rent-roll">Rent Roll</a>'
            '<a class="dd-item" href="/manager/analytics">Analytics</a>'
            '<a class="dd-item" href="/manager/properties">Properties</a>'
            '<a class="dd-item" href="/manager/property/new">Register Property</a>'
            '<a class="dd-item" href="/manager/leases">Leases</a>'
            f'<a class="dd-item" href="/manager/listing-requests">Listing Submissions {_menu_badge(counts.get("listing_reviews",0))}</a>'
            f'<a class="dd-item" href="/manager/tenants">Tenant Sync {_menu_badge(counts.get("invites_pending",0))}</a>'
        )
    changelog_item = '<a class="dd-item" href="/changelog">Changelog</a>' if role == "admin" else ""
    favorites_item = '<a class="dd-item" href="/favorites">Favorites</a>' if role == "tenant" else ""
    tenant_pay_items = ""
    if role == "tenant":
        tenant_pay_items = (
            '<a class="dd-item" href="/tenant/payment-methods">Payment Methods</a>'
            '<a class="dd-item" href="/tenant/autopay">Autopay</a>'
        )
    search_form = (
        "<form class='nav-search-form' method='GET' action='/search'>"
        "<input class='nav-search-input' name='q' placeholder='Search...' aria-label='Search'>"
        "</form>"
    )

    return (
        search_form +
        '<div class="profile">'
          '<button class="profile-btn" type="button" aria-expanded="false">'
            f'<span class="avatar">{initial}</span>'
            f'<span class="profile-name">{name}</span>'
            f'<span class="badge {mode_class}">{mode}</span>'
            f'{alert_badge}'
            '<span class="caret">&#9662;</span>'
          '</button>'
          '<div class="profile-panel" role="menu" aria-label="Account menu">'
            '<form method="POST" action="/logout" style="margin:0;">'
              '<button class="dd-item btn-link" type="submit">Log out</button>'
            '</form>'
            '<div class="dd-sep"></div>'
            f'<a class="dd-item" href="{d}">Dashboard</a>'
            '<a class="dd-item" href="/profile">Profile</a>'
            f'{favorites_item}'
            f'{tenant_pay_items}'
            '<a class="dd-item" href="/messages">Messages</a>'
            '<a class="dd-item" href="/search">Search</a>'
            f'<a class="dd-item" href="/notifications">Alerts {_menu_badge(unread)}</a>'
            '<a class="dd-item" href="/notifications/preferences">Alert Preferences</a>'
            '<a class="dd-item" href="/onboarding">Onboarding</a>'
            f'{changelog_item}'
            f'{pm_items}'
            f'{owner_items}'
          '</div>'
          f'<span id="atlasRoleMarker" data-role="{esc(role)}" data-home="{esc(d)}" style="display:none;"></span>'
        '</div>'
    )


def nav_menu(user, path="/"):
    # Hamburger menu items (mobile). Mirrors desktop actions.
    if not user:
        return (
            '<a class="menu-item" href="/register">Register</a>'
            '<a class="menu-item" href="/login">Log in</a>'
        )

    role = normalize_role(user.get("role"))
    d = role_home(role)
    counts = menu_counts_for_user(user)
    unread = to_int(counts.get("alerts"), 0)

    items = (
        '<form method="POST" action="/logout" style="margin:0;">'
          '<button class="menu-item btn-link" type="submit">Log out</button>'
        '</form>'
        '<div class="menu-sep"></div>'
        f'<a class="menu-item" href="{d}">Dashboard</a>'
        '<a class="menu-item" href="/profile">Profile</a>'
        + ('<a class="menu-item" href="/favorites">Favorites</a>' if role=="tenant" else '')
        + ('<a class="menu-item" href="/tenant/payment-methods">Payment Methods</a>' if role=="tenant" else '')
        + ('<a class="menu-item" href="/tenant/autopay">Autopay</a>' if role=="tenant" else '')
        + '<a class="menu-item" href="/messages">Messages</a>'
        + '<a class="menu-item" href="/search">Search</a>'
        + f'<a class="menu-item" href="/notifications">Alerts {_menu_badge(unread)}</a>'
        + '<a class="menu-item" href="/notifications/preferences">Alert Preferences</a>'
        + '<a class="menu-item" href="/onboarding">Onboarding</a>'
        + ('<a class="menu-item" href="/changelog">Changelog</a>' if role=="admin" else '')
    )

    if role in ("property_manager","admin"):
        items += (
            '<div class="menu-sep"></div>'
            '<div class="menu-title">Operations</div>'
            f'<a class="menu-item" href="/manager/queue">Task Queue {_menu_badge(counts.get("queue_total",0))}</a>'
            '<a class="menu-item" href="/property-manager/search">Global Search</a>'
            f'<a class="menu-item" href="/manager/maintenance">Maintenance {_menu_badge(counts.get("maintenance_open",0))}</a>'
            f'<a class="menu-item" href="/manager/payments">Payments {_menu_badge(counts.get("payments_submitted",0))}</a>'
            f'<a class="menu-item" href="/manager/checks">Property Checks {_menu_badge(counts.get("checks_pending",0))}</a>'
            f'<a class="menu-item" href="/manager/inquiries">Inquiries {_menu_badge(counts.get("inquiries_open",0))}</a>'
            f'<a class="menu-item" href="/manager/applications">Applications {_menu_badge(counts.get("applications_pending",0))}</a>'
            '<div class="menu-title">Portfolio</div>'
            '<a class="menu-item" href="/manager/rent-roll">Rent Roll</a>'
            '<a class="menu-item" href="/manager/analytics">Analytics</a>'
            '<a class="menu-item" href="/manager/properties">Properties</a>'
            '<a class="menu-item" href="/manager/property/new">Register Property</a>'
            '<a class="menu-item" href="/manager/leases">Leases</a>'
            f'<a class="menu-item" href="/manager/listing-requests">Listing Submissions {_menu_badge(counts.get("listing_reviews",0))}</a>'
            f'<a class="menu-item" href="/manager/tenants">Tenant Sync {_menu_badge(counts.get("invites_pending",0))}</a>'
        )

    if role == "admin":
        items += (
            '<div class="menu-sep"></div>'
            '<div class="menu-title">Admin</div>'
            '<a class="menu-item" href="/admin">Admin Console</a>'
            f'<a class="menu-item" href="/admin/submissions">Submissions {_menu_badge(counts.get("listing_reviews",0))}</a>'
            '<a class="menu-item" href="/admin/users">User Roles</a>'
            '<a class="menu-item" href="/admin/permissions">Permissions</a>'
            '<a class="menu-item" href="/admin/audit">Audit Log</a>'
            '<a class="menu-item" href="/property-manager/search">Global Search</a>'
        )

    return items



# â•
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HANDLER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•




# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def main():
    from .http_handler import H
    setup_logging()
    log_event(logging.INFO, "atlasbahamas_starting", host=HOST, port=PORT, prod_mode=PROD_MODE)
    bootstrap_files()
    ensure_db()
    if CLEAR_SESSIONS_ON_START:
        clear_active_sessions()
        log_event(logging.INFO, "sessions_cleared_on_startup")
    log_event(logging.INFO, "upload_storage", path=str(UPLOAD_DIR))
    if ENFORCE_HTTPS:
        log_event(logging.INFO, "https_enforcement_enabled", force_secure_cookies=FORCE_SECURE_COOKIES)
    if not _is_local_host_value(HOST):
        log_event(logging.WARNING, "builtin_server_warning", detail="ThreadingHTTPServer is not recommended for internet-facing production")
    if not(TEMPLATES_DIR/"base.html").exists():
        log_event(logging.CRITICAL, "fatal_missing_template", template=str(TEMPLATES_DIR/"base.html"))
        sys.exit(1)
    httpd=ThreadingHTTPServer((HOST,PORT),H)
    log_event(logging.INFO, "atlasbahamas_running", url=f"http://{HOST}:{PORT}")
    if SEED_DEMO_DATA:
        log_event(logging.WARNING, "demo_seed_enabled", detail="SEED_DEMO_DATA=1 should only be used for local testing.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log_event(logging.INFO, "atlasbahamas_stopped")
        httpd.shutdown()

if __name__=="__main__":
    main()





