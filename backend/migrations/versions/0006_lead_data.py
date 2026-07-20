"""lead data estructurada por conversación (idioma, ruta, monto, KYC…)

Revision ID: 0006_lead_data
Revises: 0005_message_media
Create Date: 2026-07-16
"""
from __future__ import annotations

from alembic import op

revision = "0006_lead_data"
down_revision = "0005_message_media"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS lead_data TEXT")
    else:
        try:
            op.execute("ALTER TABLE conversations ADD COLUMN lead_data TEXT")
        except Exception:  # noqa: BLE001 - ya existe
            pass


def downgrade() -> None:
    if _postgres():
        op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS lead_data")
