#!/usr/bin/env python3
"""
Manual migration script to add owner columns to cards and shop_inventory_items tables.

This mirrors the Alembic migration `add_owner_columns` but can be run
directly when Alembic state is out of sync. It is idempotent and safe to run
multiple times, intended primarily for SQLite.
"""

import os
import sqlite3
from typing import Iterable


def _add_column_if_missing(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cur.fetchall()}
    if column not in existing_cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        return True
    return False


def _apply_to_db(db_path: str) -> bool:
    """Apply column additions to a specific SQLite DB file.

    Returns True if DB exists and was processed (columns added or already present).
    """
    if not db_path or not os.path.exists(db_path):
        print(f"[INFO] Database not found at: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        any_change = False

        # cards.owner VARCHAR(80) DEFAULT 'shop'
        try:
            changed = _add_column_if_missing(cur, 'cards', 'owner', "VARCHAR(80)")
            any_change = any_change or changed
            # Backfill to 'shop' where NULL
            cur.execute("UPDATE cards SET owner = 'shop' WHERE owner IS NULL")
        except Exception as e:
            print(f"[WARN] Could not modify 'cards' table: {e}")

        # shop_inventory_items.owner VARCHAR(80)
        try:
            changed = _add_column_if_missing(cur, 'shop_inventory_items', 'owner', "VARCHAR(80)")
            any_change = any_change or changed
            # Backfill from users.username where possible
            try:
                cur.execute(
                    """
                    UPDATE shop_inventory_items AS s
                    SET owner = (
                        SELECT u.username FROM users u WHERE u.id = s.from_user_id
                    )
                    WHERE owner IS NULL
                    """
                )
            except Exception as e:
                print(f"[WARN] Could not backfill shop_inventory_items.owner: {e}")
        except Exception as e:
            print(f"[WARN] Could not modify 'shop_inventory_items' table: {e}")

        conn.commit()
        if any_change:
            print(f"[SUCCESS] Owner columns ensured in {db_path}")
        else:
            print(f"[INFO] Owner columns already present in {db_path}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed applying owner columns to {db_path}: {e}")
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


def apply_owner_columns(db_candidates: Iterable[str] | None = None) -> bool:
    """Apply migration to likely DB locations.

    If `db_candidates` is None, tries common paths under the project `instance/` dir,
    or LOTUS_TCG_DB_PATH env var.
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
    success = apply_owner_columns()
    if success:
        print("\nOwner columns migration completed.")
        raise SystemExit(0)
    else:
        print("\nNo databases were updated. Provide LOTUS_TCG_DB_PATH or place DB under instance/.")
        raise SystemExit(1)

