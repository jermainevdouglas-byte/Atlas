import http.cookiejar
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("ATLAS_ROLE_TEST_PORT", "5092"))


CREDS = {
    "tenant": ("tenant1", "AtlasTenant!1"),
    "landlord": ("landlord1", "AtlasLandlord!1"),
    "manager": ("manager1", "AtlasManager!1"),
    "admin": ("admin1", "AtlasAdmin!1"),
}


def build_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def get_cookie(jar, name):
    for c in jar:
        if c.name == name:
            return c.value
    return ""


def req(opener, method, path, data=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    payload = None
    headers = {}
    if data is not None:
        payload = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        res = opener.open(r, timeout=8)
        return res.getcode(), res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def login_as(role):
    opener, jar = build_opener()
    un, pw = CREDS[role]
    req(opener, "POST", "/login", {"username": un, "password": pw})
    return opener, jar


def main():
    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    env["PORT"] = str(PORT)
    env["DATABASE_PATH"] = str(BASE_DIR / "data" / "atlas.sqlite")
    p = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    matrix = [
        ("/tenant", "Tenant Dashboard", {"tenant", "admin"}),
        ("/tenant/ledger", "Tenant Ledger", {"tenant", "admin"}),
        # Landlord + Manager are merged to Property Manager; both seeded accounts should access both toolsets.
        ("/landlord", "Landlord Dashboard", {"landlord", "manager", "admin"}),
        ("/landlord/tenants", "Tenant Sync", {"landlord", "manager", "admin"}),
        ("/manager", "Manager Dashboard", {"landlord", "manager", "admin"}),
        ("/manager/properties", "Properties registered to your manager account.", {"landlord", "manager", "admin"}),
        ("/manager/payments", "All Payments", {"landlord", "manager", "admin"}),
        ("/manager/listings", "Manage Listings", {"admin"}),
        ("/admin", "Admin Console", {"admin"}),
        ("/admin/submissions", "Pending submissions awaiting approval.", {"admin"}),
    ]

    checks = {}
    try:
        time.sleep(1.2)
        for role in ("tenant", "landlord", "manager", "admin"):
            opener, jar = login_as(role)
            csrf = get_cookie(jar, "ATLAS_CSRF")
            checks[f"{role}_csrf"] = bool(csrf)
            for path, marker, allowed_roles in matrix:
                code, body = req(opener, "GET", path)
                granted = marker in body
                expected = role in allowed_roles
                checks[f"{role}:{path}"] = (granted == expected) and code in (200, 302, 403)
            post_code, post_body = req(opener, "POST", "/admin/submissions/approve_all", {"csrf_token": csrf})
            post_granted = "Pending submissions awaiting approval." in post_body
            checks[f"{role}:post_admin_approve_all"] = (post_granted == (role == "admin")) and post_code in (200, 302, 403)

        print("ROLE_MATRIX_CHECKS", checks)
        if not all(checks.values()):
            raise SystemExit(1)
    finally:
        p.terminate()
        try:
            p.wait(timeout=4)
        except Exception:
            p.kill()


if __name__ == "__main__":
    main()

