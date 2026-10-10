"""Credenciales individuales del panel: contraseña (scrypt), cuentas activas y sesiones con hash.

Aditiva: los usuarios existentes quedan activos y sin contraseña, así que el owner actual
sigue entrando por la vía de compatibilidad (PANEL_LOGIN_CODE / PANEL_ADMIN_TOKEN) hasta
fijar su contraseña (`manage.py set-password`). `core.auth.ensure_schema()` aplica lo mismo
en SQLite/arranque. Volver atrás requiere restaurar un backup verificado.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_panel_user_credentials"
down_revision = "0011_tenant_column_leftovers"
branch_labels = None
depends_on = None

COLUMNS = (
    ("password_hash", sa.Text(), True, None),
    ("active", sa.Integer(), False, "1"),
    ("must_change_password", sa.Integer(), False, "0"),
    ("password_changed_at", sa.Text(), True, None),
    ("deactivated_at", sa.Text(), True, None),
)


def upgrade():
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("panel_users")}
    for name, type_, nullable, default in COLUMNS:
        if name not in existing:
            op.add_column("panel_users", sa.Column(name, type_, nullable=nullable,
                                                   server_default=sa.text(default) if default else None))
    user_id = "BIGINT" if bind.dialect.name == "postgresql" else "INTEGER"
    bind.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS panel_sessions (token_hash TEXT PRIMARY KEY, "
        f"user_id {user_id} NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, "
        "revoked_at TEXT, method TEXT)"))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_panel_sessions_user ON panel_sessions(user_id)"))


def downgrade():
    raise RuntimeError("Restore a verified backup for schema rollback; credentials and sessions are security state")
