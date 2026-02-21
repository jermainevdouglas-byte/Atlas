#!/usr/bin/env python3
"""SQLite -> PostgreSQL migration tool for AtlasBahamas."""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg
except Exception:  # pragma: no cover - optional in local sqlite-only runs
    psycopg = None

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "atlasbahamas.sqlite")))
DEFAULT_PG_DSN = os.getenv("POSTGRES_DSN", "")


@dataclass
class TableMeta:
    name: str
    create_sql: str
    columns: list[str]
    dependencies: set[str] = field(default_factory=set)
    row_count: int = 0
    autoincrement_columns: list[str] = field(default_factory=list)


@dataclass
class IndexMeta:
    name: str
    table: str
    create_sql: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate AtlasBahamas SQLite data to PostgreSQL")
    p.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="Path to source SQLite file")
    p.add_argument("--pg-dsn", default=DEFAULT_PG_DSN, help="Target PostgreSQL DSN")
    p.add_argument("--verify-only", action="store_true", help="Only verify SQLite + PostgreSQL connectivity")
    p.add_argument("--dry-run", action="store_true", help="Show migration plan only")
    p.add_argument("--migrate", action="store_true", help="Execute migration")
    p.add_argument("--schema-only", action="store_true", help="Create/refresh schema only")
    p.add_argument("--data-only", action="store_true", help="Copy rows only (schema must already exist)")
    p.add_argument("--truncate-first", action="store_true", help="Truncate target tables before row copy")
    p.add_argument("--drop-existing", action="store_true", help="Drop target tables before schema creation")
    p.add_argument("--batch-size", type=int, default=500, help="Batch size for inserts")
    p.add_argument(
        "--skip-count-verify",
        action="store_true",
        help="Skip SQLite/PostgreSQL row count verification after migration",
    )
    return p.parse_args()


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sqlite_quoted_table(name: str) -> str:
    return _quote_ident(name)


def _replace_qmark_placeholders(sql: str) -> str:
    out = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def sqlite_create_to_postgres(create_sql: str) -> str:
    sql = str(create_sql or "").strip().rstrip(";")
    sql = re.sub(
        r"(?i)\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        sql,
    )
    sql = re.sub(r"(?i)\bAUTOINCREMENT\b", "", sql)
    sql = re.sub(
        r"(?i)DEFAULT\s*\(\s*datetime\(\s*['\"]now['\"]\s*\)\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        sql,
    )
    sql = re.sub(
        r"(?i)DEFAULT\s*\(\s*date\(\s*['\"]now['\"]\s*\)\s*\)",
        "DEFAULT CURRENT_DATE",
        sql,
    )
    sql = re.sub(
        r"(?i)\bdatetime\(\s*['\"]now['\"]\s*\)",
        "CURRENT_TIMESTAMP",
        sql,
    )
    sql = re.sub(
        r"(?i)\bdate\(\s*['\"]now['\"]\s*\)",
        "CURRENT_DATE",
        sql,
    )
    sql = _replace_qmark_placeholders(sql)
    return sql + ";"


def sqlite_index_to_postgres(create_sql: str) -> str:
    sql = str(create_sql or "").strip().rstrip(";")
    if "IF NOT EXISTS" not in sql.upper():
        sql = re.sub(r"(?i)^CREATE\s+UNIQUE\s+INDEX\s+", "CREATE UNIQUE INDEX IF NOT EXISTS ", sql, count=1)
        sql = re.sub(r"(?i)^CREATE\s+INDEX\s+", "CREATE INDEX IF NOT EXISTS ", sql, count=1)
    return sql + ";"


def verify_postgres(pg_dsn: str) -> tuple[bool, str]:
    if not pg_dsn:
        return False, "POSTGRES_DSN is empty"
    if psycopg is None:
        return False, "psycopg is not installed"
    try:
        with psycopg.connect(pg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, "postgres_ok"
    except Exception as e:
        return False, f"postgres_connect_failed: {e}"


def inspect_sqlite(sqlite_path: Path) -> tuple[dict[str, TableMeta], list[IndexMeta]]:
    conn = sqlite3.connect(str(sqlite_path), timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        tables: dict[str, TableMeta] = {}
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        for row in rows:
            name = str(row["name"])
            create_sql = str(row["sql"] or "").strip()
            if not create_sql:
                continue
            pragma_tbl = _sqlite_quoted_table(name)
            col_rows = conn.execute(f"PRAGMA table_info({pragma_tbl})").fetchall()
            columns = [str(c["name"]) for c in col_rows]
            row_count = int(conn.execute(f"SELECT COUNT(1) FROM {pragma_tbl}").fetchone()[0])
            fk_rows = conn.execute(f"PRAGMA foreign_key_list({pragma_tbl})").fetchall()
            deps = {
                str(fk["table"])
                for fk in fk_rows
                if fk["table"] and str(fk["table"]) != name
            }
            auto_cols = []
            for col in columns:
                pat = rf"(?i)\b{re.escape(col)}\b\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b"
                if re.search(pat, create_sql):
                    auto_cols.append(col)
            tables[name] = TableMeta(
                name=name,
                create_sql=create_sql,
                columns=columns,
                dependencies=deps,
                row_count=row_count,
                autoincrement_columns=auto_cols,
            )

        indexes: list[IndexMeta] = []
        idx_rows = conn.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_autoindex%' "
            "ORDER BY name"
        ).fetchall()
        for row in idx_rows:
            indexes.append(
                IndexMeta(
                    name=str(row["name"]),
                    table=str(row["tbl_name"]),
                    create_sql=str(row["sql"]),
                )
            )
        return tables, indexes
    finally:
        conn.close()


def topo_sort_tables(tables: dict[str, TableMeta]) -> list[str]:
    deps_map = {name: set(meta.dependencies) & set(tables.keys()) for name, meta in tables.items()}
    order: list[str] = []
    while deps_map:
        ready = sorted(name for name, deps in deps_map.items() if not deps)
        if not ready:
            # Should not happen for AtlasBahamas schema, but keep deterministic behavior.
            ready = [sorted(deps_map.keys())[0]]
        for name in ready:
            order.append(name)
            deps_map.pop(name, None)
        for deps in deps_map.values():
            deps.difference_update(ready)
    return order


def create_postgres_schema(
    pg_conn,
    tables: dict[str, TableMeta],
    indexes: list[IndexMeta],
    table_order: list[str],
    drop_existing: bool = False,
    dry_run: bool = False,
) -> None:
    if dry_run:
        print(f"schema_tables={len(table_order)}")
        print(f"schema_indexes={len(indexes)}")
        return

    if drop_existing:
        for name in reversed(table_order):
            pg_conn.execute(f"DROP TABLE IF EXISTS {_quote_ident(name)} CASCADE")

    pending = list(table_order)
    retries = 0
    while pending:
        retries += 1
        progress = False
        remaining: list[str] = []
        for name in pending:
            try:
                pg_conn.execute(sqlite_create_to_postgres(tables[name].create_sql))
                progress = True
            except Exception as e:
                msg = str(e).lower()
                # Retry transient FK-order issues for a few passes.
                if "does not exist" in msg and ("relation" in msg or "table" in msg) and retries < 6:
                    remaining.append(name)
                    continue
                raise
        if not remaining:
            break
        if not progress:
            missing = ",".join(sorted(remaining))
            raise RuntimeError(f"Could not resolve table creation order: {missing}")
        pending = remaining

    for idx in indexes:
        if idx.table not in tables:
            continue
        pg_conn.execute(sqlite_index_to_postgres(idx.create_sql))


def _iter_sqlite_rows(conn, table: TableMeta, batch_size: int) -> Iterable[list[tuple[Any, ...]]]:
    batch_size = max(1, int(batch_size))
    cols = ", ".join(_quote_ident(c) for c in table.columns)
    q = f"SELECT {cols} FROM {_sqlite_quoted_table(table.name)}"
    cur = conn.execute(q)
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        out = []
        for row in rows:
            out.append(tuple(row[c] for c in table.columns))
        yield out


def truncate_postgres_tables(pg_conn, table_order: list[str]) -> None:
    for name in reversed(table_order):
        pg_conn.execute(f"TRUNCATE TABLE {_quote_ident(name)} RESTART IDENTITY CASCADE")


def copy_sqlite_to_postgres(
    sqlite_path: Path,
    pg_conn,
    tables: dict[str, TableMeta],
    table_order: list[str],
    batch_size: int,
    dry_run: bool = False,
) -> dict[str, int]:
    copied: dict[str, int] = {}
    if dry_run:
        for name in table_order:
            copied[name] = tables[name].row_count
        return copied

    sqlite_conn = sqlite3.connect(str(sqlite_path), timeout=30)
    try:
        sqlite_conn.row_factory = sqlite3.Row
        for name in table_order:
            meta = tables[name]
            if not meta.columns:
                copied[name] = 0
                continue
            col_csv = ", ".join(_quote_ident(c) for c in meta.columns)
            vals = ", ".join(["%s"] * len(meta.columns))
            insert_sql = (
                f"INSERT INTO {_quote_ident(meta.name)}({col_csv}) VALUES ({vals}) "
                "ON CONFLICT DO NOTHING"
            )
            inserted = 0
            with pg_conn.cursor() as cur:
                for batch in _iter_sqlite_rows(sqlite_conn, meta, batch_size):
                    cur.executemany(insert_sql, batch)
                    inserted += len(batch)
            copied[name] = inserted
    finally:
        sqlite_conn.close()
    return copied


def reset_sequences(pg_conn, tables: dict[str, TableMeta]) -> None:
    for meta in tables.values():
        for col in meta.autoincrement_columns:
            seq_row = pg_conn.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                (meta.name, col),
            ).fetchone()
            seq_name = seq_row[0] if seq_row else None
            if not seq_name:
                continue
            max_row = pg_conn.execute(
                f"SELECT COALESCE(MAX({_quote_ident(col)}), 0) FROM {_quote_ident(meta.name)}"
            ).fetchone()
            max_id = int(max_row[0] or 0)
            if max_id <= 0:
                pg_conn.execute("SELECT setval(%s, 1, false)", (seq_name,))
            else:
                pg_conn.execute("SELECT setval(%s, %s, true)", (seq_name, max_id))


def postgres_counts(pg_conn, table_order: list[str]) -> dict[str, int]:
    out = {}
    for name in table_order:
        out[name] = int(pg_conn.execute(f"SELECT COUNT(1) FROM {_quote_ident(name)}").fetchone()[0])
    return out


def run_migration(args: argparse.Namespace) -> int:
    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"sqlite_missing={sqlite_path}")
        return 2

    tables, indexes = inspect_sqlite(sqlite_path)
    if not tables:
        print("sqlite_tables=0")
        print("nothing_to_migrate=true")
        return 0
    table_order = topo_sort_tables(tables)
    sqlite_count_map = {name: tables[name].row_count for name in table_order}
    print("sqlite_counts", sqlite_count_map)
    print("table_order", table_order)

    if args.verify_only:
        ok, msg = verify_postgres(args.pg_dsn)
        print(msg)
        if not ok:
            return 2
        print("verify_only_passed=true")
        return 0

    if args.dry_run:
        print(f"dry_run_tables={len(table_order)}")
        print(f"dry_run_indexes={len(indexes)}")
        est_rows = sum(tables[name].row_count for name in table_order)
        print(f"dry_run_total_rows={est_rows}")
        return 0

    ok, msg = verify_postgres(args.pg_dsn)
    print(msg)
    if not ok:
        return 2

    if not (args.migrate or args.schema_only or args.data_only):
        print("No action selected. Use --verify-only, --dry-run, --migrate, --schema-only, or --data-only.")
        return 2
    if args.schema_only and args.data_only:
        print("Invalid flags: --schema-only and --data-only are mutually exclusive.")
        return 2

    with psycopg.connect(args.pg_dsn) as pg_conn:
        pg_conn.execute("SET statement_timeout = 0")
        do_schema = args.migrate or args.schema_only
        do_data = args.migrate or args.data_only

        if do_schema:
            create_postgres_schema(
                pg_conn=pg_conn,
                tables=tables,
                indexes=indexes,
                table_order=table_order,
                drop_existing=bool(args.drop_existing),
                dry_run=False,
            )
            print("schema_created=true")

        if do_data:
            if args.truncate_first:
                truncate_postgres_tables(pg_conn, table_order)
                print("target_truncated=true")
            copied = copy_sqlite_to_postgres(
                sqlite_path=sqlite_path,
                pg_conn=pg_conn,
                tables=tables,
                table_order=table_order,
                batch_size=max(1, int(args.batch_size)),
                dry_run=False,
            )
            print("copied_rows", copied)
            reset_sequences(pg_conn, tables)
            print("sequences_reset=true")

        if do_data and not args.skip_count_verify:
            pg_count_map = postgres_counts(pg_conn, table_order)
            print("postgres_counts", pg_count_map)
            mismatches = []
            for name in table_order:
                src = int(sqlite_count_map.get(name, 0))
                dst = int(pg_count_map.get(name, 0))
                if src != dst:
                    mismatches.append((name, src, dst))
            if mismatches:
                print("count_verify=failed")
                for name, src, dst in mismatches:
                    print(f"count_mismatch table={name} sqlite={src} postgres={dst}")
                return 3
            print("count_verify=ok")

    print("migration_completed=true")
    return 0


def main() -> int:
    args = parse_args()
    return run_migration(args)


if __name__ == "__main__":
    raise SystemExit(main())


