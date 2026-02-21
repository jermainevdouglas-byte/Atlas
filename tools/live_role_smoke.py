#!/usr/bin/env python3
"""Live HTTPS smoke checks against the running AtlasBahamas stack."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


BASE_HTTPS = "https://localhost"
BASE_HTTP = "http://localhost"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def new_client():
    jar = CookieJar()
    ctx = ssl._create_unverified_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(jar),
        NoRedirect(),
    )
    return opener, jar


def cookie_value(jar: CookieJar, name: str) -> str:
    for c in jar:
        if c.name == name:
            return c.value
    return ""


def request(opener, method: str, path: str, data: dict[str, str] | None = None, base: str = BASE_HTTPS):
    payload = None
    headers = {}
    if data is not None:
        payload = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(base + path, data=payload, method=method, headers=headers)
    try:
        with opener.open(req, timeout=12) as res:
            body = res.read().decode("utf-8", "replace")
            return res.getcode(), body, dict(res.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, body, dict(e.headers)


def login(username: str, password: str):
    opener, jar = new_client()
    code, body, headers = request(
        opener,
        "POST",
        "/login",
        {"username": username, "password": password},
    )
    return opener, jar, code, body, headers


def location(headers: dict) -> str:
    for k, v in headers.items():
        if k.lower() == "location":
            return str(v)
    return ""


def main() -> int:
    checks: dict[str, bool] = {}
    notes: list[str] = []

    # HTTPS-only redirect check.
    http_opener = urllib.request.build_opener(NoRedirect())
    try:
        c, _, h = request(http_opener, "GET", "/health", base=BASE_HTTP)
        checks["http_health_redirects"] = c in (301, 302, 307, 308) and location(h).startswith("https://")
    except urllib.error.URLError:
        # Port 80 is intentionally closed in hardened mode.
        checks["http_health_redirects"] = True

    tenants = [f"tenant{i}" for i in range(1, 6)]
    for tenant in tenants:
        opener, jar, code, _, headers = login(tenant, "bahamas242")
        key = f"{tenant}_login"
        checks[key] = code in (301, 302) and "/tenant" in location(headers)
        csrf = cookie_value(jar, "ATLASBAHAMAS_CSRF")
        checks[f"{tenant}_csrf"] = bool(csrf)

        c, body, _ = request(opener, "GET", "/tenant/maintenance/new")
        checks[f"{tenant}_maintenance_page"] = c == 200 and "Request Maintenance" in body
        checks[f"{tenant}_has_active_lease_banner"] = "Linked Property:" in body and "No active lease linked." not in body

        desc = f"Smoke test request from {tenant} at {int(time.time())}"
        c, _, h = request(
            opener,
            "POST",
            "/tenant/maintenance/new",
            {
                "issue_type": "General",
                "urgency": "high",
                "description": desc,
                "csrf_token": csrf,
            },
        )
        loc = location(h)
        checks[f"{tenant}_maintenance_submit"] = c in (301, 302) and "/tenant/maintenance/confirmation?id=" in loc
        if not checks[f"{tenant}_maintenance_submit"]:
            notes.append(f"{tenant} maintenance submit location: {loc}")

    # Property-manager owner account.
    pm_opener, pm_jar, code, _, headers = login("landlord1", "bahamas242")
    checks["landlord1_login"] = code in (301, 302) and "/property-manager" in location(headers)
    pm_csrf = cookie_value(pm_jar, "ATLASBAHAMAS_CSRF")
    checks["landlord1_csrf"] = bool(pm_csrf)
    c, b, _ = request(pm_opener, "GET", "/property-manager")
    checks["landlord1_dashboard"] = c == 200 and "Property Manager Dashboard" in b
    c, b, _ = request(pm_opener, "GET", "/manager/maintenance")
    checks["landlord1_maintenance_page"] = c == 200 and "Maintenance" in b
    c, b, _ = request(pm_opener, "GET", "/manager/tenants")
    checks["landlord1_tenant_sync_page"] = c == 200 and "Tenant Sync" in b

    c, b, _ = request(pm_opener, "GET", "/manager/maintenance?status=open")
    m = re.search(r"name='request_id' value='(\d+)'", b)
    if m:
        rid = m.group(1)
        c, _, h = request(
            pm_opener,
            "POST",
            "/manager/maintenance/update",
            {"request_id": rid, "status": "in_progress", "assigned_to": "landlord1", "csrf_token": pm_csrf},
        )
        loc = location(h)
        checks["landlord1_maintenance_update"] = c in (301, 302) and loc.startswith("/manager/maintenance")
        if not checks["landlord1_maintenance_update"]:
            notes.append(f"landlord1 maintenance update location: {loc}")
    else:
        checks["landlord1_maintenance_update"] = False
        notes.append("No open maintenance request ID found on /manager/maintenance?status=open")

    # Secondary property-manager account.
    m2_opener, _, code, _, headers = login("Manager1", "bahamas242")
    checks["manager1_login"] = code in (301, 302) and "/property-manager" in location(headers)
    c, b, _ = request(m2_opener, "GET", "/property-manager")
    checks["manager1_dashboard"] = c == 200 and "Property Manager Dashboard" in b
    c, b, _ = request(m2_opener, "GET", "/manager/maintenance")
    checks["manager1_maintenance_page"] = c == 200 and "Maintenance" in b
    c, b, _ = request(m2_opener, "GET", "/manager/leases")
    checks["manager1_leases_page"] = c == 200 and "Assign Leases" in b

    # Admin role.
    a_opener, a_jar, code, _, headers = login("jayuice", "PleaseDontDropThePumpkinPie")
    checks["admin_login"] = code in (301, 302) and "/admin" in location(headers)
    a_csrf = cookie_value(a_jar, "ATLASBAHAMAS_CSRF")
    checks["admin_csrf"] = bool(a_csrf)
    c, b, _ = request(a_opener, "GET", "/admin")
    checks["admin_console"] = c == 200 and "Admin Console" in b
    c, b, _ = request(a_opener, "GET", "/admin/submissions")
    checks["admin_submissions"] = c == 200 and "Listing Submissions" in b
    c, b, _ = request(a_opener, "GET", "/notifications")
    checks["admin_modern_alerts_markup"] = c == 200 and "alerts-page" in b and "alerts-summary" in b
    c, _, h = request(a_opener, "POST", "/notifications/readall", {"csrf_token": a_csrf})
    checks["admin_readall_post"] = c in (301, 302) and location(h).startswith("/notifications")

    print("LIVE_ROLE_SMOKE_RESULTS", json.dumps(checks, sort_keys=True))
    if notes:
        print("LIVE_ROLE_SMOKE_NOTES", json.dumps(notes))

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())


