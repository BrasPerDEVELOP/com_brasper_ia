"""Versioned attention settings, private media metadata and durable follow-ups.

Additive migration. Old application binaries can be restored while retaining data;
physical schema rollback requires an independently verified backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_autonomous_attention"
down_revision = "0008_brasper_modeling"
branch_labels = None
depends_on = None

DDL = [('CREATE TABLE IF NOT EXISTS idempotency_keys (key TEXT PRIMARY KEY, scope TEXT NOT NULL, result TEXT, '
  'created_at TEXT NOT NULL)',
  ()),
 ('CREATE TABLE IF NOT EXISTS agent_presence (email TEXT PRIMARY KEY, status TEXT NOT NULL, last_seen TEXT '
  'NOT NULL, updated_at TEXT NOT NULL)',
  ()),
 ('CREATE TABLE IF NOT EXISTS public_documents (id SERIAL PRIMARY KEY, slug TEXT NOT NULL, lang TEXT NOT '
  'NULL, version INTEGER NOT NULL, title TEXT NOT NULL, body_md TEXT NOT NULL, status TEXT NOT NULL, author '
  'TEXT, created_at TEXT NOT NULL, published_at TEXT, published_by TEXT)',
  ()),
 ('CREATE TABLE IF NOT EXISTS deletion_requests (id SERIAL PRIMARY KEY, contact TEXT NOT NULL, channel TEXT, '
  "detail TEXT, status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
  'handled_by TEXT, note TEXT)',
  ()),
 ('CREATE UNIQUE INDEX IF NOT EXISTS public_documents_version ON public_documents(slug,lang,version)', ()),
 ('CREATE TABLE IF NOT EXISTS public_document_heads (slug TEXT NOT NULL, lang TEXT NOT NULL, version INTEGER '
  'NOT NULL, PRIMARY KEY(slug,lang))',
  ()),
 ('INSERT INTO public_document_heads(slug,lang,version) SELECT slug,lang,MAX(version) FROM public_documents '
  'GROUP BY slug,lang ON CONFLICT(slug,lang) DO NOTHING',
  ()),
 ('CREATE TABLE IF NOT EXISTS agent_profiles (id TEXT PRIMARY KEY, latest_version INTEGER NOT NULL, '
  'published_version INTEGER, enabled INTEGER NOT NULL DEFAULT 0)',
  ()),
 ('CREATE TABLE IF NOT EXISTS agent_profile_versions (profile_id TEXT NOT NULL, version INTEGER NOT NULL, '
  'payload TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(profile_id, version))',
  ()),
 ('CREATE TABLE IF NOT EXISTS media_library (id TEXT PRIMARY KEY, latest_version INTEGER NOT NULL, '
  'published_version INTEGER, enabled INTEGER NOT NULL DEFAULT 0)',
  ()),
 ('CREATE TABLE IF NOT EXISTS media_library_versions (asset_id TEXT NOT NULL, version INTEGER NOT NULL, '
  'payload TEXT NOT NULL, image_base64 TEXT NOT NULL, mime TEXT NOT NULL, sha256 TEXT NOT NULL, author TEXT '
  'NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(asset_id, version))',
  ()),
 ('CREATE TABLE IF NOT EXISTS engagement_settings (id INTEGER PRIMARY KEY, version INTEGER NOT NULL, payload '
  'TEXT NOT NULL)',
  ()),
 ('INSERT INTO engagement_settings VALUES (1,0,?) ON CONFLICT(id) DO NOTHING',
  ('{"enabled":false,"surveys":false,"timezone":"America/Lima","weekdays":[],"start_hour":9,"end_hour":18,"waiting_minutes":30,"inactivity_minutes":60,"max_reminders":0,"sla_minutes":120,"expiry_hours":24,"allowed_channels":[],"whatsapp_window_seconds":null,"policy_source":""}',)),
 ('CREATE TABLE IF NOT EXISTS engagement_jobs (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, revision '
  'INTEGER NOT NULL, kind TEXT NOT NULL, sequence INTEGER NOT NULL, due_at TEXT NOT NULL, expires_at TEXT '
  'NOT NULL, state TEXT NOT NULL, detail TEXT, UNIQUE(conversation_id,revision,kind,sequence))',
  ()),
 ('CREATE INDEX IF NOT EXISTS engagement_jobs_due ON engagement_jobs(state,due_at)', ()),
 ('CREATE TABLE IF NOT EXISTS satisfaction (job_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, state '
  'TEXT NOT NULL, score INTEGER, comment TEXT, updated_at TEXT NOT NULL, revision INTEGER NOT NULL)',
  ()),
 ('CREATE TABLE IF NOT EXISTS channel_receipts (connection_id TEXT NOT NULL, message_id TEXT NOT NULL, '
  'created_at TEXT NOT NULL, PRIMARY KEY(connection_id,message_id))',
  ())]


def _renumber_duplicate_public_documents(bind):
    """Drafts created concurrently before this index could share a version. Keep the oldest
    row's number and move the rest to the end; never delete evidence to create the index."""
    dups = bind.execute(sa.text("SELECT slug, lang, version FROM public_documents GROUP BY slug, lang, version "
                                "HAVING COUNT(*) > 1")).fetchall()
    for slug, lang, version in dups:
        ids = [r[0] for r in bind.execute(sa.text(
            "SELECT id FROM public_documents WHERE slug=:s AND lang=:l AND version=:v ORDER BY id"),
            {"s": slug, "l": lang, "v": version}).fetchall()]
        for doc_id in ids[1:]:
            top = bind.execute(sa.text("SELECT MAX(version) FROM public_documents WHERE slug=:s AND lang=:l"),
                               {"s": slug, "l": lang}).scalar()
            bind.execute(sa.text("UPDATE public_documents SET version=:n WHERE id=:i"), {"n": top + 1, "i": doc_id})


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("conversations")}
    if "connection_id" not in columns:
        op.add_column("conversations", sa.Column("connection_id", sa.Text(), nullable=True))
    if "human_revision" not in columns:
        op.add_column("conversations", sa.Column("human_revision", sa.Integer(), nullable=False, server_default="0"))
    if "public_documents" in sa.inspect(bind).get_table_names():
        _renumber_duplicate_public_documents(bind)
    for sql, params in DDL:
        if bind.dialect.name != "postgresql":
            sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        names = {f"p{i}": value for i, value in enumerate(params)}
        for name in names:
            sql = sql.replace("?", ":" + name, 1)
        bind.execute(sa.text(sql), names)


def downgrade():
    raise RuntimeError("Restore a verified backup for schema rollback; do not discard customer history or campaign evidence")
