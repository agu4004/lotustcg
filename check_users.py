#!/usr/bin/env python3
"""
Script to check existing users in the database
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import User, UserInventory

def check_existing_users():
    """Check what users exist in the database"""
    with app.app_context():
        try:
            print("=== Existing Users in Database ===")

            # Get all users
            users = User.query.all()

            if not users:
                print("No users found in database.")
                print("\nDefault users will be created when the app starts:")
                print("- Username: 'admin', Password: 'admin123' (Admin role)")
                print("- Username: 'user', Password: 'user123' (User role)")
                return

            print(f"Found {len(users)} user(s):")
            print("-" * 50)

            for user in users:
                print(f"ID: {user.id}")
                print(f"Username: {user.username}")
                print(f"Email: {user.email or 'Not set'}")
                print(f"Role: {user.role}")
                print(f"Created: {user.created_at}")

                # Check if user has inventory
                inventory = UserInventory.query.filter_by(user_id=user.id).first()
                if inventory:
                    print(f"Inventory: {'Public' if inventory.is_public else 'Private'} (ID: {inventory.id})")
                    item_count = len(inventory.items) if hasattr(inventory, 'items') else 0
                    print(f"Inventory Items: {item_count}")
                else:
                    print("Inventory: Not created yet")

                print("-" * 30)

            print("\n=== Login Credentials ===")
            for user in users:
                password_hint = ""
                if user.username == 'admin':
                    password_hint = " (Password: admin123)"
                elif user.username == 'user':
                    password_hint = " (Password: user123)"

                print(f"- {user.username}{password_hint}")

        except Exception as e:
            print(f"Error checking users: {e}")

if __name__ == "__main__":
    check_existing_users()