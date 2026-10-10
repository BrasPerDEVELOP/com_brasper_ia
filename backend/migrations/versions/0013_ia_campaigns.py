"""Campañas con persistencia propia en la plataforma IA, registro de ofertas y expediente de operación.

Aditiva. Las campañas del diseño anterior (API financiera) se importan como BORRADOR con
`python manage.py import-campaigns` (idempotente); no se publican automáticamente.
Volver al esquema anterior requiere restaurar un backup verificado.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_ia_campaigns"
down_revision = "0012_panel_user_credentials"
branch_labels = None
depends_on = None

DDL = [
    "CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, "
    "latest_version INTEGER NOT NULL, published_version INTEGER, active INTEGER NOT NULL DEFAULT 0, "
    "used_count INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS campaign_versions (campaign_id TEXT NOT NULL, version INTEGER NOT NULL, "
    "payload TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(campaign_id, version))",
    "CREATE TABLE IF NOT EXISTS campaign_benefits (id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, "
    "campaign_version INTEGER NOT NULL, person_key TEXT NOT NULL, conversation_id TEXT, operation_ref TEXT, "
    "state TEXT NOT NULL, eligibility_source TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, closed_by TEXT)",
    "CREATE INDEX IF NOT EXISTS campaign_benefits_campaign ON campaign_benefits(campaign_id, state)",
    "CREATE TABLE IF NOT EXISTS campaign_person_uses (campaign_id TEXT NOT NULL, person_key TEXT NOT NULL, "
    "used INTEGER NOT NULL, PRIMARY KEY(campaign_id, person_key))",
    "CREATE TABLE IF NOT EXISTS first_transfer_claims (identity_key TEXT PRIMARY KEY, benefit_id TEXT NOT NULL, "
    "created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS campaign_offers (subject TEXT NOT NULL, coupon_id TEXT NOT NULL, "
    "version INTEGER NOT NULL, conversation_id TEXT NOT NULL, language TEXT NOT NULL, asset_id TEXT, "
    "asset_version INTEGER, offered_at TEXT NOT NULL, delivery_key TEXT, state TEXT NOT NULL DEFAULT 'prepared', "
    "updated_at TEXT, PRIMARY KEY(subject, coupon_id, version))",
    "CREATE TABLE IF NOT EXISTS campaign_benefit_events (benefit_id TEXT NOT NULL, from_state TEXT, "
    "to_state TEXT NOT NULL, actor TEXT, note TEXT, at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS campaign_benefit_events_benefit ON campaign_benefit_events(benefit_id)",
    "CREATE TABLE IF NOT EXISTS sales_cases (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, status TEXT NOT NULL, "
    "quote TEXT NOT NULL, campaign TEXT, accepted_at TEXT NOT NULL, quote_expires_at TEXT, operation_ref TEXT, "
    "proofs TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL, updated_by TEXT)",
    "CREATE INDEX IF NOT EXISTS sales_cases_conversation ON sales_cases(conversation_id, status)",
]


def upgrade():
    bind = op.get_bind()
    for sql in DDL:
        bind.execute(sa.text(sql))


def downgrade():
    raise RuntimeError("Restore a verified backup for schema rollback; campaign benefits are financial evidence")
