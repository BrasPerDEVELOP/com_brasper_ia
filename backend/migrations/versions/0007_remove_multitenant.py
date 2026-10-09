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


def _drop_sqlite_column(table: str, column: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    if column not in {c["name"] for c in inspector.get_columns(table)}:
        return
    with op.batch_alter_table(table, recreate="always") as batch_op:
        for index in inspector.get_indexes(table):
            if column in index["column_names"]:
                batch_op.drop_index(index["name"])
        batch_op.drop_column(column)


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
        # Drop indexes referring to removed columns before recreating each table.
        # Failures must remain visible; silently swallowing them leaves mixed schemas.
        _drop_sqlite_column("panel_users", "tenant_scope")
        for table in ("conversations", "messages", "usage_events", "audit_events"):
            _drop_sqlite_column(table, "tenant_id")
        op.execute("CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC)")


def downgrade() -> None:
    pass  # Unidirectional migration
