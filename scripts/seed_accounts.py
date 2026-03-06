"""Seed social accounts into the database.
Usage: python scripts/seed_accounts.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.social_account_manager import social_account_manager

ACCOUNTS = [
    {
        "platform": "facebook",
        "email": "analytics360@yopmail.com",
        "password": "Ultra64#.",
        "notes": "Cuenta de prueba Analytics 360",
    },
    {
        "platform": "instagram",
        "email": "analytics360@yopmail.com",
        "password": "Ultra64#.",
        "notes": "Cuenta de prueba Analytics 360",
    },
    {
        "platform": "tiktok",
        "email": "analytics360@yopmail.com",
        "password": "Ultra64#.",
        "notes": "Cuenta de prueba Analytics 360",
    },
]


def main():
    social_account_manager.init()
    for acc in ACCOUNTS:
        try:
            account_id = social_account_manager.add_account(
                platform=acc["platform"],
                email=acc["email"],
                password=acc["password"],
                notes=acc["notes"],
            )
            print(f"Added {acc['platform']} account: {acc['email']} (id={account_id})")
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                print(f"Already exists: {acc['platform']} / {acc['email']}")
            else:
                print(f"Error adding {acc['platform']} / {acc['email']}: {e}")

    print("\nAll accounts:")
    for a in social_account_manager.get_all_accounts():
        print(f"  [{a['id']}] {a['platform']:12} {a['email']:30} status={a['status']}")


if __name__ == "__main__":
    main()
