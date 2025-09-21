#!/usr/bin/env python3
"""
Manual migration helper to add linking columns to orders:
 - email (VARCHAR(120))
 - order_number (VARCHAR(30))
 - user_id (INTEGER, indexed)

It is safe to run multiple times. It also backfills order_number from id and
attempts to link user_id via email when possible.
"""

import os
import sqlite3


def _apply(path: str) -> bool:
    if not os.path.exists(path):
        print(f"[INFO] DB not found: {path}")
        return False
    con = sqlite3.connect(path)
    cur = con.cursor()
    try:
        print(f"[INFO] Updating: {path}")
        cur.execute("PRAGMA table_info(orders)")
        cols = {r[1] for r in cur.fetchall()}

        # Add email
        if 'email' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN email VARCHAR(120)")
            print("  + Added orders.email")

        # Add order_number
        cur.execute("PRAGMA table_info(orders)")
        cols = {r[1] for r in cur.fetchall()}
        if 'order_number' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN order_number VARCHAR(30)")
            print("  + Added orders.order_number")
        # Backfill order_number from id
        cur.execute("UPDATE orders SET order_number = id WHERE order_number IS NULL")

        # Add user_id
        cur.execute("PRAGMA table_info(orders)")
        cols = {r[1] for r in cur.fetchall()}
        if 'user_id' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER")
            print("  + Added orders.user_id")

        # Indexes (ignore errors if they exist)
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders(user_id)")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS ix_orders_order_number ON orders(order_number)")
        except Exception:
            pass

        # Attempt to backfill user_id where emails match (if users table exists)
        try:
            cur.execute("PRAGMA table_info(users)")
            ucols = {r[1] for r in cur.fetchall()}
            if 'email' in ucols and 'id' in ucols:
                cur.execute(
                    "UPDATE orders SET user_id = (SELECT id FROM users WHERE users.email = orders.email) "
                    "WHERE user_id IS NULL AND email IS NOT NULL"
                )
        except Exception:
            pass

        con.commit()
        print("[SUCCESS] Orders linking columns ensured and backfilled.")
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        try:
            con.rollback()
        except Exception:
            pass
        return False
    finally:
        con.close()


def main():
    base = os.path.dirname(__file__)
    candidates = [
        os.path.join(base, 'instance', 'your_database.db'),
        os.path.join(base, 'instance', 'lotus_tcg_dev.db'),
    ]
    override = os.environ.get('LOTUS_TCG_DB_PATH')
    if override:
        candidates = [override]
    any_ok = False
    for p in candidates:
        if _apply(p):
            any_ok = True
    if not any_ok:
        print("[INFO] No databases updated.")


if __name__ == '__main__':
    main()

