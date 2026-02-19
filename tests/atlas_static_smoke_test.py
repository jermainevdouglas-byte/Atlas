import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    "AtlasBahamasHome.html",
    "AtlasBahamasAbout.html",
    "AtlasBahamasContact.html",
    "AtlasBahamasListings.html",
    "AtlasBahamasLogin.html",
    "AtlasBahamasRegister.html",
    "AtlasBahamasTenantDashboard.html",
    "AtlasBahamasLandlordDashboard.html",
]

REQUIRED_ASSETS = [
    "AtlasBahamasVisualIdentity.css",
    "AtlasBahamasAuth.js",
    "AtlasBahamasShell.js",
    "assets/images/AtlasBahamasDoorHomeCropped.png",
]

errors = []

for rel in REQUIRED_ASSETS:
    path = ROOT / rel
    if not path.exists():
        errors.append(f"missing_required_asset:{rel}")

for page in PAGES:
    path = ROOT / page
    if not path.exists():
        errors.append(f"missing_page:{page}")
        continue

    html = path.read_text(encoding="utf-8")

    if "data-atlas-header" not in html:
        errors.append(f"missing_shared_header_mount:{page}")

    if "AtlasBahamasAuth.js" not in html or "AtlasBahamasShell.js" not in html:
        errors.append(f"missing_core_scripts:{page}")

    links = re.findall(r'href="([^"]+)"', html)
    for href in links:
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = href.split("?", 1)[0]
        if not target or target == "/":
            continue
        file_target = (ROOT / target).resolve()
        if not file_target.exists():
            errors.append(f"broken_link:{page}->{href}")

home = (ROOT / "AtlasBahamasHome.html").read_text(encoding="utf-8") if (ROOT / "AtlasBahamasHome.html").exists() else ""
if home.count("data-role-door") < 2:
    errors.append("home_missing_dual_role_doors")
if "?role=tenant" not in home or "?role=landlord" not in home:
    errors.append("home_missing_role_routes")

if errors:
    print("STATIC_SMOKE_FAIL")
    for err in errors:
        print(err)
    sys.exit(1)

print("STATIC_SMOKE_PASS")
