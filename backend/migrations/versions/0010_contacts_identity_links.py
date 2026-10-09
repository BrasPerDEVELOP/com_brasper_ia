"""Contactos internos con alias por proveedor/conexión, grants de vinculación y locks sin Redis.

Migración aditiva. La asignación de contacto a conversaciones históricas la hace
`core.contacts.backfill()` al iniciar (idempotente, por alias exacto; nunca fusiona por
nombre). Volver al esquema anterior requiere restaurar un backup verificado.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_contacts_identity_links"
down_revision = "0009_autonomous_attention"
branch_labels = None
depends_on = None

DDL = [
    "CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, display_name TEXT, phone_e164 TEXT, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS contacts_phone ON contacts(phone_e164)",
    "CREATE TABLE IF NOT EXISTS contact_aliases (provider TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', "
    "external_id TEXT NOT NULL, kind TEXT NOT NULL, contact_id TEXT NOT NULL, created_at TEXT NOT NULL, "
    "PRIMARY KEY(provider, connection_id, external_id))",
    "CREATE INDEX IF NOT EXISTS contact_aliases_contact ON contact_aliases(contact_id)",
    "CREATE TABLE IF NOT EXISTS contact_conflicts (id TEXT PRIMARY KEY, provider TEXT NOT NULL, "
    "connection_id TEXT NOT NULL, external_id TEXT NOT NULL, existing_contact_id TEXT NOT NULL, "
    "proposed_contact_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT, "
    "resolved_by TEXT)",
    "CREATE TABLE IF NOT EXISTS identity_grants (conversation_id TEXT PRIMARY KEY, channel TEXT NOT NULL, "
    "subject_hash TEXT NOT NULL, brasper_user_id TEXT NOT NULL, grant_ciphertext TEXT NOT NULL, "
    "expires_at TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS conversation_locks (name TEXT PRIMARY KEY, token TEXT NOT NULL, "
    "expires_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS outbound_messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
    "channel TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', recipient TEXT NOT NULL, kind TEXT NOT NULL, "
    "human_revision INTEGER, text_sha256 TEXT, state TEXT NOT NULL, provider_message_id TEXT, detail TEXT, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS outbound_provider ON outbound_messages(connection_id, provider_message_id)",
    "CREATE INDEX IF NOT EXISTS outbound_inflight ON outbound_messages(connection_id, recipient, state)",
    "CREATE TABLE IF NOT EXISTS channel_events (provider TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', "
    "event_id TEXT NOT NULL, kind TEXT NOT NULL, recipient TEXT, payload TEXT NOT NULL, state TEXT NOT NULL, "
    "received_at TEXT NOT NULL, processed_at TEXT, PRIMARY KEY(provider, connection_id, event_id))",
    "CREATE INDEX IF NOT EXISTS channel_events_state ON channel_events(kind, state)",
]


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("conversations")}
    if "contact_id" not in columns:
        op.add_column("conversations", sa.Column("contact_id", sa.Text(), nullable=True))
    if "access_scope" not in {c["name"] for c in sa.inspect(bind).get_columns("panel_users")}:
        op.add_column("panel_users", sa.Column("access_scope", sa.Text(), nullable=True))
    for sql in DDL:
        bind.execute(sa.text(sql))


def downgrade():
    raise RuntimeError("Restore a verified backup for schema rollback; contact links and grants are evidence")
