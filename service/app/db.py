"""PostgreSQL access: users, audit log, feedback."""

import hashlib
import json
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('staff', 'reviewer')),
    token_hash  TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id         INT REFERENCES users(id),
    role            TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    citations       JSONB NOT NULL,
    citation_ok     BOOLEAN NOT NULL,
    blocked         BOOLEAN NOT NULL DEFAULT false,
    latency_ms      INT,
    dify_message_id TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    audit_id    BIGINT PRIMARY KEY REFERENCES audit_log(id),
    helpful     BOOLEAN NOT NULL,
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def connect():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        yield conn


def init_schema():
    with connect() as conn:
        conn.execute(SCHEMA)


def user_by_token(token: str):
    with connect() as conn:
        return conn.execute("SELECT id, name, role FROM users WHERE token_hash = %s", (hash_token(token),)).fetchone()


def add_user(name: str, role: str, token: str):
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (name, role, token_hash) VALUES (%s, %s, %s) ON CONFLICT (token_hash) DO NOTHING",
            (name, role, hash_token(token)),
        )


def log_answer(user, question, answer, check, blocked, latency_ms, message_id) -> int:
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO audit_log (user_id, role, question, answer, citations, citation_ok, blocked, latency_ms, dify_message_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (user["id"], user["role"], question, answer, json.dumps(check.model_dump(), ensure_ascii=False),
             check.ok, blocked, latency_ms, message_id),
        ).fetchone()
        return row["id"]


def add_feedback(audit_id: int, user_id: int, helpful: bool, comment: str | None) -> bool:
    with connect() as conn:
        owner = conn.execute("SELECT user_id FROM audit_log WHERE id = %s", (audit_id,)).fetchone()
        if not owner or owner["user_id"] != user_id:
            return False
        conn.execute(
            """INSERT INTO feedback (audit_id, helpful, comment) VALUES (%s, %s, %s)
               ON CONFLICT (audit_id) DO UPDATE SET helpful = EXCLUDED.helpful, comment = EXCLUDED.comment""",
            (audit_id, helpful, comment),
        )
        return True
