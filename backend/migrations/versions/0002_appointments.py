"""appointments

Revision ID: 0002_appointments
Revises: 0001_production_schema
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op

revision = "0002_appointments"
down_revision = "0001_production_schema"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
          id BIGSERIAL PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          conversation_id TEXT,
          user_ref TEXT,
          patient_name TEXT NOT NULL,
          document_id TEXT,
          specialty TEXT NOT NULL,
          scheduled_for TIMESTAMPTZ NOT NULL,
          status TEXT NOT NULL DEFAULT 'scheduled',
          metadata JSONB,
          created_at TIMESTAMPTZ NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL
        )
        """)
    else:
        op.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          conversation_id TEXT,
          user_ref TEXT,
          patient_name TEXT NOT NULL,
          document_id TEXT,
          specialty TEXT NOT NULL,
          scheduled_for TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'scheduled',
          metadata TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_appointments_tenant ON appointments(tenant_id, scheduled_for DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS appointments")
