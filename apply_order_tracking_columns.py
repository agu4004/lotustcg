#!/usr/bin/env python3
"""
Manual migration helper to add tracking columns to orders table when Alembic isn't run.
Idempotent and safe to execute multiple times.
"""

import os
import sqlite3
from typing import Iterable


def _add_column_if_missing(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column in existing:
        return False
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


def _apply_to_db(db_path: str) -> bool:
    if not db_path or not os.path.exists(db_path):
        return False

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        changed = False
        changed |= _add_column_if_missing(cur, 'orders', 'tracking_number', 'VARCHAR(120)')
        changed |= _add_column_if_missing(cur, 'orders', 'tracking_carrier', 'VARCHAR(80)')
        changed |= _add_column_if_missing(cur, 'orders', 'tracking_url', 'VARCHAR(255)')
        changed |= _add_column_if_missing(cur, 'orders', 'tracking_notes', 'TEXT')
        changed |= _add_column_if_missing(cur, 'orders', 'shipped_at', 'DATETIME')
        if changed:
            conn.commit()
        else:
            conn.rollback()
        return changed
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def apply_order_tracking_columns(db_candidates: Iterable[str] | None = None) -> bool:
    base_dir = os.path.dirname(__file__)
    if db_candidates is None:
        db_candidates = (
            os.environ.get("LOTUS_TCG_DB_PATH"),
            os.path.join(base_dir, "instance", "your_database.db"),
            os.path.join(base_dir, "instance", "lotus_tcg_dev.db"),
        )

    any_ok = False
    for p in db_candidates:
        if not p:
            continue
        ok = _apply_to_db(p)
        any_ok = any_ok or ok
    return any_ok


if __name__ == '__main__':
    ok = apply_order_tracking_columns()
    raise SystemExit(0 if ok else 1)
