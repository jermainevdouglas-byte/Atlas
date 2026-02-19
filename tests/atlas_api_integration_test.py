import importlib
import os
import sys
import tempfile
from pathlib import Path


def assert_true(name, condition):
    if not condition:
        raise AssertionError(name)


def main():
    root_dir = Path(__file__).resolve().parents[1]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "atlasbahamas_test.sqlite")
        os.environ["ATLASBAHAMAS_DB_PATH"] = db_path
        os.environ["SECRET_KEY"] = "atlasbahamas-test-secret"
        os.environ["SEED_DEMO_USERS"] = "1"
        os.environ["COOKIE_SECURE"] = "0"
        os.environ["SESSION_COOKIE_SAMESITE"] = "Lax"

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

        r = client.post("/api/login", json={"identifier": "tenantdemo", "password": "wrong", "role": "tenant"})
        assert_true("login_bad_401", r.status_code == 401)

        r = client.post("/api/login", json={"identifier": "tenantdemo", "password": "AtlasTenant!2026", "role": "tenant"})
        j = r.get_json()
        assert_true("login_ok_200", r.status_code == 200)
        assert_true("login_ok_true", j.get("ok") is True)
        assert_true("login_role_tenant", j.get("session", {}).get("role") == "tenant")

        r = client.get("/api/dashboard/tenant")
        assert_true("tenant_dashboard_ok", r.status_code == 200)

        r = client.get("/api/dashboard/landlord")
        assert_true("tenant_forbidden_landlord_dashboard", r.status_code == 403)

        r = client.post("/api/contact", json={"name": "Test User", "email": "test@example.com", "message": "Hello"})
        assert_true("contact_ok", r.status_code == 200)

        r = client.post("/api/logout", json={})
        assert_true("logout_ok", r.status_code == 200)

        r = client.post(
            "/api/register",
            json={
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

        r = client.get("/api/dashboard/landlord")
        assert_true("landlord_dashboard_ok", r.status_code == 200)

    print("API_INTEGRATION_TEST_PASS")


if __name__ == "__main__":
    main()
