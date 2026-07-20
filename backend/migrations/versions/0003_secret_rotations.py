"""secret rotations

Revision ID: 0003_secret_rotations
Revises: 0002_appointments
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op

revision = "0003_secret_rotations"
down_revision = "0002_appointments"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("""
        CREATE TABLE IF NOT EXISTS secret_rotations (
          id BIGSERIAL PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          actor TEXT,
          secret_path TEXT NOT NULL,
          env_name TEXT NOT NULL,
          note TEXT,
          rotated_at TIMESTAMPTZ NOT NULL
        )
        """)
    else:
        op.execute("""
        CREATE TABLE IF NOT EXISTS secret_rotations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tenant_id TEXT NOT NULL,
          actor TEXT,
          secret_path TEXT NOT NULL,
          env_name TEXT NOT NULL,
          note TEXT,
          rotated_at TEXT NOT NULL
        )
        """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_secret_rotations_tenant ON secret_rotations(tenant_id, rotated_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS secret_rotations")
