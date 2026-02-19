import argparse
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]


def load_server():
    mod_path = ROOT / "server.py"
    spec = importlib.util.spec_from_file_location("atlas_server", mod_path)
    if not spec or not spec.loader:
        raise SystemExit("cannot_load_server_module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def main():
    parser = argparse.ArgumentParser(description="Reset Atlas DB and re-run schema/bootstrap setup.")
    parser.add_argument("--yes", action="store_true", help="Skip safety prompt.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("refused_without_yes_flag")

    mod = load_server()
    db_path = Path(mod.DATABASE_PATH)
    upload_dir = Path(getattr(mod, "UPLOAD_DIR", ROOT / "data" / "uploads"))
    if db_path.exists():
        db_path.unlink()
    # Reset uploads for deterministic local testing.
    if upload_dir.exists() and upload_dir.is_dir():
        for p in upload_dir.rglob("*"):
            if p.is_file():
                try:
                    p.unlink()
                except Exception:
                    pass
    mod.ensure_db()
    print(f"seed_reset_complete={db_path}")


if __name__ == "__main__":
    main()

