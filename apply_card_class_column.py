#!/usr/bin/env python3
"""
Manual migration helper to add cards.card_class column for SQLite when Alembic isn't run.
Idempotent and safe to run multiple times.
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
        added = _add_column_if_missing(
            cur,
            'cards',
            'card_class',
            "VARCHAR(50) DEFAULT 'General'",
        )
        # Backfill NULLs regardless of whether the column was just added
        cur.execute("UPDATE cards SET card_class = 'General' WHERE card_class IS NULL")
        conn.commit()
        return added
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


def apply_card_class_column(db_candidates: Iterable[str] | None = None) -> bool:
    base_dir = os.path.dirname(__file__)
    if db_candidates is None:
        db_candidates = (
            os.environ.get("LOTUS_TCG_DB_PATH"),
            os.path.join(base_dir, "instance", "your_database.db"),
            os.path.join(base_dir, "instance", "lotus_tcg_dev.db"),
        )
    any_ok = False
    for path in db_candidates:
        if not path:
            continue
        ok = _apply_to_db(path)
        any_ok = any_ok or ok
    return any_ok


if __name__ == "__main__":
    success = apply_card_class_column()
    raise SystemExit(0 if success else 1)
