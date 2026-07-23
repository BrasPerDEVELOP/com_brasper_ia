"""brasper modeling

Revision ID: 0008_brasper_modeling
Revises: 0007_remove_multitenant
Create Date: 2026-07-23
"""
from __future__ import annotations

from alembic import op

revision = "0008_brasper_modeling"
down_revision = "0007_remove_multitenant"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("""
        CREATE TABLE IF NOT EXISTS customers (
          id SERIAL PRIMARY KEY,
          phone_number TEXT UNIQUE NOT NULL,
          name TEXT,
          document_type TEXT,
          document_number TEXT,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TIMESTAMPTZ NOT NULL
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
          id SERIAL PRIMARY KEY,
          customer_id INTEGER,
          conversation_id TEXT,
          from_currency TEXT,
          to_currency TEXT,
          amount_send NUMERIC(18,4),
          amount_receive NUMERIC(18,4),
          exchange_rate NUMERIC(18,6),
          fee NUMERIC(18,4),
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TIMESTAMPTZ NOT NULL
        )
        """)
        op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS customer_id INTEGER")
    else:
        op.execute("""
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          phone_number TEXT UNIQUE NOT NULL,
          name TEXT,
          document_type TEXT,
          document_number TEXT,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER,
          conversation_id TEXT,
          from_currency TEXT,
          to_currency TEXT,
          amount_send REAL,
          amount_receive REAL,
          exchange_rate REAL,
          fee REAL,
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL
        )
        """)
        try:
            op.execute("ALTER TABLE conversations ADD COLUMN customer_id INTEGER")
        except Exception:
            pass


def downgrade() -> None:
    pass
