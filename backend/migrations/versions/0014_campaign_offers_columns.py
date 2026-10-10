"""Repara `campaign_offers` del diseño anterior (8 columnas) y liga beneficios al expediente.

`0013` solo hace CREATE TABLE IF NOT EXISTS: si la tabla ya existía sin `delivery_key`,
`state` y `updated_at`, el código nuevo falla al registrar ofertas. Esta migración agrega
las columnas que falten y completa las ofertas antiguas SIN reenviarlas:
`state='legacy_unverified'` (no se sabe si se entregaron; nunca se marcan como enviadas ni
vuelven a ofrecerse porque la clave contacto/campaña/versión ya existe).
Aditiva; no borra ni reescribe ofertas. Downgrade: restaurar backup.
"""
import hashlib

from alembic import op
import sqlalchemy as sa

revision = "0014_campaign_offers_columns"
down_revision = "0013_ia_campaigns"
branch_labels = None
depends_on = None


def _key(*parts) -> str:  # misma fórmula que core.idempotency.make_key
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:40]


BENEFIT_COLUMNS = (("case_id", sa.Text()), ("commission_gross", sa.Float()), ("discount", sa.Float()),
                   ("commission_final", sa.Float()), ("evidence", sa.Text()))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Beneficios ligados al expediente aceptado, con desglose y evidencia de verificación humana.
    if "campaign_benefits" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("campaign_benefits")}
        for name, kind in BENEFIT_COLUMNS:
            if name not in existing:
                op.add_column("campaign_benefits", sa.Column(name, kind, nullable=True))
    if "campaign_offers" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("campaign_offers")}
    if "delivery_key" not in columns:
        op.add_column("campaign_offers", sa.Column("delivery_key", sa.Text(), nullable=True))
    if "state" not in columns:
        op.add_column("campaign_offers", sa.Column("state", sa.Text(), nullable=False,
                                                   server_default="legacy_unverified"))
    if "updated_at" not in columns:
        op.add_column("campaign_offers", sa.Column("updated_at", sa.Text(), nullable=True))
    rows = bind.execute(sa.text("SELECT subject, coupon_id, version, language, offered_at FROM campaign_offers "
                                "WHERE delivery_key IS NULL")).fetchall()
    for subject, coupon_id, version, language, offered_at in rows:
        bind.execute(sa.text("UPDATE campaign_offers SET delivery_key=:k, updated_at=COALESCE(updated_at, :t) "
                             "WHERE subject=:s AND coupon_id=:c AND version=:v"),
                     {"k": _key("campaign_offer", subject, coupon_id, version, language), "t": offered_at,
                      "s": subject, "c": coupon_id, "v": version})


def downgrade():
    raise RuntimeError("Restore a verified backup for schema rollback; offers are delivery evidence")
