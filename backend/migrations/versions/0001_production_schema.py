"""production schema

Revision ID: 0001_production_schema
Revises:
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op

revision = "0001_production_schema"
down_revision = None
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        _upgrade_postgres()
    else:
        _upgrade_sqlite()


def downgrade() -> None:
    for table in (
        "connector_configs",
        "channel_configs",
        "tenants",
        "audit_events",
        "usage_events",
        "messages",
        "conversations",
        "panel_users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def _upgrade_postgres() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS panel_users (
      id BIGSERIAL PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      role TEXT NOT NULL,
      tenant_scope TEXT,
      token TEXT NOT NULL UNIQUE
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_panel_users_token ON panel_users(token)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
      id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      channel TEXT NOT NULL DEFAULT 'webchat',
      user_ref TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      started_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL,
      PRIMARY KEY (tenant_id, id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_conv_tenant ON conversations(tenant_id, updated_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id BIGSERIAL PRIMARY KEY,
      conversation_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(tenant_id, conversation_id, id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS usage_events (
      id BIGSERIAL PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      conversation_id TEXT,
      provider TEXT,
      model TEXT,
      tokens_in INTEGER NOT NULL DEFAULT 0,
      tokens_out INTEGER NOT NULL DEFAULT 0,
      cost_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_events(tenant_id, created_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_events (
      id BIGSERIAL PRIMARY KEY,
      tenant_id TEXT,
      actor TEXT,
      action TEXT NOT NULL,
      resource TEXT,
      metadata JSONB,
      created_at TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id, created_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      vertical TEXT,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS channel_configs (
      id BIGSERIAL PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      channel TEXT NOT NULL,
      config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL,
      UNIQUE (tenant_id, channel)
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS connector_configs (
      id BIGSERIAL PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      connector_key TEXT NOT NULL,
      config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL,
      UNIQUE (tenant_id, connector_key)
    )
    """)


def _upgrade_sqlite() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS panel_users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      role TEXT NOT NULL,
      tenant_scope TEXT,
      token TEXT NOT NULL UNIQUE
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_panel_users_token ON panel_users(token)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
      id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      channel TEXT NOT NULL DEFAULT 'webchat',
      user_ref TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      started_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (tenant_id, id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_conv_tenant ON conversations(tenant_id, updated_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(tenant_id, conversation_id, id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS usage_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      conversation_id TEXT,
      provider TEXT,
      model TEXT,
      tokens_in INTEGER NOT NULL DEFAULT 0,
      tokens_out INTEGER NOT NULL DEFAULT 0,
      cost_usd REAL NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_events(tenant_id, created_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT,
      actor TEXT,
      action TEXT NOT NULL,
      resource TEXT,
      metadata TEXT,
      created_at TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id, created_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      vertical TEXT,
      active INTEGER NOT NULL DEFAULT 1,
      config_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS channel_configs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      channel TEXT NOT NULL,
      config_json TEXT NOT NULL DEFAULT '{}',
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE (tenant_id, channel)
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS connector_configs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      connector_key TEXT NOT NULL,
      config_json TEXT NOT NULL DEFAULT '{}',
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE (tenant_id, connector_key)
    )
    """)
