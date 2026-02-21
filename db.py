"""Database compatibility layer for AtlasBahamas (SQLite default, optional PostgreSQL)."""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency in sqlite-only runs
    psycopg = None

if psycopg is not None:
    DBOperationalError = (sqlite3.OperationalError, psycopg.OperationalError)
else:  # pragma: no cover
    DBOperationalError = (sqlite3.OperationalError,)


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


_PRAGMA_TABLE_INFO_SQL = (
    "SELECT "
    "(c.ordinal_position - 1)::int AS cid, "
    "c.column_name AS name, "
    "c.data_type AS type, "
    "CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, "
    "c.column_default AS dflt_value, "
    "CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS pk "
    "FROM information_schema.columns c "
    "LEFT JOIN ("
    "  SELECT kcu.column_name "
    "  FROM information_schema.table_constraints tc "
    "  JOIN information_schema.key_column_usage kcu "
    "    ON tc.constraint_name = kcu.constraint_name "
    "   AND tc.table_schema = kcu.table_schema "
    "   AND tc.table_name = kcu.table_name "
    "  WHERE tc.constraint_type = 'PRIMARY KEY' "
    "    AND tc.table_schema = current_schema() "
    "    AND tc.table_name = %s"
    ") pk ON pk.column_name = c.column_name "
    "WHERE c.table_schema = current_schema() AND c.table_name = %s "
    "ORDER BY c.ordinal_position"
)

_SQLITE_NOW_TEXT = "(to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00')"
_SQLITE_DATE_TEXT = "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD')"


def _normalize_modifier_token(token: str) -> str:
    t = str(token or "").strip()
    if t == "%s":
        return t
    if (t.startswith("'") and t.endswith("'")) or (t.startswith('"') and t.endswith('"')):
        return t[1:-1]
    return t


def _datetime_with_modifier_to_pg(token: str) -> str:
    mod = _normalize_modifier_token(token)
    if mod == "%s":
        interval_expr = "(%s)::interval"
    else:
        interval_expr = f"('{mod}')::interval"
    return (
        "(to_char((NOW() AT TIME ZONE 'UTC') + "
        + interval_expr +
        ", 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00')"
    )


def _date_with_modifier_to_pg(token: str) -> str:
    mod = _normalize_modifier_token(token)
    if mod == "%s":
        interval_expr = "(%s)::interval"
    else:
        interval_expr = f"('{mod}')::interval"
    return (
        "to_char((NOW() AT TIME ZONE 'UTC') + "
        + interval_expr +
        ", 'YYYY-MM-DD')"
    )


def _date_expr_to_pg(token: str) -> str:
    expr = str(token or "").strip()
    return "to_char(NULLIF((" + expr + ")::text, '')::date, 'YYYY-MM-DD')"


def _julianday_expr_to_pg(token: str) -> str:
    expr = str(token or "").strip()
    return (
        "(EXTRACT(EPOCH FROM (NULLIF(("
        + expr +
        ")::text, '')::timestamptz)) / 86400.0)"
    )


def _translate_sql(sql: str, params):
    text = str(sql or "")
    stripped = text.strip().rstrip(";")

    m = re.match(r"(?is)^PRAGMA\s+table_info\(([^)]+)\)$", stripped)
    if m:
        raw_name = m.group(1).strip().strip('"\'`[]')
        return _PRAGMA_TABLE_INFO_SQL, (raw_name, raw_name)

    if re.match(r"(?is)^PRAGMA\s+", stripped):
        return "SELECT 1", ()

    if re.match(r"(?is)^SELECT\s+last_insert_rowid\(\)\s*$", stripped):
        return "SELECT LASTVAL()", ()

    if re.search(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", text):
        text = re.sub(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", text, count=1)
        if "ON CONFLICT" not in text.upper():
            text = text.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    text = re.sub(
        r"(?i)\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        text,
    )
    text = re.sub(r"(?i)\bAUTOINCREMENT\b", "", text)
    text = re.sub(
        r"(?is)\bdatetime\(\s*['\"]now['\"]\s*,\s*([^)]+?)\s*\)",
        lambda m: _datetime_with_modifier_to_pg(m.group(1)),
        text,
    )
    text = re.sub(
        r"(?is)\bdate\(\s*['\"]now['\"]\s*,\s*([^)]+?)\s*\)",
        lambda m: _date_with_modifier_to_pg(m.group(1)),
        text,
    )
    text = re.sub(r"(?i)\bdatetime\(\s*'now'\s*\)", _SQLITE_NOW_TEXT, text)
    text = re.sub(r"(?i)\bdatetime\(\s*\"now\"\s*\)", _SQLITE_NOW_TEXT, text)
    text = re.sub(r"(?i)\bdate\(\s*'now'\s*\)", _SQLITE_DATE_TEXT, text)
    text = re.sub(r"(?i)\bdate\(\s*\"now\"\s*\)", _SQLITE_DATE_TEXT, text)
    text = re.sub(
        r"(?is)\bdate\(\s*([^)]+)\s*\)",
        lambda m: _date_expr_to_pg(m.group(1)),
        text,
    )
    text = re.sub(
        r"(?i)\bjulianday\(\s*'now'\s*\)",
        "(EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC')) / 86400.0)",
        text,
    )
    text = re.sub(
        r"(?i)\bjulianday\(\s*\"now\"\s*\)",
        "(EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC')) / 86400.0)",
        text,
    )
    text = re.sub(
        r"(?is)\bjulianday\(\s*([^)]+)\s*\)",
        lambda m: _julianday_expr_to_pg(m.group(1)),
        text,
    )
    text = _replace_qmark_placeholders(text)
    return text, tuple(params or ())


class CompatRow(dict):
    """dict-like row supporting both row['col'] and row[idx] access."""

    __slots__ = ("_keys",)

    def __init__(self, keys, values):
        keys2 = tuple(keys)
        super().__init__(zip(keys2, values))
        self._keys = keys2

    def __getitem__(self, key):
        if isinstance(key, int):
            key = self._keys[key]
        return super().__getitem__(key)

    def keys(self):
        return list(self._keys)


class PostgresCursorCompat:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def _columns(self):
        desc = self._cursor.description
        if not desc:
            return []
        cols = []
        for c in desc:
            cols.append(getattr(c, "name", c[0]))
        return cols

    def _wrap_row(self, row):
        if row is None:
            return None
        cols = self._columns()
        if isinstance(row, dict):
            values = [row.get(c) for c in cols]
        else:
            values = list(row)
        return CompatRow(cols, values)

    def fetchone(self):
        return self._wrap_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._wrap_row(r) for r in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        if size is None:
            rows = self._cursor.fetchmany()
        else:
            rows = self._cursor.fetchmany(size)
        return [self._wrap_row(r) for r in rows]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row

    def close(self):
        self._cursor.close()


class PostgresConnectionCompat:
    backend = "postgres"

    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self._conn = psycopg.connect(dsn)

    def execute(self, sql: str, params=()):
        sql2, params2 = _translate_sql(sql, params)
        cur = self._conn.execute(sql2, params2)
        return PostgresCursorCompat(cur)

    def executemany(self, sql: str, seq_of_params):
        sql2, _ = _translate_sql(sql, ())
        cur = self._conn.cursor()
        cur.executemany(sql2, seq_of_params)
        return PostgresCursorCompat(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return PostgresCursorCompat(self._conn.cursor())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


class SqliteConnectionCompat:
    backend = "sqlite"

    def __init__(self, path: str, timeout: int = 30):
        self._conn = sqlite3.connect(path, timeout=timeout)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params):
        return self._conn.executemany(sql, seq_of_params)

    def executescript(self, script: str):
        return self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def postgres_enabled(dsn: str | None = None) -> bool:
    use_dsn = (dsn if dsn is not None else os.getenv("POSTGRES_DSN", "")).strip()
    return bool(use_dsn)


def connect_db(path: str | None = None):
    dsn = (os.getenv("POSTGRES_DSN", "") or "").strip()
    if dsn:
        if psycopg is None:
            raise RuntimeError("POSTGRES_DSN is set but psycopg is not installed")
        return PostgresConnectionCompat(dsn)
    sqlite_path = path or os.getenv("DATABASE_PATH", "data/atlasbahamas.sqlite")
    return SqliteConnectionCompat(sqlite_path, timeout=30)


class PostgresDB:
    def __init__(self, dsn: str | None = None):
        self.dsn = (dsn if dsn is not None else os.getenv("POSTGRES_DSN", "")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    @contextmanager
    def connect(self):
        if not self.enabled:
            raise RuntimeError("PostgreSQL not configured. Set POSTGRES_DSN and install dependencies.")
        conn = PostgresConnectionCompat(self.dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class SqliteDB:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("DATABASE_PATH", "data/atlasbahamas.sqlite")

    @contextmanager
    def connect(self):
        conn = SqliteConnectionCompat(self.path, timeout=15)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_db_backend():
    pg = PostgresDB()
    if pg.enabled:
        return pg
    return SqliteDB()


