#!/usr/bin/env python3
"""
Manual migration script to add email column to users table
"""

import sqlite3
import os

def add_email_column():
    """Add email column to users table"""
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'your_database.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if email column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'email' not in column_names:
            print("Adding email column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(120)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)")
            conn.commit()
            print("[SUCCESS] Email column added successfully!")
        else:
            print("[INFO] Email column already exists")

        conn.close()

    except Exception as e:
        print(f"[ERROR] Error adding email column: {e}")
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    add_email_column()