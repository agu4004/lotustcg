#!/usr/bin/env python3
"""
Manual migration script to add user contact and address fields to the users table.

This mirrors the Alembic migration `add_user_contact_fields` but can be run
directly when Alembic state is out of sync. It is idempotent and safe to run
multiple times.
"""

import os
import sqlite3
from typing import Iterable


COLS: tuple[tuple[str, str], ...] = (
    ("full_name", "VARCHAR(100)"),
    ("phone_number", "VARCHAR(20)"),
    ("address_line", "TEXT"),
    ("address_city", "VARCHAR(100)"),
    ("address_province", "VARCHAR(100)"),
    ("address_postal_code", "VARCHAR(20)"),
    ("address_country", "VARCHAR(100)"),
)


def _apply_to_db(db_path: str) -> bool:
    """Apply column additions to a specific SQLite DB file.

    Returns True if DB exists and was processed (columns added or already present).
    """
    if not os.path.exists(db_path):
        print(f"[INFO] Database not found at: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(users)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        added = []
        for name, ddl_type in COLS:
            if name not in existing_cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl_type}")
                added.append(name)

        if added:
            conn.commit()
            print(f"[SUCCESS] Added columns to users: {', '.join(added)} in {db_path}")
        else:
            print(f"[INFO] All contact fields already exist in {db_path}")

        return True
    except Exception as e:
        print(f"[ERROR] Failed applying user contact fields to {db_path}: {e}")
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


def apply_user_contact_fields(db_candidates: Iterable[str] | None = None) -> bool:
    """Apply migration to likely DB locations.

    If `db_candidates` is None, tries common paths under the project `instance/` dir.
    You can also override with env var `LOTUS_TCG_DB_PATH` to point to a specific DB.
    """
    base_dir = os.path.dirname(__file__)
    if db_candidates is None:
        db_candidates = (
            os.environ.get("LOTUS_TCG_DB_PATH"),
            os.path.join(base_dir, "instance", "your_database.db"),
            os.path.join(base_dir, "instance", "lotus_tcg_dev.db"),
        )

    any_processed = False
    for path in db_candidates:
        if not path:
            continue
        ok = _apply_to_db(path)
        any_processed = any_processed or ok

    return any_processed


if __name__ == "__main__":
    success = apply_user_contact_fields()
    if success:
        print("\nUser contact fields migration completed.")
        raise SystemExit(0)
    else:
        print("\nNo databases were updated. Provide LOTUS_TCG_DB_PATH or place DB under instance/.")
        raise SystemExit(1)

