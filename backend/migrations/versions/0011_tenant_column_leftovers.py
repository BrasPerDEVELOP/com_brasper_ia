"""appointments / secret_rotations still had tenant_id NOT NULL after 0007.

The single-tenant code no longer sends tenant_id, so both inserts failed on databases
built by migrations. Additive and data-preserving: existing rows keep their value; new
rows get 'brasper'. Downgrade is a no-op (restoring NOT NULL without default would break
current code).
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_tenant_column_leftovers"
down_revision = "0010_contacts_identity_links"
branch_labels = None
depends_on = None

TABLES = ("appointments", "secret_rotations")


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        if "tenant_id" not in {c["name"] for c in inspector.get_columns(table)}:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT 'brasper'")
            op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
        else:
            with op.batch_alter_table(table) as batch:
                batch.alter_column("tenant_id", existing_type=sa.Text(), nullable=True,
                                   server_default="brasper")


def downgrade():
    pass
