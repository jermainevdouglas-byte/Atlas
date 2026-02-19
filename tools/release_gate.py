#!/usr/bin/env python3
"""Release gate for staging promotion.

Runs required validations:
- smoke tests
- role-matrix tests
- backup + restore verification
- PostgreSQL migration connectivity verification
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def run(cmd: list[str], name: str, env=None) -> bool:
    print(f"[gate] {name}: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=BASE_DIR, env=env)
    print(f"[gate] {name}: {'PASS' if res.returncode == 0 else 'FAIL'}")
    return res.returncode == 0


def main() -> int:
    env = os.environ.copy()
    checks = [
        ("smoke", [sys.executable, "tests/smoke_test.py"]),
        ("role_matrix", [sys.executable, "tests/role_matrix_test.py"]),
        ("backup", [sys.executable, "tools/backup_restore.py", "backup"]),
        ("restore_test", [sys.executable, "tools/backup_restore.py", "restore-test", "--latest"]),
    ]
    if (env.get("POSTGRES_DSN") or "").strip():
        checks.append(("pg_verify", [sys.executable, "tools/migrate_sqlite_to_postgres.py", "--verify-only"]))
    else:
        print("[gate] pg_verify: SKIPPED (POSTGRES_DSN not set)")
    ok_all = True
    for name, cmd in checks:
        ok = run(cmd, name, env=env)
        ok_all = ok_all and ok

    if not ok_all:
        print("[gate] RELEASE_GATE=FAILED")
        return 1

    print("[gate] RELEASE_GATE=PASSED")
    promote_cmd = (env.get("PROMOTE_CMD") or "").strip()
    if promote_cmd:
        print(f"[gate] promoting via PROMOTE_CMD={promote_cmd}")
        res = subprocess.run(promote_cmd, cwd=BASE_DIR, shell=True)
        if res.returncode != 0:
            print("[gate] promote_failed")
            return res.returncode
        print("[gate] promote_succeeded")
    else:
        print("[gate] no PROMOTE_CMD configured; promotion step skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

