#!/usr/bin/env python3
"""
Manual script to apply coupon system database changes
This bypasses the alembic migration system which seems to have corrupted state
"""

import sqlite3
import os
from datetime import datetime

def _apply_to_db(db_path: str) -> bool:
    """Apply coupon system database changes to a specific SQLite DB file"""
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print(f"Applying coupon system database changes to: {db_path}")

        # Create coupons table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                discount_percentage DECIMAL(5,2) NOT NULL,
                description VARCHAR(255),
                valid_from DATETIME,
                valid_until DATETIME,
                usage_limit INTEGER,
                usage_count INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create index on coupon code
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ix_coupons_code ON coupons(code)
        ''')

        # Add coupon fields to orders table
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'coupon_id' not in columns:
            cursor.execute('ALTER TABLE orders ADD COLUMN coupon_id INTEGER REFERENCES coupons(id)')

        if 'coupon_code' not in columns:
            cursor.execute('ALTER TABLE orders ADD COLUMN coupon_code VARCHAR(20)')

        if 'discount_amount' not in columns:
            cursor.execute('ALTER TABLE orders ADD COLUMN discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0')

        if 'discounted_total' not in columns:
            cursor.execute('ALTER TABLE orders ADD COLUMN discounted_total DECIMAL(10,2)')

        # Commit changes
        conn.commit()

        print("SUCCESS: Coupon system database changes applied successfully!")
        print("Changes made:")
        print("  - Created 'coupons' table")
        print("  - Added coupon fields to 'orders' table")
        print("  - Created indexes for performance")

        return True

    except Exception as e:
        print(f"ERROR: Error applying database changes: {e}")
        conn.rollback()
        return False

    finally:
        if 'conn' in locals():
            conn.close()


def apply_coupon_migration():
    """Apply coupon system database changes manually.

    Tries to detect common SQLite DB files used by this app and apply the
    schema changes to each (idempotent if already applied).
    """
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(base_dir, 'instance', 'your_database.db'),
        os.path.join(base_dir, 'instance', 'lotus_tcg_dev.db'),
    ]

    # Allow overriding via env var if provided
    override = os.environ.get('LOTUS_TCG_DB_PATH')
    if override:
        candidates = [override]

    any_ok = False
    for path in candidates:
        ok = _apply_to_db(path)
        any_ok = any_ok or ok

    return any_ok

if __name__ == "__main__":
    success = apply_coupon_migration()
    if success:
        print("\nDatabase migration completed successfully!")
        print("You can now proceed with implementing the coupon system routes and templates.")
    else:
        print("\nDatabase migration failed!")
        exit(1)
