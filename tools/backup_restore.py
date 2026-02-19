#!/usr/bin/env python3
"""SQLite backup + restore verification tooling for Atlas.

Usage examples:
  py -3 tools/backup_restore.py backup
  py -3 tools/backup_restore.py list
  py -3 tools/backup_restore.py restore-test --latest
  py -3 tools/backup_restore.py restore --file data/backups/atlas_YYYYMMDD_HHMMSS.sqlite
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "atlas.sqlite")))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(BASE_DIR / "data" / "backups")))
RETENTION_COUNT = max(3, int(os.getenv("BACKUP_RETENTION_COUNT", "14")))
RETENTION_DAYS = max(1, int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
USE_GZIP = (os.getenv("BACKUP_GZIP", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _integrity_check(db_path: Path) -> tuple[bool, str]:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        msg = (row[0] if row else "")
        return msg.lower() == "ok", msg
    finally:
        conn.close()


def _required_tables_ok(db_path: Path) -> tuple[bool, list[str]]:
    required = {
        "users", "sessions", "properties", "units", "tenant_leases", "payments",
        "listings", "listing_requests", "maintenance_requests", "notifications", "audit_logs",
    }
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        got = {r[0] for r in rows}
    finally:
        conn.close()
    missing = sorted(required - got)
    return len(missing) == 0, missing


def _backup_filename() -> str:
    base = f"atlas_{_now_stamp()}.sqlite"
    return base + (".gz" if USE_GZIP else "")


def create_backup(src: Path, backup_dir: Path) -> Path:
    if not src.exists():
        raise FileNotFoundError(f"Database not found: {src}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / _backup_filename()
    tmp_raw = backup_dir / f"atlas_{_now_stamp()}_tmp.sqlite"

    src_conn = sqlite3.connect(str(src), timeout=30)
    try:
        dst_conn = sqlite3.connect(str(tmp_raw), timeout=30)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    ok, msg = _integrity_check(tmp_raw)
    if not ok:
        tmp_raw.unlink(missing_ok=True)
        raise RuntimeError(f"Backup integrity failed: {msg}")

    if USE_GZIP:
        with open(tmp_raw, "rb") as rf, gzip.open(out, "wb") as wf:
            shutil.copyfileobj(rf, wf)
        tmp_raw.unlink(missing_ok=True)
    else:
        tmp_raw.replace(out)

    prune_backups(backup_dir)
    return out


def _iter_backups(backup_dir: Path):
    if not backup_dir.exists():
        return []
    files = [p for p in backup_dir.glob("atlas_*.sqlite*") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def prune_backups(backup_dir: Path) -> None:
    files = _iter_backups(backup_dir)
    now = datetime.now(timezone.utc).timestamp()
    for i, f in enumerate(files):
        age_days = (now - f.stat().st_mtime) / 86400.0
        if i >= RETENTION_COUNT or age_days > RETENTION_DAYS:
            f.unlink(missing_ok=True)


def list_backups(backup_dir: Path) -> list[Path]:
    return _iter_backups(backup_dir)


def _extract_backup_to_temp(backup_file: Path) -> Path:
    td = Path(tempfile.mkdtemp(prefix="atlas_restore_test_"))
    out = td / "restore_test.sqlite"
    if backup_file.suffix == ".gz":
        with gzip.open(backup_file, "rb") as rf, open(out, "wb") as wf:
            shutil.copyfileobj(rf, wf)
    else:
        shutil.copy2(backup_file, out)
    return out


def restore_test(backup_file: Path) -> tuple[bool, str]:
    if not backup_file.exists():
        return False, f"Backup file not found: {backup_file}"
    extracted = _extract_backup_to_temp(backup_file)
    ok, msg = _integrity_check(extracted)
    if not ok:
        return False, f"Integrity check failed: {msg}"
    tables_ok, missing = _required_tables_ok(extracted)
    if not tables_ok:
        return False, f"Missing required tables: {', '.join(missing)}"
    return True, f"Restore test passed for {backup_file.name}"


def restore(backup_file: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    extracted = _extract_backup_to_temp(backup_file)
    ok, msg = _integrity_check(extracted)
    if not ok:
        raise RuntimeError(f"Backup integrity failed: {msg}")
    shutil.copy2(extracted, target_db)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Atlas backup/restore tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backup", help="Create backup")
    b.add_argument("--db", default=str(DEFAULT_DB))
    b.add_argument("--backup-dir", default=str(BACKUP_DIR))

    l = sub.add_parser("list", help="List backups")
    l.add_argument("--backup-dir", default=str(BACKUP_DIR))

    rt = sub.add_parser("restore-test", help="Verify backup can be restored")
    rt.add_argument("--backup-dir", default=str(BACKUP_DIR))
    rt.add_argument("--file", default="")
    rt.add_argument("--latest", action="store_true")

    r = sub.add_parser("restore", help="Restore backup into target db")
    r.add_argument("--file", required=True)
    r.add_argument("--target-db", default=str(DEFAULT_DB))

    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.cmd == "backup":
        out = create_backup(Path(args.db), Path(args.backup_dir))
        print(f"backup_created={out}")
        return 0
    if args.cmd == "list":
        for p in list_backups(Path(args.backup_dir)):
            print(p)
        return 0
    if args.cmd == "restore-test":
        backup_file = Path(args.file) if args.file else None
        if args.latest and not backup_file:
            files = list_backups(Path(args.backup_dir))
            if not files:
                print("no_backups_found")
                return 2
            backup_file = files[0]
        if not backup_file:
            print("--file or --latest is required")
            return 2
        ok, msg = restore_test(backup_file)
        print(msg)
        return 0 if ok else 1
    if args.cmd == "restore":
        restore(Path(args.file), Path(args.target_db))
        print(f"restored_to={args.target_db}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

