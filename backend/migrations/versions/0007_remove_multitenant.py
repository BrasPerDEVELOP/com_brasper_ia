"""remove multitenant

Revision ID: 0007_remove_multitenant
Revises: 0006_lead_data
Create Date: 2026-07-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_remove_multitenant"
down_revision = "0006_lead_data"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Drop tables that are strictly for multi-tenancy configuration
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TABLE IF EXISTS channel_configs")
    op.execute("DROP TABLE IF EXISTS connector_configs")

    if _postgres():
        # Postgres allows dropping constraints and columns cleanly
        op.execute("ALTER TABLE panel_users DROP COLUMN IF EXISTS tenant_scope")
        
        op.execute("ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_pkey CASCADE")
        op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS tenant_id CASCADE")
        op.execute("ALTER TABLE conversations ADD PRIMARY KEY (id)")
        
        for table in ("messages", "usage_events", "audit_events"):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id CASCADE")
            
    else:
        # SQLite: use Alembic's batch_alter_table to handle table recreation safely
        with op.batch_alter_table("panel_users") as batch_op:
            batch_op.drop_column("tenant_scope")
            
        # For conversations, we must recreate the primary key
        with op.batch_alter_table("conversations", recreate=True) as batch_op:
            batch_op.drop_column("tenant_id")
            # Note: batch_alter_table automatically infers the new PK if id is the only remaining pk column
            
        tables = ["messages", "usage_events", "audit_events"]
        # Also include appointments and tool_results if they exist in your SQLite
        for table in tables:
            try:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.drop_column("tenant_id")
            except Exception:
                pass


def downgrade() -> None:
    pass  # Unidirectional migration
