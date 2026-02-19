import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "atlas.sqlite"
DEFAULT_BACKUP_DIR = ROOT / "data" / "backups"


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_db(db_path: Path, backup_dir: Path):
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"atlas_{timestamp()}.sqlite"
    shutil.copy2(db_path, out)
    print(f"backup_created={out}")


def restore_db(db_path: Path, backup_file: Path):
    if not backup_file.exists():
        raise SystemExit(f"backup_not_found={backup_file}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, db_path)
    print(f"db_restored_from={backup_file}")


def integrity_check(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()
    quick_ok = bool(quick and str(quick[0]).lower() == "ok")
    print(f"quick_check={'ok' if quick_ok else quick[0] if quick else 'unknown'}")
    print(f"foreign_key_violations={len(fk)}")
    if not quick_ok or fk:
        raise SystemExit(1)


def run_migrations():
    mod_path = ROOT / "server.py"
    spec = importlib.util.spec_from_file_location("atlas_server", mod_path)
    if not spec or not spec.loader:
        raise SystemExit("cannot_load_server_module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    mod.ensure_db()
    print("migrations_applied=ok")


def main():
    parser = argparse.ArgumentParser(description="Atlas DB backup/restore/integrity/migrate tooling.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="Create timestamped DB backup.")
    p_backup.add_argument("--db", default=str(DEFAULT_DB))
    p_backup.add_argument("--out", default=str(DEFAULT_BACKUP_DIR))

    p_restore = sub.add_parser("restore", help="Restore DB from backup file.")
    p_restore.add_argument("--db", default=str(DEFAULT_DB))
    p_restore.add_argument("--file", required=True)

    p_check = sub.add_parser("integrity", help="Run quick_check + foreign_key_check.")
    p_check.add_argument("--db", default=str(DEFAULT_DB))

    sub.add_parser("migrate", help="Run ensure_db() migrations.")

    args = parser.parse_args()
    cmd = args.cmd
    if cmd == "backup":
        backup_db(Path(args.db), Path(args.out))
    elif cmd == "restore":
        restore_db(Path(args.db), Path(args.file))
    elif cmd == "integrity":
        integrity_check(Path(args.db))
    elif cmd == "migrate":
        run_migrations()


if __name__ == "__main__":
    main()


