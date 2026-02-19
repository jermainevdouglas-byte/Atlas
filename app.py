"""AtlasBahamas web app runtime (Flask + SQLite + secure session cookies)."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, g, jsonify, redirect, request, send_from_directory, session

try:
    from redis_client import RedisClient
except Exception:
    RedisClient = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = DATA_DIR / "atlasbahamas.sqlite"

PASSWORD_POLICY_TEXT = "minimum 10 chars, uppercase, lowercase, number, and symbol"

LISTINGS_DATA = [
    {"id": "coral-heights-4b", "name": "Coral Heights 4B", "beds": 2, "baths": 1, "city": "Nassau", "price_monthly": 1250},
    {"id": "harbor-walk-2a", "name": "Harbor Walk 2A", "beds": 1, "baths": 1, "city": "Nassau", "price_monthly": 1050},
    {"id": "ocean-ridge-7c", "name": "Ocean Ridge 7C", "beds": 3, "baths": 2, "city": "Nassau", "price_monthly": 1780},
]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def _db_path() -> Path:
    raw = (
        os.getenv("ATLASBAHAMAS_DB_PATH")
        or os.getenv("DATABASE_PATH")
        or ""
    ).strip()
    if raw:
        return Path(raw)
    return DEFAULT_DB_PATH


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip().lower() for part in str(raw).split(",") if part.strip()]


def _request_is_secure(req) -> bool:
    if req.is_secure:
        return True
    xf_proto = str(req.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return xf_proto == "https"


def _is_local_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    return h in {"localhost", "127.0.0.1", "::1"}


def _host_allowed(host: str, rules: list[str]) -> bool:
    if not rules:
        return True

    h = str(host or "").split(":")[0].strip().lower()
    for rule in rules:
        r = str(rule or "").strip().lower()
        if not r:
            continue
        if r.startswith("."):
            base = r[1:]
            if h == base or h.endswith(r):
                return True
        elif h == r:
            return True
    return False


def _is_placeholder_secret(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    markers = (
        "replace",
        "changeme",
        "example",
        "placeholder",
        "set_in",
        "set-me",
        "your_secret",
        "secret_key",
    )
    if len(text) < 24:
        return True
    return any(marker in text for marker in markers)


def _password_policy_errors(password: str) -> list[str]:
    value = str(password or "")
    errs = []
    if len(value) < 10:
        errs.append("minimum 10 characters")
    if not re.search(r"[A-Z]", value):
        errs.append("at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        errs.append("at least one lowercase letter")
    if not re.search(r"[0-9]", value):
        errs.append("at least one number")
    if not re.search(r"[^A-Za-z0-9]", value):
        errs.append("at least one symbol")
    return errs


def _normalize_role(role: str) -> str:
    value = str(role or "").strip().lower()
    if value in {"tenant"}:
        return "tenant"
    if value in {"landlord", "property_manager", "manager"}:
        return "landlord"
    return ""


def _pbkdf2_hash(password: str, salt_hex: str, rounds: int) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, rounds)
    return digest.hex()


def _hash_password(password: str, rounds: int | None = None) -> tuple[str, str]:
    use_rounds = int(rounds if rounds is not None else _env_int("PASSWORD_HASH_ROUNDS", 240000))
    salt_hex = secrets.token_hex(16)
    return salt_hex, _pbkdf2_hash(password, salt_hex, use_rounds)


def _verify_password(password: str, salt_hex: str, expected_hash: str, rounds: int) -> bool:
    computed = _pbkdf2_hash(password, salt_hex, rounds)
    return hmac.compare_digest(str(expected_hash or ""), computed)


def _serialize_payment(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "tenantUserId": int(row["tenant_user_id"]),
        "tenantName": str(row["tenant_name"]),
        "tenantUsername": str(row["tenant_username"]),
        "amountCents": int(row["amount_cents"]),
        "amount": round(int(row["amount_cents"]) / 100.0, 2),
        "paymentMonth": str(row["payment_month"]),
        "status": str(row["status"]),
        "note": str(row["note"] or ""),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"] or ""),
    }


def _serialize_maintenance(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "tenantUserId": int(row["tenant_user_id"]),
        "tenantName": str(row["tenant_name"]),
        "tenantUsername": str(row["tenant_username"]),
        "subject": str(row["subject"]),
        "details": str(row["details"]),
        "severity": str(row["severity"]),
        "status": str(row["status"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"] or ""),
    }


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    prod_mode = _env_bool("PROD_MODE", False)
    enforce_https = _env_bool("ENFORCE_HTTPS", prod_mode)
    force_secure_cookies = _env_bool("FORCE_SECURE_COOKIES", prod_mode)
    security_headers_enabled = _env_bool("SECURITY_HEADERS_ENABLED", True)
    session_timeout_minutes = max(5, _env_int("SESSION_TIMEOUT_MINUTES", 60))
    password_rounds = max(120000, _env_int("PASSWORD_HASH_ROUNDS", 240000))
    login_max_attempts = max(2, _env_int("MAX_LOGIN_ATTEMPTS", 5))
    login_lockout_minutes = max(1, _env_int("LOGIN_ATTEMPT_TIMEOUT_MINUTES", 15))
    login_window_seconds = login_lockout_minutes * 60
    allowed_hosts = _split_csv(os.getenv("ALLOWED_HOSTS"))
    csrf_trusted_hosts = _split_csv(os.getenv("CSRF_TRUSTED_HOSTS")) or allowed_hosts

    secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        if prod_mode:
            raise RuntimeError("SECRET_KEY is required when PROD_MODE=1.")
        secret_key = secrets.token_urlsafe(48)
    if prod_mode and _is_placeholder_secret(secret_key):
        raise RuntimeError("SECRET_KEY appears to be placeholder text. Set a strong random value.")

    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_NAME"] = os.getenv("SESSION_COOKIE_NAME", "ATLASBAHAMAS_SESSION")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = force_secure_cookies or _env_bool("COOKIE_SECURE", False)
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=session_timeout_minutes)
    app.config["JSON_SORT_KEYS"] = False

    redis_client = None
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if RedisClient is not None and redis_url:
        try:
            candidate = RedisClient(redis_url)
            if candidate.enabled:
                redis_client = candidate
        except Exception:
            redis_client = None

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            db_path = _db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            g.db = conn
        return g.db

    @app.teardown_appcontext
    def _close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def init_db() -> None:
        conn = sqlite3.connect(str(_db_path()), timeout=10)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN('tenant','landlord')),
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contact_messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS login_attempts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    window_started INTEGER NOT NULL DEFAULT 0,
                    locked_until INTEGER NOT NULL DEFAULT 0,
                    last_failed_at TEXT NOT NULL,
                    UNIQUE(ip, identifier)
                );

                CREATE TABLE IF NOT EXISTS tenant_payments(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_user_id INTEGER NOT NULL,
                    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                    payment_month TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN('submitted','received','rejected')),
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY(tenant_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS maintenance_requests(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    details TEXT NOT NULL,
                    severity TEXT NOT NULL CHECK(severity IN('low','medium','high','urgent')),
                    status TEXT NOT NULL CHECK(status IN('open','in_progress','resolved','closed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY(tenant_user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def seed_demo_users() -> None:
        if not _env_bool("SEED_DEMO_USERS", not prod_mode):
            return

        conn = sqlite3.connect(str(_db_path()), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            count = conn.execute("SELECT COUNT(1) AS n FROM users").fetchone()["n"]
            if int(count) > 0:
                return

            demos = [
                {
                    "full_name": "Atlas Tenant Demo",
                    "email": "tenant@atlasbahamas.demo",
                    "username": "tenantdemo",
                    "role": "tenant",
                    "password": os.getenv("DEMO_TENANT_PASSWORD", "AtlasTenant!2026"),
                },
                {
                    "full_name": "Atlas Landlord Demo",
                    "email": "landlord@atlasbahamas.demo",
                    "username": "landlorddemo",
                    "role": "landlord",
                    "password": os.getenv("DEMO_LANDLORD_PASSWORD", "AtlasLandlord!2026"),
                },
            ]

            for row in demos:
                salt_hex, pw_hash = _hash_password(row["password"], rounds=password_rounds)
                conn.execute(
                    "INSERT INTO users(full_name,email,username,role,password_salt,password_hash,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (
                        row["full_name"],
                        row["email"].lower(),
                        row["username"].lower(),
                        row["role"],
                        salt_hex,
                        pw_hash,
                        _utc_now_iso(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _json_error(message: str, status: int = 400):
        return jsonify({"ok": False, "error": str(message)}), int(status)

    def _ensure_csrf_token(reset: bool = False) -> str:
        token = str(session.get("csrf_token") or "")
        if reset or not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def _is_local_request_host() -> bool:
        host = str(request.host or "").split(":")[0].strip().lower()
        if host and _is_local_host(host):
            return True
        forwarded = str(request.headers.get("X-Forwarded-Host") or "").split(",")[0].split(":")[0].strip().lower()
        return bool(forwarded and _is_local_host(forwarded))

    def session_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "userId": int(row["id"]),
            "fullName": str(row["full_name"]),
            "email": str(row["email"]),
            "username": str(row["username"]),
            "role": _normalize_role(str(row["role"])),
        }

    def current_user() -> dict[str, Any] | None:
        auth = session.get("auth")
        if not auth or not isinstance(auth, dict):
            return None
        user_id = int(auth.get("userId", 0) or 0)
        if user_id <= 0:
            return None

        conn = get_db()
        row = conn.execute(
            "SELECT id,full_name,email,username,role FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            session.pop("auth", None)
            return None
        payload = session_payload(row)
        session["auth"] = payload
        return payload

    def require_auth(expected_role: str | None = None):
        user = current_user()
        if not user:
            return None, _json_error("Authentication required.", status=401)
        if expected_role and _normalize_role(user["role"]) != _normalize_role(expected_role):
            return None, _json_error("Forbidden for this role.", status=403)
        return user, None

    def _login_rate_status(remote_ip: str, identifier: str) -> tuple[bool, int]:
        key_ip = str(remote_ip or "unknown").strip() or "unknown"
        key_id = str(identifier or "").strip().lower()
        now = int(time.time())
        conn = get_db()
        row = conn.execute(
            "SELECT attempts,window_started,locked_until FROM login_attempts WHERE ip=? AND identifier=?",
            (key_ip, key_id),
        ).fetchone()
        if not row:
            return False, 0

        locked_until = int(row["locked_until"] or 0)
        if locked_until > now:
            return True, max(1, locked_until - now)

        attempts = int(row["attempts"] or 0)
        window_started = int(row["window_started"] or 0)
        if attempts <= 0 or window_started <= 0 or (now - window_started) >= login_window_seconds:
            conn.execute("DELETE FROM login_attempts WHERE ip=? AND identifier=?", (key_ip, key_id))
            conn.commit()
            return False, 0

        return False, 0

    def _login_rate_fail(remote_ip: str, identifier: str) -> None:
        key_ip = str(remote_ip or "unknown").strip() or "unknown"
        key_id = str(identifier or "").strip().lower()
        now = int(time.time())
        conn = get_db()
        row = conn.execute(
            "SELECT attempts,window_started FROM login_attempts WHERE ip=? AND identifier=?",
            (key_ip, key_id),
        ).fetchone()

        attempts = 0
        window_started = now
        if row:
            attempts = int(row["attempts"] or 0)
            window_started = int(row["window_started"] or now)
            if window_started <= 0 or (now - window_started) >= login_window_seconds:
                attempts = 0
                window_started = now

        attempts += 1
        locked_until = now + login_window_seconds if attempts >= login_max_attempts else 0
        conn.execute(
            """
            INSERT INTO login_attempts(ip,identifier,attempts,window_started,locked_until,last_failed_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(ip,identifier)
            DO UPDATE SET attempts=excluded.attempts,
                          window_started=excluded.window_started,
                          locked_until=excluded.locked_until,
                          last_failed_at=excluded.last_failed_at
            """,
            (key_ip, key_id, attempts, window_started, locked_until, _utc_now_iso()),
        )
        conn.commit()

        if redis_client is not None and redis_client.enabled:
            redis_client.rate_limit(
                key=f"atlas:login:{key_ip}:{key_id}",
                limit=login_max_attempts,
                window_seconds=login_window_seconds,
            )

    def _login_rate_clear(remote_ip: str, identifier: str) -> None:
        key_ip = str(remote_ip or "unknown").strip() or "unknown"
        key_id = str(identifier or "").strip().lower()
        conn = get_db()
        conn.execute("DELETE FROM login_attempts WHERE ip=? AND identifier=?", (key_ip, key_id))
        conn.commit()

    @app.before_request
    def request_guards():
        host = str(request.host or "").split(":")[0].strip().lower()
        if host and allowed_hosts and not _is_local_host(host) and not _host_allowed(host, allowed_hosts):
            return _json_error("Host header not allowed.", status=400)

        if enforce_https and not _request_is_secure(request) and not _is_local_request_host():
            if request.path.startswith("/api/"):
                return _json_error("HTTPS is required.", status=426)
            target = request.url.replace("http://", "https://", 1)
            return redirect(target, code=308)

        _ensure_csrf_token()

        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        csrf_exempt_paths = {"/api/login", "/api/register"}
        if request.path.startswith("/api/") and request.method in write_methods and request.path not in csrf_exempt_paths:
            req_host = host
            if not req_host:
                req_host = str(request.headers.get("X-Forwarded-Host") or "").split(",")[0].split(":")[0].strip().lower()
            if req_host and csrf_trusted_hosts and not _is_local_host(req_host) and not _host_allowed(req_host, csrf_trusted_hosts):
                return _json_error("Untrusted request host.", status=400)

            supplied = str(request.headers.get("X-CSRF-Token") or "").strip()
            if not supplied:
                payload = request.get_json(silent=True) or {}
                if isinstance(payload, dict):
                    supplied = str(payload.get("csrfToken") or "").strip()
            expected = str(session.get("csrf_token") or "")
            if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                return _json_error("CSRF token missing or invalid.", status=400)

    @app.after_request
    def apply_headers(response):
        if not security_headers_enabled:
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "script-src 'self'; connect-src 'self'"
        )
        if enforce_https and (_request_is_secure(request) or prod_mode):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/health")
    def health():
        db_ok = True
        try:
            conn = get_db()
            conn.execute("SELECT 1").fetchone()
        except Exception:
            db_ok = False

        redis_ok = None
        if redis_client is not None:
            redis_ok = bool(redis_client.ping())

        ok = db_ok and (redis_ok is None or redis_ok)
        return jsonify(
            {
                "ok": ok,
                "service": "atlasbahamas",
                "db": db_ok,
                "redis": redis_ok,
                "ts": _utc_now_iso(),
            }
        ), (200 if ok else 503)

    @app.get("/api/session")
    def api_session():
        user = current_user()
        csrf_token = _ensure_csrf_token()
        if not user:
            return jsonify({"ok": True, "authenticated": False, "session": None, "csrfToken": csrf_token})
        return jsonify({"ok": True, "authenticated": True, "session": user, "csrfToken": csrf_token})

    @app.post("/api/register")
    def api_register():
        data = request.get_json(silent=True) or {}
        full_name = str(data.get("fullName") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        username = str(data.get("username") or "").strip().lower()
        role = _normalize_role(str(data.get("role") or ""))
        password = str(data.get("password") or "")
        password_confirm = str(data.get("passwordConfirm") or "")

        if not full_name or not email or not username or not role or not password or not password_confirm:
            return _json_error("All registration fields are required.", status=400)
        if password != password_confirm:
            return _json_error("Passwords must match.", status=400)
        if not re.fullmatch(r"[a-z0-9._-]{3,32}", username):
            return _json_error("Username must be 3-32 chars (letters, numbers, . _ -).", status=400)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return _json_error("Valid email is required.", status=400)
        pw_errs = _password_policy_errors(password)
        if pw_errs:
            return _json_error("Password must include: " + ", ".join(pw_errs) + ".", status=400)

        salt_hex, pw_hash = _hash_password(password, rounds=password_rounds)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users(full_name,email,username,role,password_salt,password_hash,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (full_name, email, username, role, salt_hex, pw_hash, _utc_now_iso()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return _json_error("Username or email already exists.", status=409)

        row = conn.execute(
            "SELECT id,full_name,email,username,role FROM users WHERE username=?",
            (username,),
        ).fetchone()
        payload = session_payload(row)
        session["auth"] = payload
        session.permanent = True
        csrf_token = _ensure_csrf_token(reset=True)
        return jsonify({"ok": True, "session": payload, "user": payload, "csrfToken": csrf_token})

    @app.post("/api/login")
    def api_login():
        data = request.get_json(silent=True) or {}
        identifier = str(data.get("identifier") or "").strip().lower()
        password = str(data.get("password") or "")
        expected_role = _normalize_role(str(data.get("role") or ""))
        remote_ip = str(request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        if not remote_ip:
            remote_ip = "unknown"

        if not identifier or not password:
            return _json_error("Username/email and password are required.", status=400)

        blocked, wait_sec = _login_rate_status(remote_ip, identifier)
        if blocked:
            wait_min = max(1, int(round(wait_sec / 60.0)))
            return _json_error(f"Login locked. Try again in about {wait_min} minute(s).", status=429)

        conn = get_db()
        row = conn.execute(
            "SELECT id,full_name,email,username,role,password_salt,password_hash "
            "FROM users WHERE lower(email)=? OR lower(username)=? LIMIT 1",
            (identifier, identifier),
        ).fetchone()
        if not row:
            _login_rate_fail(remote_ip, identifier)
            return _json_error("Invalid credentials.", status=401)

        row_role = _normalize_role(str(row["role"]))
        if expected_role and row_role != expected_role:
            _login_rate_fail(remote_ip, identifier)
            return _json_error("Selected role does not match this account.", status=403)

        if not _verify_password(password, str(row["password_salt"]), str(row["password_hash"]), rounds=password_rounds):
            _login_rate_fail(remote_ip, identifier)
            return _json_error("Invalid credentials.", status=401)

        _login_rate_clear(remote_ip, identifier)
        payload = session_payload(row)
        session["auth"] = payload
        session.permanent = True
        csrf_token = _ensure_csrf_token(reset=True)
        return jsonify({"ok": True, "session": payload, "user": payload, "csrfToken": csrf_token})

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        _ensure_csrf_token(reset=True)
        return jsonify({"ok": True, "message": "Logged out.", "csrfToken": session.get("csrf_token")})

    @app.post("/api/contact")
    def api_contact():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        email = str(data.get("email") or "").strip()
        message = str(data.get("message") or "").strip()
        if not name or not email or not message:
            return _json_error("All contact fields are required.", status=400)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return _json_error("Valid email is required.", status=400)

        user = current_user()
        user_id = int(user["userId"]) if user else None
        conn = get_db()
        conn.execute(
            "INSERT INTO contact_messages(user_id,name,email,message,created_at) VALUES(?,?,?,?,?)",
            (user_id, name, email, message, _utc_now_iso()),
        )
        conn.commit()
        return jsonify({"ok": True, "message": "Message sent."})

    @app.get("/api/listings")
    def api_listings():
        return jsonify({"ok": True, "listings": LISTINGS_DATA})

    @app.get("/api/workflow/payments")
    def api_workflow_payments():
        user, err = require_auth()
        if err:
            return err

        conn = get_db()
        role = _normalize_role(user["role"])
        if role == "tenant":
            rows = conn.execute(
                """
                SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                       tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
                FROM tenant_payments tp
                JOIN users u ON u.id = tp.tenant_user_id
                WHERE tp.tenant_user_id=?
                ORDER BY tp.id DESC
                LIMIT 60
                """,
                (int(user["userId"]),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                       tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
                FROM tenant_payments tp
                JOIN users u ON u.id = tp.tenant_user_id
                ORDER BY tp.id DESC
                LIMIT 120
                """
            ).fetchall()
        return jsonify({"ok": True, "payments": [_serialize_payment(row) for row in rows]})

    @app.post("/api/workflow/payment")
    def api_workflow_payment_submit():
        user, err = require_auth("tenant")
        if err:
            return err

        data = request.get_json(silent=True) or {}
        note = str(data.get("note") or "").strip()[:280]
        payment_month = str(data.get("paymentMonth") or _utc_month()).strip()
        if not re.fullmatch(r"\d{4}-\d{2}", payment_month):
            return _json_error("paymentMonth must be YYYY-MM.", status=400)

        raw_amount = data.get("amount")
        try:
            amount = float(raw_amount)
        except Exception:
            amount = -1.0
        amount_cents = int(round(amount * 100))
        if amount_cents < 100:
            return _json_error("Amount must be at least 1.00.", status=400)
        if amount_cents > 500000000:
            return _json_error("Amount exceeds allowed limit.", status=400)

        conn = get_db()
        conn.execute(
            """
            INSERT INTO tenant_payments(tenant_user_id,amount_cents,payment_month,status,note,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (int(user["userId"]), amount_cents, payment_month, "submitted", note, _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
            FROM tenant_payments tp
            JOIN users u ON u.id = tp.tenant_user_id
            WHERE tp.id = last_insert_rowid()
            """
        ).fetchone()
        return jsonify({"ok": True, "payment": _serialize_payment(row)})

    @app.post("/api/workflow/payment/<int:payment_id>/status")
    def api_workflow_payment_status(payment_id: int):
        _user, err = require_auth("landlord")
        if err:
            return err

        data = request.get_json(silent=True) or {}
        status = str(data.get("status") or "").strip().lower()
        note = str(data.get("note") or "").strip()[:280]
        if status not in {"received", "rejected"}:
            return _json_error("status must be received or rejected.", status=400)

        conn = get_db()
        updated = conn.execute(
            "UPDATE tenant_payments SET status=?, note=?, updated_at=? WHERE id=?",
            (status, note, _utc_now_iso(), int(payment_id)),
        ).rowcount
        if int(updated) <= 0:
            return _json_error("Payment not found.", status=404)
        conn.commit()

        row = conn.execute(
            """
            SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
            FROM tenant_payments tp
            JOIN users u ON u.id = tp.tenant_user_id
            WHERE tp.id=?
            """,
            (int(payment_id),),
        ).fetchone()
        return jsonify({"ok": True, "payment": _serialize_payment(row)})

    @app.get("/api/workflow/maintenance")
    def api_workflow_maintenance():
        user, err = require_auth()
        if err:
            return err

        conn = get_db()
        role = _normalize_role(user["role"])
        if role == "tenant":
            rows = conn.execute(
                """
                SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                       mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
                FROM maintenance_requests mr
                JOIN users u ON u.id = mr.tenant_user_id
                WHERE mr.tenant_user_id=?
                ORDER BY mr.id DESC
                LIMIT 80
                """,
                (int(user["userId"]),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                       mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
                FROM maintenance_requests mr
                JOIN users u ON u.id = mr.tenant_user_id
                ORDER BY mr.id DESC
                LIMIT 160
                """
            ).fetchall()
        return jsonify({"ok": True, "requests": [_serialize_maintenance(row) for row in rows]})

    @app.post("/api/workflow/maintenance")
    def api_workflow_maintenance_submit():
        user, err = require_auth("tenant")
        if err:
            return err

        data = request.get_json(silent=True) or {}
        subject = str(data.get("subject") or "").strip()
        details = str(data.get("details") or "").strip()
        severity = str(data.get("severity") or "medium").strip().lower()

        if len(subject) < 3 or len(subject) > 140:
            return _json_error("Subject must be between 3 and 140 characters.", status=400)
        if len(details) < 5 or len(details) > 2000:
            return _json_error("Details must be between 5 and 2000 characters.", status=400)
        if severity not in {"low", "medium", "high", "urgent"}:
            return _json_error("severity must be low, medium, high, or urgent.", status=400)

        conn = get_db()
        conn.execute(
            """
            INSERT INTO maintenance_requests(tenant_user_id,subject,details,severity,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (int(user["userId"]), subject, details, severity, "open", _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_user_id
            WHERE mr.id = last_insert_rowid()
            """
        ).fetchone()
        return jsonify({"ok": True, "request": _serialize_maintenance(row)})

    @app.post("/api/workflow/maintenance/<int:request_id>/status")
    def api_workflow_maintenance_status(request_id: int):
        _user, err = require_auth("landlord")
        if err:
            return err

        data = request.get_json(silent=True) or {}
        status = str(data.get("status") or "").strip().lower()
        if status not in {"open", "in_progress", "resolved", "closed"}:
            return _json_error("status must be open, in_progress, resolved, or closed.", status=400)

        conn = get_db()
        updated = conn.execute(
            "UPDATE maintenance_requests SET status=?, updated_at=? WHERE id=?",
            (status, _utc_now_iso(), int(request_id)),
        ).rowcount
        if int(updated) <= 0:
            return _json_error("Maintenance request not found.", status=404)
        conn.commit()

        row = conn.execute(
            """
            SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_user_id
            WHERE mr.id=?
            """,
            (int(request_id),),
        ).fetchone()
        return jsonify({"ok": True, "request": _serialize_maintenance(row)})

    @app.get("/api/dashboard/tenant")
    def api_dashboard_tenant():
        user, err = require_auth("tenant")
        if err:
            return err

        conn = get_db()
        tenant_id = int(user["userId"])
        today = datetime.now(timezone.utc).date()
        next_due = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        days_to_due = max(0, int((next_due - today).days))

        last_payment = conn.execute(
            "SELECT amount_cents FROM tenant_payments WHERE tenant_user_id=? ORDER BY id DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        rent_due_cents = int(last_payment["amount_cents"]) if last_payment else 125000
        open_requests = conn.execute(
            "SELECT COUNT(1) AS n FROM maintenance_requests WHERE tenant_user_id=? AND status IN('open','in_progress')",
            (tenant_id,),
        ).fetchone()
        receipt_count = conn.execute(
            "SELECT COUNT(1) AS n FROM tenant_payments WHERE tenant_user_id=? AND status='received'",
            (tenant_id,),
        ).fetchone()
        payments = conn.execute(
            """
            SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
            FROM tenant_payments tp
            JOIN users u ON u.id = tp.tenant_user_id
            WHERE tp.tenant_user_id=?
            ORDER BY tp.id DESC
            LIMIT 20
            """,
            (tenant_id,),
        ).fetchall()
        requests = conn.execute(
            """
            SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_user_id
            WHERE mr.tenant_user_id=?
            ORDER BY mr.id DESC
            LIMIT 20
            """,
            (tenant_id,),
        ).fetchall()
        return jsonify(
            {
                "ok": True,
                "session": user,
                "kpis": {
                    "rentDue": round(rent_due_cents / 100.0, 2),
                    "daysToDue": days_to_due,
                    "openRequests": int(open_requests["n"] or 0),
                    "receipts": int(receipt_count["n"] or 0),
                },
                "payments": [_serialize_payment(row) for row in payments],
                "maintenance": [_serialize_maintenance(row) for row in requests],
            }
        )

    @app.get("/api/dashboard/landlord")
    def api_dashboard_landlord():
        user, err = require_auth("landlord")
        if err:
            return err

        conn = get_db()
        current_month = _utc_month()
        open_requests = conn.execute(
            "SELECT COUNT(1) AS n FROM maintenance_requests WHERE status IN('open','in_progress')"
        ).fetchone()
        active_tenants = conn.execute(
            "SELECT COUNT(DISTINCT tenant_user_id) AS n FROM tenant_payments"
        ).fetchone()
        month_revenue = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS cents FROM tenant_payments WHERE status='received' AND payment_month=?",
            (current_month,),
        ).fetchone()
        pending_payments = conn.execute(
            """
            SELECT tp.id,tp.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   tp.amount_cents,tp.payment_month,tp.status,tp.note,tp.created_at,tp.updated_at
            FROM tenant_payments tp
            JOIN users u ON u.id = tp.tenant_user_id
            WHERE tp.status='submitted'
            ORDER BY tp.id DESC
            LIMIT 40
            """
        ).fetchall()
        queue = conn.execute(
            """
            SELECT mr.id,mr.tenant_user_id,u.full_name AS tenant_name,u.username AS tenant_username,
                   mr.subject,mr.details,mr.severity,mr.status,mr.created_at,mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_user_id
            WHERE mr.status IN('open','in_progress')
            ORDER BY mr.id DESC
            LIMIT 60
            """
        ).fetchall()
        properties = len(LISTINGS_DATA)
        occupied = min(properties, int(active_tenants["n"] or 0))
        return jsonify(
            {
                "ok": True,
                "session": user,
                "kpis": {
                    "properties": properties,
                    "occupied": occupied,
                    "monthlyRevenue": round(int(month_revenue["cents"] or 0) / 100.0, 2),
                    "openRequests": int(open_requests["n"] or 0),
                },
                "pendingPayments": [_serialize_payment(row) for row in pending_payments],
                "maintenanceQueue": [_serialize_maintenance(row) for row in queue],
            }
        )

    @app.get("/")
    def home_root():
        return redirect("/AtlasBahamasHome.html", code=302)

    @app.get("/<path:filename>")
    def serve_static(filename: str):
        clean = str(filename or "").strip()
        if not clean:
            abort(404)
        if clean.startswith("api/"):
            abort(404)

        rel = Path(clean)
        if rel.is_absolute() or ".." in rel.parts:
            abort(404)

        full = (BASE_DIR / rel).resolve()
        if not full.exists() or not full.is_file():
            abort(404)
        if BASE_DIR not in full.parents:
            abort(404)

        return send_from_directory(str(BASE_DIR), clean)

    with app.app_context():
        init_db()
        seed_demo_users()

    return app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = _env_int("PORT", 5000)
    app.run(host=host, port=port, debug=False)

