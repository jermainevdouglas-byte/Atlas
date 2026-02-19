import importlib
import os
import sys
import tempfile
from pathlib import Path


def assert_true(name, condition):
    if not condition:
        raise AssertionError(name)


def post_json(client, path, payload=None, csrf_token=None):
    body = dict(payload or {})
    if csrf_token:
        body["csrfToken"] = csrf_token
    return client.post(path, json=body)


def main():
    root_dir = Path(__file__).resolve().parents[1]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "atlasbahamas_test.sqlite")
        os.environ["ATLASBAHAMAS_DB_PATH"] = db_path
        os.environ["SECRET_KEY"] = "atlasbahamas-test-secret-value-1234567890"
        os.environ["SEED_DEMO_USERS"] = "1"
        os.environ["COOKIE_SECURE"] = "0"
        os.environ["SESSION_COOKIE_SAMESITE"] = "Lax"
        os.environ["PROD_MODE"] = "0"
        os.environ["ENFORCE_HTTPS"] = "0"

        import app as app_module

        app_module = importlib.reload(app_module)
        flask_app = app_module.create_app()
        client = flask_app.test_client()

        r = client.get("/health")
        assert_true("health_200", r.status_code == 200)
        assert_true("health_ok", r.get_json().get("ok") is True)

        r = client.get("/AtlasBahamasHome.html")
        assert_true("home_page_served", r.status_code == 200)

        r = client.get("/assets/images/AtlasBahamasDoorHomeCropped.png")
        assert_true("door_asset_served", r.status_code == 200)

        r = client.get("/api/session")
        j = r.get_json()
        assert_true("session_guest", j.get("authenticated") is False)
        assert_true("guest_csrf_present", len(str(j.get("csrfToken") or "")) > 10)

        r = post_json(client, "/api/login", {"identifier": "tenantdemo", "password": "wrong", "role": "tenant"})
        assert_true("login_bad_401", r.status_code == 401)

        r = post_json(client, "/api/login", {"identifier": "tenantdemo", "password": "AtlasTenant!2026", "role": "tenant"})
        j = r.get_json()
        assert_true("login_ok_200", r.status_code == 200)
        assert_true("login_ok_true", j.get("ok") is True)
        assert_true("login_role_tenant", j.get("session", {}).get("role") == "tenant")
        tenant_csrf = str(j.get("csrfToken") or "")
        assert_true("tenant_csrf_present", len(tenant_csrf) > 10)

        r = client.get("/api/dashboard/tenant")
        assert_true("tenant_dashboard_ok", r.status_code == 200)

        r = client.get("/api/dashboard/landlord")
        assert_true("tenant_forbidden_landlord_dashboard", r.status_code == 403)

        r = post_json(
            client,
            "/api/workflow/payment",
            {"amount": 1250, "paymentMonth": "2026-02", "note": "Bank transfer reference 447"},
            csrf_token=tenant_csrf,
        )
        assert_true("tenant_payment_submit_ok", r.status_code == 200)
        assert_true("tenant_payment_submitted_status", r.get_json().get("payment", {}).get("status") == "submitted")

        r = post_json(
            client,
            "/api/workflow/maintenance",
            {"subject": "Air conditioner issue", "details": "The AC in bedroom 2 is not cooling.", "severity": "high"},
            csrf_token=tenant_csrf,
        )
        assert_true("tenant_maintenance_submit_ok", r.status_code == 200)
        assert_true("tenant_maintenance_open_status", r.get_json().get("request", {}).get("status") == "open")

        r = client.get("/api/workflow/payments")
        payments = r.get_json().get("payments", [])
        assert_true("tenant_workflow_payments_visible", r.status_code == 200 and len(payments) >= 1)

        r = client.get("/api/workflow/maintenance")
        requests = r.get_json().get("requests", [])
        assert_true("tenant_workflow_maintenance_visible", r.status_code == 200 and len(requests) >= 1)

        r = post_json(
            client,
            "/api/contact",
            {"name": "Test User", "email": "test@example.com", "message": "Hello"},
            csrf_token=tenant_csrf,
        )
        assert_true("contact_ok", r.status_code == 200)

        r = post_json(client, "/api/logout", {}, csrf_token=tenant_csrf)
        assert_true("logout_ok", r.status_code == 200)
        assert_true("logout_returns_new_csrf", len(str(r.get_json().get("csrfToken") or "")) > 10)

        r = post_json(
            client,
            "/api/register",
            {
                "fullName": "Casey Landlord",
                "email": "casey.landlord@example.com",
                "username": "caseyl",
                "role": "landlord",
                "password": "CaseyLandlord!2026",
                "passwordConfirm": "CaseyLandlord!2026",
            },
        )
        assert_true("register_ok", r.status_code == 200)
        assert_true("register_role_landlord", r.get_json().get("session", {}).get("role") == "landlord")
        landlord_csrf = str(r.get_json().get("csrfToken") or "")
        assert_true("landlord_csrf_present", len(landlord_csrf) > 10)

        r = client.get("/api/dashboard/landlord")
        assert_true("landlord_dashboard_ok", r.status_code == 200)
        dashboard_data = r.get_json()
        pending = dashboard_data.get("pendingPayments", [])
        queue = dashboard_data.get("maintenanceQueue", [])
        assert_true("landlord_dashboard_pending_present", len(pending) >= 1)
        assert_true("landlord_dashboard_maintenance_present", len(queue) >= 1)

        pending_payment_id = int(pending[0]["id"])
        maintenance_id = int(queue[0]["id"])

        r = post_json(
            client,
            f"/api/workflow/payment/{pending_payment_id}/status",
            {"status": "received", "note": "Confirmed in landlord review."},
            csrf_token=landlord_csrf,
        )
        assert_true("landlord_payment_review_ok", r.status_code == 200)
        assert_true("landlord_payment_review_status", r.get_json().get("payment", {}).get("status") == "received")

        r = post_json(
            client,
            f"/api/workflow/maintenance/{maintenance_id}/status",
            {"status": "in_progress"},
            csrf_token=landlord_csrf,
        )
        assert_true("landlord_maintenance_review_ok", r.status_code == 200)
        assert_true("landlord_maintenance_review_status", r.get_json().get("request", {}).get("status") == "in_progress")

    print("API_INTEGRATION_TEST_PASS")


if __name__ == "__main__":
    main()
