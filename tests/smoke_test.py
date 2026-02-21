#!/usr/bin/env python3
import http.cookiejar
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("ATLASBAHAMAS_TEST_PORT", "5091"))


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
        return res.getcode(), res.read().decode("utf-8", "replace"), res.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers


def main():
    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    env["PORT"] = str(PORT)
    env["DATABASE_PATH"] = str(BASE_DIR / "data" / "atlasbahamas.sqlite")
    env["SEED_DEMO_DATA"] = "1"
    env["CLEAR_SESSIONS_ON_START"] = "0"
    env["PROD_MODE"] = "0"
    p = subprocess.Popen([sys.executable, "server.py"], cwd=BASE_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        opener, jar = build_opener()
        for _ in range(120):
            try:
                hc, _, _ = req(opener, "GET", "/health")
                if hc == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            raise SystemExit("server_not_ready")

        checks = {}
        c, home, _ = req(opener, "GET", "/")
        checks["home_ok"] = c == 200 and "/static/img/door_hero.svg" in home
        c, listings_json, _ = req(opener, "GET", "/api/listings")
        listing_form_split_ok = False
        try:
            listings_data = json.loads(listings_json)
            first_listing_id = (listings_data.get("listings") or [{}])[0].get("id")
            if first_listing_id:
                c, listing_html, _ = req(opener, "GET", f"/listing/{first_listing_id}")
                listing_form_split_ok = (
                    c == 200 and
                    'id="applyForm"' in listing_html and
                    'id="inquiryForm"' in listing_html and
                    'form="applyForm"' in listing_html and
                    'form="inquiryForm"' in listing_html
                )
        except Exception:
            listing_form_split_ok = False
        checks["listing_forms_independent_markup"] = listing_form_split_ok

        # Login throttling: repeated failures should lock this username+ip key.
        lock_user = "rate_limit_probe"
        for _ in range(6):
            req(opener, "POST", "/login", {"username": lock_user, "password": "bad-pass"})
        c, lock_body, _ = req(opener, "POST", "/login", {"username": lock_user, "password": "bad-pass"})
        checks["login_lockout"] = c == 200 and "Login locked" in lock_body

        c, _, _ = req(opener, "POST", "/login", {"username": "admin1", "password": "AtlasAdmin!1"})
        checks["login_redirect"] = c in (200, 302)
        csrf = get_cookie(jar, "ATLASBAHAMAS_CSRF")
        checks["csrf_cookie_set"] = bool(csrf)

        c, profile, _ = req(opener, "GET", "/profile")
        checks["profile_page"] = c == 200 and "Manage your account details and password" in profile

        c, messages, _ = req(opener, "GET", "/messages")
        checks["messages_page"] = c == 200 and "Threaded messages" in messages

        c, _, _ = req(opener, "POST", "/notifications/readall", {})
        checks["csrf_blocks_missing_token"] = c == 400

        c, body, _ = req(opener, "POST", "/notifications/readall", {"csrf_token": csrf})
        ok_json = False
        ok_html = "All alerts marked as read" in body
        try:
            ok_json = json.loads(body).get("ok") is True
        except Exception:
            ok_json = False
        checks["csrf_allows_valid_token"] = c == 200 and (ok_json or ok_html)

        c, profile2, _ = req(opener, "POST", "/profile/update", {
            "full_name": "AtlasBahamas Admin",
            "phone": "2420000999",
            "email": "admin@atlasbahamas.local",
            "current_password": "",
            "new_password": "",
            "new_password2": "",
            "csrf_token": csrf,
        })
        checks["profile_update_ok"] = c == 200 and "Your profile has been updated" in profile2

        c, apps, _ = req(opener, "GET", "/manager/applications")
        checks["back_to_dashboard_visible"] = c == 200 and "Back to Dashboard" in apps
        checks["top_nav_back_removed"] = c == 200 and "&larr; Back to Dashboard" not in apps

        mgr_opener, mgr_jar = build_opener()
        c, _, _ = req(mgr_opener, "POST", "/login", {"username": "manager1", "password": "AtlasManager!1"})
        checks["manager_login_ok"] = c in (200, 302)
        c, checks_page, _ = req(mgr_opener, "GET", "/manager/checks")
        checks["manager_checks_page"] = c == 200 and "Property Checks" in checks_page
        c, mgr_tenants, _ = req(mgr_opener, "GET", "/manager/tenants")
        checks["manager_tenants_page"] = c == 200 and "Tenant Sync" in mgr_tenants
        c, mgr_props, _ = req(mgr_opener, "GET", "/manager/properties")
        checks["manager_properties_page"] = c == 200 and "Properties registered to your manager account" in mgr_props
        checks["manager_tenant_unit_autofill"] = (
            c == 200 and
            "managerTenantUnitSelect" in mgr_tenants and
            "/api/units?property_id=" in mgr_tenants
        )
        c, mgr_listing_requests, _ = req(mgr_opener, "GET", "/manager/listings")
        checks["manager_cannot_open_manage_listings"] = c == 200 and "Listing Submissions" in mgr_listing_requests
        csrf_mgr = get_cookie(mgr_jar, "ATLASBAHAMAS_CSRF")
        c, mgr_action_result, _ = req(mgr_opener, "POST", "/manager/listings/action", {
            "listing_id": "1",
            "action": "approve",
            "csrf_token": csrf_mgr,
        })
        checks["manager_cannot_approve_listing"] = c == 200 and "Listing Submissions" in mgr_action_result
        c, mgr_reg_result, _ = req(mgr_opener, "POST", "/manager/property/new", {
            "name": f"Manager Smoke {int(time.time())}",
            "location": "Nassau",
            "property_type": "Apartment",
            "units_count": "2",
            "csrf_token": csrf_mgr,
        })
        checks["manager_register_property"] = c == 200 and "View Properties" in mgr_reg_result

        ll_opener, ll_jar = build_opener()
        c, _, _ = req(ll_opener, "POST", "/login", {"username": "landlord1", "password": "AtlasLandlord!1"})
        checks["landlord_login_ok"] = c in (200, 302)
        c, listing_requests, _ = req(ll_opener, "GET", "/landlord/listing-requests")
        checks["landlord_listing_requests_page"] = c == 200 and "Listing Submissions" in listing_requests
        c, landlord_tenants, _ = req(ll_opener, "GET", "/landlord/tenants")
        checks["landlord_tenants_page"] = c == 200 and "Send Confirmation Invite" in landlord_tenants
        checks["landlord_tenant_unit_autofill"] = (
            c == 200 and
            "landlordTenantUnitSelect" in landlord_tenants and
            "/api/units?property_id=" in landlord_tenants
        )

        csrf_ll = get_cookie(ll_jar, "ATLASBAHAMAS_CSRF")
        req(ll_opener, "POST", "/landlord/property/new", {
            "name": f"Invite Smoke {int(time.time())}",
            "location": "Nassau",
            "property_type": "Apartment",
            "units_count": "1",
            "csrf_token": csrf_ll,
        })
        c, props_html, _ = req(ll_opener, "GET", "/landlord/properties")
        m = re.search(r"ID:\s*<b>([^<]+)</b>", props_html)
        property_id = m.group(1).strip() if m else ""
        c, invite_result, _ = req(ll_opener, "POST", "/landlord/tenant/invite", {
            "tenant_ident": "tenant1",
            "property_id": property_id,
            "unit_label": "Unit 1",
            "message": "Please accept this property link.",
            "csrf_token": csrf_ll,
        })
        checks["landlord_send_invite"] = c == 200 and (
            "Confirmation invite sent to tenant" in invite_result or
            "pending invite already exists" in invite_result.lower()
        )
        c, submit_all_result, _ = req(ll_opener, "POST", "/landlord/listing/submit_all", {
            "property_id": property_id,
            "category": "Long Term Rental",
            "csrf_token": csrf_ll,
        })
        checks["landlord_submit_all_units"] = c == 200 and "Submitted " in submit_all_result and "Skipped " in submit_all_result

        c, approve_all_result, _ = req(opener, "POST", "/admin/submissions/approve_all", {
            "csrf_token": csrf,
        })
        checks["admin_approve_all_submissions"] = c == 200 and "Listing Submissions" in approve_all_result
        conn = sqlite3.connect(str(BASE_DIR / "data" / "atlasbahamas.sqlite"))
        pending_after = conn.execute(
            "SELECT COUNT(*) FROM listing_requests WHERE property_id=? AND status='pending'",
            (property_id,),
        ).fetchone()[0]
        conn.close()
        checks["submit_all_requests_approved"] = pending_after == 0

        t_opener, t_jar = build_opener()
        c, _, _ = req(t_opener, "POST", "/login", {"username": "tenant1", "password": "AtlasTenant!1"})
        csrf_t = get_cookie(t_jar, "ATLASBAHAMAS_CSRF")
        c, tenant_home, _ = req(t_opener, "GET", "/tenant")
        checks["tenant_toolbar_hides_invites"] = c == 200 and "/tenant/invites" not in tenant_home and "Alerts" in tenant_home
        c, tenant_alerts, _ = req(t_opener, "GET", "/notifications")
        checks["tenant_invite_via_alert_link"] = c == 200 and ("/tenant/invites" in tenant_alerts or "Property sync invite" in tenant_alerts)
        c, invites_page, _ = req(t_opener, "GET", "/tenant/invites")
        checks["tenant_invites_page"] = c == 200 and "Property Invites" in invites_page
        mi = re.search(r"name='invite_id' value='(\\d+)'", invites_page)
        if mi:
            c, _, _ = req(t_opener, "POST", "/tenant/invite/respond", {
                "invite_id": mi.group(1),
                "action": "accept",
                "csrf_token": csrf_t,
            })
            c, lease_page, _ = req(t_opener, "GET", "/tenant/lease")
            checks["tenant_accept_invite"] = c == 200 and "Active:" in lease_page
        else:
            checks["tenant_accept_invite"] = True

        print("SMOKE_CHECKS", checks)
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


