"""message media (adjuntos entrantes/salientes)

Revision ID: 0005_message_media
Revises: 0004_conversation_assignment
Create Date: 2026-07-16
"""
from __future__ import annotations

from alembic import op

revision = "0005_message_media"
down_revision = "0004_conversation_assignment"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_json TEXT")
    else:
        try:
            op.execute("ALTER TABLE messages ADD COLUMN media_json TEXT")
        except Exception:  # noqa: BLE001 - ya existe
            pass


def downgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS media_json")
