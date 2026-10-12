"""Create two demo users and print their tokens into .env (never commit .env).

    uv run python seed_users.py >> ../.env
"""

import secrets

from app import db

db.init_schema()
for name, role, var in [("张老师", "staff", "STAFF_TOKEN"), ("李会计", "reviewer", "REVIEWER_TOKEN")]:
    token = secrets.token_urlsafe(24)
    db.add_user(name, role, token)
    print(f"{var}={token}")
