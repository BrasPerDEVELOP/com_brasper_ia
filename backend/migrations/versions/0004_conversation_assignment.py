"""conversation assignment (derivación a asesores)

Revision ID: 0004_conversation_assignment
Revises: 0003_secret_rotations
Create Date: 2026-07-06
"""
from __future__ import annotations

from alembic import op

revision = "0004_conversation_assignment"
down_revision = "0003_secret_rotations"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_to TEXT")
    else:
        # SQLite no soporta IF NOT EXISTS en ADD COLUMN.
        try:
            op.execute("ALTER TABLE conversations ADD COLUMN assigned_to TEXT")
        except Exception:  # noqa: BLE001 - ya existe
            pass


def downgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS assigned_to")
    # SQLite: DROP COLUMN moderno lo soporta; si falla, se ignora (columna inocua).
