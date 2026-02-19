"""AtlasBahamas web app runtime (Flask + SQLite + secure session cookies)."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Flask, abort, g, jsonify, redirect, request, send_from_directory, session

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

LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_ATTEMPTS_LOCK = Lock()


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
    raw = (os.getenv("ATLASBAHAMAS_DB_PATH") or "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DB_PATH


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def _ip_identifier_key(ip: str, identifier: str) -> str:
    return f"{str(ip or '').strip()}::{str(identifier or '').strip().lower()}"


def _login_rate_status(ip: str, identifier: str) -> tuple[bool, int]:
    max_attempts = _env_int("MAX_LOGIN_ATTEMPTS", 5)
    window_secs = _env_int("LOGIN_ATTEMPT_TIMEOUT_MINUTES", 15) * 60
    key = _ip_identifier_key(ip, identifier)
    now = time.time()

    with LOGIN_ATTEMPTS_LOCK:
        bucket = LOGIN_ATTEMPTS.get(key, [])
        bucket = [ts for ts in bucket if (now - ts) < window_secs]
        LOGIN_ATTEMPTS[key] = bucket
        if len(bucket) >= max_attempts:
            wait = int(window_secs - (now - min(bucket)))
            return True, max(wait, 1)
        return False, 0


def _login_rate_fail(ip: str, identifier: str) -> None:
    max_attempts = _env_int("MAX_LOGIN_ATTEMPTS", 5)
    key = _ip_identifier_key(ip, identifier)
    now = time.time()
    with LOGIN_ATTEMPTS_LOCK:
        bucket = LOGIN_ATTEMPTS.get(key, [])
        bucket.append(now)
        LOGIN_ATTEMPTS[key] = bucket[-max(max_attempts * 3, 15) :]


def _login_rate_clear(ip: str, identifier: str) -> None:
    key = _ip_identifier_key(ip, identifier)
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(key, None)


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), int(status)


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    app.config["SECRET_KEY"] = (
        os.getenv("SECRET_KEY")
        or os.getenv("FLASK_SECRET_KEY")
        or secrets.token_urlsafe(48)
    )
    app.config["SESSION_COOKIE_NAME"] = os.getenv("SESSION_COOKIE_NAME", "ATLASBAHAMAS_SESSION")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = _env_bool("COOKIE_SECURE", False)
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=_env_int("SESSION_TIMEOUT_MINUTES", 60))
    app.config["JSON_SORT_KEYS"] = False

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
                """
            )
            conn.commit()
        finally:
            conn.close()

    def seed_demo_users() -> None:
        if not _env_bool("SEED_DEMO_USERS", True):
            return

        rounds = _env_int("PASSWORD_HASH_ROUNDS", 240000)
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
                salt_hex, pw_hash = _hash_password(row["password"], rounds=rounds)
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

    @app.after_request
    def apply_headers(response):
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
        return response

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "atlasbahamas", "ts": _utc_now_iso()})

    @app.get("/api/session")
    def api_session():
        user = current_user()
        if not user:
            return jsonify({"ok": True, "authenticated": False, "session": None})
        return jsonify({"ok": True, "authenticated": True, "session": user})

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

        rounds = _env_int("PASSWORD_HASH_ROUNDS", 240000)
        salt_hex, pw_hash = _hash_password(password, rounds=rounds)
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
        return jsonify({"ok": True, "session": payload, "user": payload})

    @app.post("/api/login")
    def api_login():
        data = request.get_json(silent=True) or {}
        identifier = str(data.get("identifier") or "").strip().lower()
        password = str(data.get("password") or "")
        expected_role = _normalize_role(str(data.get("role") or ""))
        remote_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        remote_ip = str(remote_ip).split(",")[0].strip()

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

        rounds = _env_int("PASSWORD_HASH_ROUNDS", 240000)
        if not _verify_password(password, str(row["password_salt"]), str(row["password_hash"]), rounds=rounds):
            _login_rate_fail(remote_ip, identifier)
            return _json_error("Invalid credentials.", status=401)

        _login_rate_clear(remote_ip, identifier)
        payload = session_payload(row)
        session["auth"] = payload
        session.permanent = True
        return jsonify({"ok": True, "session": payload, "user": payload})

    @app.post("/api/logout")
    def api_logout():
        session.pop("auth", None)
        return jsonify({"ok": True, "message": "Logged out."})

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

    @app.get("/api/dashboard/tenant")
    def api_dashboard_tenant():
        user, err = require_auth("tenant")
        if err:
            return err
        return jsonify(
            {
                "ok": True,
                "session": user,
                "kpis": {"rentDue": 1250, "daysToDue": 5, "openRequests": 1, "receipts": 12},
            }
        )

    @app.get("/api/dashboard/landlord")
    def api_dashboard_landlord():
        user, err = require_auth("landlord")
        if err:
            return err
        return jsonify(
            {
                "ok": True,
                "session": user,
                "kpis": {"properties": 4, "occupied": 3, "monthlyRevenue": 4800, "openRequests": 2},
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

