"""Persistencia multi-tenant.

Produccion usa Postgres via DATABASE_URL. SQLite queda como fallback local y
para pruebas sin servicios externos.
"""
import os
import json
import sqlite3
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "plataforma.db"


def database_url() -> str | None:
    value = (os.getenv("DATABASE_URL") or "").strip()
    return value or None


def is_postgres() -> bool:
    url = database_url()
    return bool(url and not url.startswith("sqlite:"))


def backend_name() -> str:
    return "postgres" if is_postgres() else "sqlite"


def assert_production_infra() -> None:
    """Fail-fast en produccion: Postgres y Redis son OBLIGATORIOS.

    SQLite existe solo como fallback de desarrollo/tests; en APP_ENV=production
    la app no debe ni arrancar sin la infraestructura real (plan §4/§10).
    """
    from .util import is_production
    if not is_production():
        return
    if not is_postgres():
        raise RuntimeError(
            "APP_ENV=production requiere DATABASE_URL de Postgres. "
            "SQLite es solo para desarrollo/tests (plan §4).")
    if not (os.getenv("REDIS_URL") or "").strip():
        raise RuntimeError(
            "APP_ENV=production requiere REDIS_URL (locks, colas, debounce).")


from .util import now_iso as _now  # noqa: E402  (timestamp UTC único, ver core/util.py)


def _qmark_to_pg(sql: str) -> str:
    """Convierte placeholders simples `?` a `%s` para psycopg.

    Las queries del proyecto no contienen `?` dentro de strings SQL, así que un
    replace directo mantiene el wrapper pequeño y legible.
    """
    return sql.replace("?", "%s")


class _PgConn:
    def __init__(self, url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as e:  # pragma: no cover - solo cuando falta dependencia en prod
            raise RuntimeError(
                "DATABASE_URL requiere psycopg. Instala requirements.txt antes de arrancar."
            ) from e
        self._conn = psycopg.connect(url, row_factory=dict_row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def execute(self, sql: str, args: tuple | list = ()):
        return self._conn.execute(_qmark_to_pg(sql), tuple(args or ()))

    def executemany(self, sql: str, seq):
        with self._conn.cursor() as cur:
            cur.executemany(_qmark_to_pg(sql), seq)
            return cur

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)


def connect():
    """Devuelve una conexion SQLite o Postgres con API execute/fetch compatible."""
    url = database_url()
    if is_postgres():
        return _PgConn(url)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@lru_cache(maxsize=32)
def has_column(table: str, column: str) -> bool:
    """Compatibilidad temporal entre el esquema multi-tenant histórico y el
    esquema single-tenant desplegado por la migración 0007."""
    if not table.replace("_", "").isalnum() or not column.replace("_", "").isalnum():
        raise ValueError("Identificador SQL inválido")
    with connect() as con:
        if is_postgres():
            row = con.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=? AND column_name=?",
                (table, column),
            ).fetchone()
            return row is not None
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(_rowdict(row).get("name") == column for row in rows)


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  channel TEXT NOT NULL DEFAULT 'webchat',
  user_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  assigned_to TEXT,
  lead_data TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  media_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS usage_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  conversation_id TEXT,
  provider TEXT,
  model TEXT,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT DEFAULT 'brasper',
  actor TEXT,
  action TEXT NOT NULL,
  resource TEXT,
  metadata TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS channel_configs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel TEXT NOT NULL UNIQUE,
  config_json TEXT NOT NULL DEFAULT '{}',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connector_configs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  connector_key TEXT NOT NULL UNIQUE,
  config_json TEXT NOT NULL DEFAULT '{}',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT,
  user_ref TEXT,
  patient_name TEXT NOT NULL,
  document_id TEXT,
  specialty TEXT NOT NULL,
  scheduled_for TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  metadata TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled ON appointments(scheduled_for DESC);

CREATE TABLE IF NOT EXISTS secret_rotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT,
  secret_path TEXT NOT NULL,
  env_name TEXT NOT NULL,
  note TEXT,
  rotated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_secret_rotations_rotated ON secret_rotations(rotated_at DESC);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone_number TEXT UNIQUE NOT NULL,
  name TEXT,
  document_type TEXT,
  document_number TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER,
  conversation_id TEXT,
  from_currency TEXT,
  to_currency TEXT,
  amount_send REAL,
  amount_receive REAL,
  exchange_rate REAL,
  fee REAL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  channel TEXT NOT NULL DEFAULT 'webchat',
  user_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  assigned_to TEXT,
  lead_data TEXT,
  started_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  media_json TEXT,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS usage_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'brasper',
  conversation_id TEXT,
  provider TEXT,
  model TEXT,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT DEFAULT 'brasper',
  actor TEXT,
  action TEXT NOT NULL,
  resource TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS channel_configs (
  id BIGSERIAL PRIMARY KEY,
  channel TEXT NOT NULL UNIQUE,
  config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS connector_configs (
  id BIGSERIAL PRIMARY KEY,
  connector_key TEXT NOT NULL UNIQUE,
  config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
  id BIGSERIAL PRIMARY KEY,
  conversation_id TEXT,
  user_ref TEXT,
  patient_name TEXT NOT NULL,
  document_id TEXT,
  specialty TEXT NOT NULL,
  scheduled_for TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled ON appointments(scheduled_for DESC);

CREATE TABLE IF NOT EXISTS secret_rotations (
  id BIGSERIAL PRIMARY KEY,
  actor TEXT,
  secret_path TEXT NOT NULL,
  env_name TEXT NOT NULL,
  note TEXT,
  rotated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_secret_rotations_rotated ON secret_rotations(rotated_at DESC);

CREATE TABLE IF NOT EXISTS customers (
  id SERIAL PRIMARY KEY,
  phone_number TEXT UNIQUE NOT NULL,
  name TEXT,
  document_type TEXT,
  document_number TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
  id SERIAL PRIMARY KEY,
  customer_id INTEGER,
  conversation_id TEXT,
  from_currency TEXT,
  to_currency TEXT,
  amount_send NUMERIC(18,4),
  amount_receive NUMERIC(18,4),
  exchange_rate NUMERIC(18,6),
  fee NUMERIC(18,4),
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL
);
"""


def init_db() -> None:
    with connect() as con:
        con.executescript(_POSTGRES_SCHEMA if is_postgres() else _SQLITE_SCHEMA)
    _ensure_columns()
    # Tablas de los módulos de atención autónoma (importación local: ellos importan db).
    from . import idempotency, presence, public_docs  # noqa: PLC0415
    idempotency.ensure_schema()
    presence.ensure_schema()
    public_docs.ensure_schema()
    from . import agent_profiles
    agent_profiles.ensure_schema()
    from . import media_library
    media_library.ensure_schema()
    from . import engagement
    engagement.ensure_schema()
    from . import channel_receipts
    channel_receipts.ensure_schema()
    from . import identity_link
    identity_link.ensure_schema()
    from . import db_lock
    db_lock.ensure_schema()
    from . import outbound, channel_events
    outbound.ensure_schema()
    channel_events.ensure_schema()
    from . import access
    access.ensure_schema()
    from . import campaign_offers, campaigns
    campaign_offers.ensure_schema()
    campaigns.ensure_schema()
    from . import cases
    cases.ensure_schema()
    from . import contacts
    contacts.ensure_schema()
    contacts.backfill()


def _ensure_columns() -> None:
    """Columnas añadidas después del CREATE inicial (bases ya existentes).

    CREATE IF NOT EXISTS no altera tablas viejas; esto aplica el ALTER de forma
    idempotente (equivalente runtime de la migración 0004).
    """
    for ddl in ("ALTER TABLE conversations ADD COLUMN assigned_to TEXT",
                "ALTER TABLE messages ADD COLUMN media_json TEXT",
                "ALTER TABLE conversations ADD COLUMN lead_data TEXT",
                "ALTER TABLE conversations ADD COLUMN customer_id INTEGER",
                # Panel v2: quién escribió el mensaje saliente (bot vs asesor).
                "ALTER TABLE messages ADD COLUMN sender TEXT",
                "ALTER TABLE messages ADD COLUMN agent_email TEXT",
                # Varios números WhatsApp: conexión (phone_number_id) de origen por conversación.
                "ALTER TABLE conversations ADD COLUMN connection_id TEXT",
                "ALTER TABLE conversations ADD COLUMN human_revision INTEGER NOT NULL DEFAULT 0"):
        try:
            with connect() as con:
                con.execute(ddl)
        except Exception:  # noqa: BLE001 - la columna ya existe
            pass
    # Notas internas del asesor (no se envían al cliente).
    notes_ddl = (
        "CREATE TABLE IF NOT EXISTS conversation_notes ("
        + ("id SERIAL PRIMARY KEY," if is_postgres() else "id INTEGER PRIMARY KEY AUTOINCREMENT,")
        + " conversation_id TEXT NOT NULL, author TEXT, text TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    with connect() as con:
        con.execute(notes_ddl)
        con.execute(
            "CREATE TABLE IF NOT EXISTS conversation_tags ("
            "conversation_id TEXT NOT NULL, tag TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL, "
            "PRIMARY KEY (conversation_id, tag))"
        )


def ping() -> bool:
    try:
        with connect() as con:
            con.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def _rowdict(row: Any) -> dict:
    return dict(row) if row is not None else {}


def _lease_guard() -> None:
    """Escrituras del procesamiento de un mensaje solo con el lease vigente (core.lease)."""
    from .lease import guard  # noqa: PLC0415 - lease importa redis_runtime, no db
    guard()


def get_or_create_conversation(*args, conversation_id: str | None = None, connection_id: str | None = None) -> str:
    """Obtiene/crea conversación.

    Acepta la firma actual ``(user_ref, channel, conversation_id?)`` y la
    histórica ``(tenant_id, user_ref, channel, conversation_id?)`` mientras se
    completa la migración single-tenant.
    """
    if len(args) in {3, 4} and str(args[2]) in {"webchat", "telegram", "whatsapp"}:
        tenant_id, user_ref, channel = str(args[0]), str(args[1]), str(args[2])
        if len(args) == 4:
            conversation_id = args[3]
    elif len(args) in {2, 3}:
        tenant_id, user_ref, channel = "brasper", str(args[0]), str(args[1])
        if len(args) == 3:
            conversation_id = args[2]
    else:
        raise TypeError("get_or_create_conversation espera 2-4 argumentos")
    tenant_scoped = has_column("conversations", "tenant_id")
    from . import tenants
    bind_legacy = bool(connection_id and len(tenants.whatsapp_connections()) == 1)
    cid = _get_or_create_conversation(tenant_id, user_ref, channel, conversation_id, connection_id,
                                      tenant_scoped, bind_legacy)
    try:
        from . import contacts  # noqa: PLC0415 - contacts importa db
        provider, external = contacts.split_user_ref(channel, user_ref)
        if external and has_column("conversations", "contact_id"):
            contacts.attach(cid, contacts.resolve(provider, connection_id, external))
    except Exception:  # noqa: BLE001 - el contacto es metadato: nunca bloquea la atención
        import logging
        logging.getLogger(__name__).exception("contact resolution failed")
    return cid


def _creation_lock(con, user_ref: str, channel: str, connection_id: str | None) -> None:
    """Serializa la creación de la conversación abierta de un mismo cliente/canal/conexión:
    dos webhooks simultáneos no abren dos conversaciones."""
    if is_postgres():
        con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"conv:{channel}:{connection_id or ''}:{user_ref}",))
    elif not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")


def _get_or_create_conversation(tenant_id, user_ref, channel, conversation_id, connection_id,
                                tenant_scoped, bind_legacy) -> str:
    with connect() as con:
        if not conversation_id:
            _creation_lock(con, user_ref, channel, connection_id)
        if conversation_id:
            sql = "SELECT id FROM conversations WHERE id=? AND user_ref=? AND channel=?"
            params: tuple = (conversation_id, user_ref, channel)
            if connection_id:
                sql += " AND connection_id=?"
                params += (connection_id,)
            if tenant_scoped:
                sql += " AND tenant_id=?"
                params += (tenant_id,)
            row = con.execute(sql, params).fetchone()
            if row:
                return row["id"]
            if con.execute("SELECT id FROM conversations WHERE id=?", (conversation_id,)).fetchone():
                raise ValueError("La conversación no corresponde al canal, cliente o conexión")
        # Reutiliza la conversación en curso (activa O en handoff): así los mensajes
        # que llegan mientras un asesor atiende NO abren una conversación nueva ni
        # reactivan al bot. Solo 'closed' inicia una conversación fresca.
        sql = "SELECT id FROM conversations WHERE user_ref=? AND channel=? AND status!='closed'"
        params = (user_ref, channel)
        if connection_id:
            sql += " AND (connection_id=? OR connection_id IS NULL)" if bind_legacy else " AND connection_id=?"
            params += (connection_id,)
        if tenant_scoped:
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        row = con.execute(sql + " ORDER BY updated_at DESC LIMIT ?", params + (1,)).fetchone()
        if row and not conversation_id:
            if connection_id:
                con.execute("UPDATE conversations SET connection_id=? WHERE id=? AND connection_id IS NULL", (connection_id, row["id"]))
            return row["id"]
        cid = conversation_id or uuid.uuid4().hex[:12]
        if has_column("conversations", "tenant_id"):
            con.execute(
                "INSERT INTO conversations "
                "(id, tenant_id, channel, user_ref, started_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (cid, tenant_id, channel, user_ref, _now(), _now()))
        else:
            con.execute(
                "INSERT INTO conversations "
                "(id, channel, user_ref, started_at, updated_at) VALUES (?,?,?,?,?)",
                (cid, channel, user_ref, _now(), _now()))
        if connection_id:
            con.execute("UPDATE conversations SET connection_id=? WHERE id=?", (connection_id, cid))
        return cid


def add_message(*args, media: dict | None = None, sender: str | None = None,
                agent_email: str | None = None) -> None:
    """Guarda un mensaje. `sender` distingue quién habla del lado Brasper:
    'user' (cliente), 'bot' (IA/flujos deterministas) o 'agent' (asesor humano).
    Si no se indica, se deduce del role (user→user, assistant→bot)."""
    _lease_guard()
    if len(args) == 4:
        tenant_id, conversation_id, role, content = args
    elif len(args) == 3:
        tenant_id, (conversation_id, role, content) = "brasper", args
    else:
        raise TypeError("add_message espera 3 o 4 argumentos")
    media_json = json.dumps(media, ensure_ascii=False) if media else None
    sender = sender or ("user" if role == "user" else "bot")
    with connect() as con:
        if has_column("messages", "tenant_id"):
            con.execute(
                "INSERT INTO messages "
                "(conversation_id, tenant_id, role, content, media_json, sender, agent_email, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (conversation_id, tenant_id, role, content, media_json, sender, agent_email, _now()))
        else:
            con.execute(
                "INSERT INTO messages "
                "(conversation_id, role, content, media_json, sender, agent_email, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (conversation_id, role, content, media_json, sender, agent_email, _now()))
        con.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (_now(), conversation_id))
        if role == "user":
            con.execute("UPDATE conversations SET human_revision=human_revision+1 WHERE id=?", (conversation_id,))
            con.execute("UPDATE engagement_jobs SET state='cancelled' WHERE conversation_id=? AND state='pending'", (conversation_id,))


def get_history(*args, limit: int = 12) -> list[dict]:
    if len(args) == 2:
        tenant_id, conversation_id = args
    elif len(args) == 1:
        tenant_id, conversation_id = "brasper", args[0]
    else:
        raise TypeError("get_history espera conversation_id o tenant_id, conversation_id")
    scoped = has_column("messages", "tenant_id")
    with connect() as con:
        sql = "SELECT role, content FROM messages WHERE conversation_id=?"
        params: tuple = (conversation_id,)
        if scoped:
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        rows = con.execute(sql + " ORDER BY id DESC LIMIT ?", params + (limit,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def set_conversation_status(*args) -> None:
    _lease_guard()
    if len(args) == 3:
        tenant_id, conversation_id, status = args
    elif len(args) == 2:
        tenant_id, (conversation_id, status) = "brasper", args
    else:
        raise TypeError("set_conversation_status espera 2 o 3 argumentos")
    with connect() as con:
        sql = "UPDATE conversations SET status=?, updated_at=? WHERE id=?"
        params: tuple = (status, _now(), conversation_id)
        if has_column("conversations", "tenant_id"):
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        con.execute(sql, params)


def get_conversation(*args) -> dict | None:
    if len(args) == 2:
        tenant_id, conversation_id = args
    elif len(args) == 1:
        tenant_id, conversation_id = "brasper", args[0]
    else:
        raise TypeError("get_conversation espera 1 o 2 argumentos")
    with connect() as con:
        sql = "SELECT * FROM conversations WHERE id=?"
        params: tuple = (conversation_id,)
        if has_column("conversations", "tenant_id"):
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        row = con.execute(sql, params).fetchone()
    if not row:
        return None
    d = _rowdict(row)
    raw = d.get("lead_data")
    if raw:
        try:
            d["lead_data"] = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            d["lead_data"] = {}
    else:
        d["lead_data"] = {}
    return d


def is_first_contact(*args) -> bool:
    """True si este user_ref aún no tiene ningún mensaje suyo (lead nuevo).
    Llamar ANTES de guardar el mensaje entrante."""
    if len(args) == 2:
        tenant_id, user_ref = args
    elif len(args) == 1:
        tenant_id, user_ref = "brasper", args[0]
    else:
        raise TypeError("is_first_contact espera 1 o 2 argumentos")
    scoped = has_column("conversations", "tenant_id")
    with connect() as con:
        sql = ("SELECT COUNT(*) AS n FROM messages m "
               "JOIN conversations c ON m.conversation_id=c.id "
               "WHERE c.user_ref=? AND m.role='user'")
        params: tuple = (user_ref,)
        if scoped:
            sql += " AND c.tenant_id=? AND m.tenant_id=c.tenant_id"
            params += (tenant_id,)
        row = con.execute(sql, params).fetchone()
    n = row["n"] if not isinstance(row, tuple) else row[0]
    return int(n or 0) == 0


def get_lead_data(*args) -> dict:
    conv = get_conversation(*args)
    return conv.get("lead_data", {}) if conv else {}


def merge_lead_data(*args, allow_null: bool = False) -> dict:
    """Fusiona campos del lead (idioma, ruta, monto, KYC…) sin pisar lo ya guardado
    con valores vacíos. allow_null permite invalidar explícitamente un dato
    anterior cuando su fuente deja de estar disponible."""
    _lease_guard()
    if len(args) == 3:
        tenant_id, conversation_id, updates = args
    elif len(args) == 2:
        tenant_id, (conversation_id, updates) = "brasper", args
    else:
        raise TypeError("merge_lead_data espera 2 o 3 argumentos")
    if not updates:
        return get_lead_data(tenant_id, conversation_id)
    current = get_lead_data(tenant_id, conversation_id)
    for k, v in updates.items():
        if (v is not None and v != "") or (allow_null and v is None):
            current[k] = v
    with connect() as con:
        sql = "UPDATE conversations SET lead_data=?, updated_at=? WHERE id=?"
        params: tuple = (json.dumps(current, ensure_ascii=False), _now(), conversation_id)
        if has_column("conversations", "tenant_id"):
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        con.execute(sql, params)
    return current


def conversation_status(*args) -> str | None:
    conv = get_conversation(*args)
    return conv.get("status") if conv else None


def assign_conversation(*args) -> None:
    _lease_guard()
    if len(args) == 3:
        tenant_id, conversation_id, email = args
    elif len(args) == 2:
        tenant_id, (conversation_id, email) = "brasper", args
    else:
        raise TypeError("assign_conversation espera 2 o 3 argumentos")
    """Deriva la conversación a un asesor del panel (o None para desasignar)."""
    with connect() as con:
        sql = "UPDATE conversations SET assigned_to=?, updated_at=? WHERE id=?"
        params: tuple = (email, _now(), conversation_id)
        if has_column("conversations", "tenant_id"):
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        con.execute(sql, params)


def claim_conversation(conversation_id: str, email: str) -> bool:
    """Asignación con protección de concurrencia: solo si está libre o ya es del mismo
    asesor. Devuelve False si otro asesor la tiene (409 en la API)."""
    _lease_guard()
    with connect() as con:
        cur = con.execute(
            "UPDATE conversations SET assigned_to=?, updated_at=? "
            "WHERE id=? AND (assigned_to IS NULL OR assigned_to=? )",
            (email, _now(), conversation_id, email))
        return bool(cur.rowcount)


def invalidate_ai(conversation_id: str, *, pause: bool = True) -> None:
    """Persist human intervention before delivery; survives pause/resume and restarts."""
    with connect() as con:
        con.execute("UPDATE conversations SET human_revision=human_revision+1, "
                    + ("status='handoff', " if pause else "")
                    + "updated_at=? WHERE id=?", (_now(), conversation_id))
        con.execute("UPDATE engagement_jobs SET state='cancelled' WHERE conversation_id=? AND state='pending'",
                    (conversation_id,))


def set_connection(conversation_id: str, connection_id: str | None) -> None:
    if not connection_id:
        return
    with connect() as con:
        con.execute("UPDATE conversations SET connection_id=? WHERE id=? AND connection_id IS NULL",
                    (connection_id, conversation_id))


# ---------- etiquetas (panel) ----------
_TAG_MAX = 40


def normalize_tag(tag: str) -> str:
    t = " ".join(str(tag or "").strip().lower().split())
    return t[:_TAG_MAX]


def add_tag(conversation_id: str, tag: str, actor: str | None) -> list[str]:
    t = normalize_tag(tag)
    if not t:
        raise ValueError("etiqueta vacía")
    with connect() as con:
        if is_postgres():
            con.execute("INSERT INTO conversation_tags (conversation_id, tag, created_by, created_at) "
                        "VALUES (?,?,?,?) ON CONFLICT DO NOTHING", (conversation_id, t, actor, _now()))
        else:
            con.execute("INSERT OR IGNORE INTO conversation_tags (conversation_id, tag, created_by, created_at) "
                        "VALUES (?,?,?,?)", (conversation_id, t, actor, _now()))
    return tags_for(conversation_id)


def remove_tag(conversation_id: str, tag: str) -> list[str]:
    with connect() as con:
        con.execute("DELETE FROM conversation_tags WHERE conversation_id=? AND tag=?",
                    (conversation_id, normalize_tag(tag)))
    return tags_for(conversation_id)


def tags_for(conversation_id: str) -> list[str]:
    with connect() as con:
        rows = con.execute("SELECT tag FROM conversation_tags WHERE conversation_id=? ORDER BY tag",
                           (conversation_id,)).fetchall()
    return [r["tag"] for r in rows]


def tags_bulk(conversation_ids: list[str]) -> dict[str, list[str]]:
    if not conversation_ids:
        return {}
    out: dict[str, list[str]] = {}
    with connect() as con:
        marks = ",".join("?" for _ in conversation_ids)
        rows = con.execute(f"SELECT conversation_id, tag FROM conversation_tags WHERE conversation_id IN ({marks}) "
                           "ORDER BY tag", tuple(conversation_ids)).fetchall()
    for r in rows:
        out.setdefault(r["conversation_id"], []).append(r["tag"])
    return out


def all_tags() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT tag, COUNT(*) AS n FROM conversation_tags GROUP BY tag ORDER BY n DESC, tag").fetchall()
    return [{"tag": r["tag"], "count": int(r["n"])} for r in rows]


def handoff_load_by_agent(tenant_id: str = "brasper") -> dict[str, int]:
    """Conversaciones en handoff activas por asesor (para asignar al menos cargado)."""
    with connect() as con:
        sql = ("SELECT assigned_to, COUNT(*) AS n FROM conversations "
               "WHERE status='handoff' AND assigned_to IS NOT NULL")
        params: tuple = ()
        if has_column("conversations", "tenant_id"):
            sql += " AND tenant_id=?"
            params = (tenant_id,)
        rows = con.execute(sql + " GROUP BY assigned_to", params).fetchall()
    return {r["assigned_to"]: int(r["n"]) for r in rows}


def list_conversations(tenant_id: str = "brasper", limit: int = 50, assigned_to: str | None = None,
                       include_unassigned: bool = False, status: str | None = None,
                       channel: str | None = None, q: str | None = None,
                       since: str | None = None, before: str | None = None,
                       only_unassigned: bool = False, tag: str | None = None,
                       scope_where: str = "", scope_args: list | None = None) -> list[dict]:
    """Conversaciones del sistema. Si `assigned_to` se da (vista de asesor), filtra a
    las suyas; con `include_unassigned=True` incluye las libres (la cola por reclamar).

    Filtros del panel: `status` (active|handoff|closed), `channel`, `q` (texto en
    user_ref / lead_data / último mensaje), `since` (updated_at > since, polling
    incremental), `before` (updated_at < before, cursor de paginación) y
    `only_unassigned` (cola de libres). Cada fila trae `last_message`, `last_role`,
    `message_count`, `lead_name` y `waiting_since`."""
    if isinstance(tenant_id, int):
        limit, tenant_id = tenant_id, "brasper"
    where = "1=1"
    args: list = []
    if has_column("conversations", "tenant_id"):
        where += " AND c.tenant_id=?"
        args.append(tenant_id)
    if assigned_to is not None:
        if include_unassigned:
            where += " AND (c.assigned_to=? OR c.assigned_to IS NULL)"
        else:
            where += " AND c.assigned_to=?"
        args.append(assigned_to)
    if only_unassigned:
        where += " AND c.assigned_to IS NULL"
    if status:
        where += " AND c.status=?"
        args.append(status)
    if channel:
        where += " AND c.channel=?"
        args.append(channel)
    if since:
        where += " AND c.updated_at>=?"  # inclusivo (resolucion de segundos); el panel fusiona por id
        args.append(str(since))
    if before:
        where += " AND c.updated_at<?"
        args.append(str(before))
    if scope_where:  # alcance del usuario (core.access.sql_filter), siempre parametrizado
        where += scope_where
        args.extend(scope_args or [])
    if tag:
        where += " AND EXISTS (SELECT 1 FROM conversation_tags t WHERE t.conversation_id=c.id AND t.tag=?)"
        args.append(normalize_tag(tag))
    if q:
        like = f"%{q.strip().lower()}%"
        where += (" AND (LOWER(c.user_ref) LIKE ? OR LOWER(COALESCE(c.lead_data,'')) LIKE ? "
                  "OR LOWER(COALESCE((SELECT content FROM messages m WHERE m.conversation_id=c.id "
                  "ORDER BY m.id DESC LIMIT 1),'')) LIKE ?)")
        args.extend([like, like, like])
    args.append(max(1, min(int(limit), 500)))
    with connect() as con:
        rows = con.execute(
            "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id=c.id "
            "ORDER BY m.id DESC LIMIT 1) AS last_message, "
            "(SELECT role FROM messages m WHERE m.conversation_id=c.id "
            "ORDER BY m.id DESC LIMIT 1) AS last_role, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id "
            ") AS message_count "
            f"FROM conversations c WHERE {where} ORDER BY c.updated_at DESC LIMIT ?",
            tuple(args)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("updated_at", "started_at"):
            if d.get(k) is not None and not isinstance(d[k], str):
                d[k] = d[k].isoformat()
        d["lead_name"] = _lead_name(d.get("lead_data"))
        d["waiting_since"] = d.get("updated_at") if d.get("status") == "handoff" else None
        out.append(d)
    tags = tags_bulk([d["id"] for d in out])
    for d in out:
        d["tags"] = tags.get(d["id"], [])
    return out


def _lead_name(raw: Any) -> str | None:
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    name = data.get("nombre") if isinstance(data, dict) else None
    return (str(name).strip() or None) if name else None


# ---------- notas internas (panel) ----------
def add_note(conversation_id: str, author: str | None, text: str) -> dict:
    with connect() as con:
        con.execute(
            "INSERT INTO conversation_notes (conversation_id, author, text, created_at) VALUES (?,?,?,?)",
            (conversation_id, author, text, _now()))
        row = con.execute(
            "SELECT * FROM conversation_notes WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
            (conversation_id,)).fetchone()
    return _rowdict(row)


def list_notes(conversation_id: str, limit: int = 100) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM conversation_notes WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") is not None and not isinstance(d["created_at"], str):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return out


def get_messages(*args, after: str | None = None) -> list[dict]:
    """Mensajes de una conversación en orden. Con `after` (created_at ISO) devuelve
    solo los posteriores: el panel hace append en vez de recargar el hilo."""
    if len(args) == 2:
        tenant_id, conversation_id = args
    elif len(args) == 1:
        tenant_id, conversation_id = "brasper", args[0]
    else:
        raise TypeError("get_messages espera 1 o 2 argumentos")
    with connect() as con:
        sql = ("SELECT role, content, media_json, sender, agent_email, created_at FROM messages "
               "WHERE conversation_id=?")
        params: tuple = (conversation_id,)
        if has_column("messages", "tenant_id"):
            sql += " AND tenant_id=?"
            params += (tenant_id,)
        if after:
            sql += " AND created_at>=?"  # inclusivo: el timestamp es de segundos; el panel deduplica
            params += (str(after),)
        rows = con.execute(sql + " ORDER BY id", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") is not None and not isinstance(d["created_at"], str):
            d["created_at"] = d["created_at"].isoformat()  # Postgres devuelve datetime
        d["sender"] = d.get("sender") or ("user" if d.get("role") == "user" else "bot")
        raw = d.pop("media_json", None)
        if raw:
            try:
                d["media"] = json.loads(raw)
                if isinstance(d["media"], dict):
                    d["media"]["conversation_id"] = conversation_id
            except (ValueError, TypeError):
                d["media"] = None
        out.append(d)
    return out


def delete_conversation(conversation_id: str, expected_user_ref: str) -> dict:
    """Elimina una conversación y sus datos dependientes en una transacción.

    ``expected_user_ref`` es un guard obligatorio para evitar borrar otra
    conversación por copiar un ID incorrecto desde el panel.
    """
    with connect() as con:
        row = con.execute(
            "SELECT id, user_ref, channel FROM conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        if not row:
            raise KeyError(conversation_id)
        conv = _rowdict(row)
        if conv.get("user_ref") != expected_user_ref:
            raise ValueError("user_ref no coincide con la conversación")

        counts: dict[str, int] = {}
        for table in ("messages", "usage_events", "appointments", "quotes"):
            count_row = con.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
            counts[table] = int(count_row["n"] if count_row else 0)
            con.execute(
                f"DELETE FROM {table} WHERE conversation_id=?",
                (conversation_id,),
            )
        con.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return {
        "conversation_id": conversation_id,
        "user_ref": expected_user_ref,
        "channel": conv.get("channel"),
        "deleted": counts,
    }


def add_usage(*args) -> None:
    if len(args) == 7:
        tenant_id, conversation_id, provider, model, tokens_in, tokens_out, cost_usd = args
    elif len(args) == 6:
        tenant_id = "brasper"
        conversation_id, provider, model, tokens_in, tokens_out, cost_usd = args
    else:
        raise TypeError("add_usage espera 6 o 7 argumentos")
    with connect() as con:
        if has_column("usage_events", "tenant_id"):
            con.execute(
                "INSERT INTO usage_events "
                "(tenant_id, conversation_id, provider, model, tokens_in, "
                "tokens_out, cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (tenant_id, conversation_id, provider, model, tokens_in, tokens_out,
                 cost_usd, _now()))
        else:
            con.execute(
                "INSERT INTO usage_events "
                "(conversation_id, provider, model, tokens_in, tokens_out, cost_usd, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (conversation_id, provider, model, tokens_in, tokens_out, cost_usd, _now()))


def _usage_row(row: Any) -> dict:
    d = _rowdict(row)
    d["calls"] = d.get("calls") or 0
    d["tokens_in"] = d.get("tokens_in") or 0
    d["tokens_out"] = d.get("tokens_out") or 0
    d["cost_usd"] = round(float(d.get("cost_usd") or 0), 6)
    return d


def usage_summary(tenant_id: str | None = None) -> list[dict]:
    q = ("SELECT COUNT(*) AS calls, SUM(tokens_in) AS tokens_in, "
         "SUM(tokens_out) AS tokens_out, SUM(cost_usd) AS cost_usd "
         "FROM usage_events")
    args: tuple = ()
    if tenant_id and has_column("usage_events", "tenant_id"):
        q += " WHERE tenant_id=?"
        args = (tenant_id,)
    with connect() as con:
        rows = con.execute(q, args).fetchall()
    return [_usage_row(r) for r in rows]


def usage_events(limit: int = 100) -> list[dict]:
    q = "SELECT * FROM usage_events ORDER BY id DESC LIMIT ?"
    args: list = [limit]
    with connect() as con:
        rows = con.execute(q, args).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["cost_usd"] = float(d.get("cost_usd") or 0)
        out.append(d)
    return out


def add_audit_event(actor: str | None,
                    action: str, resource: str | None = None,
                    metadata: dict | str | None = None) -> None:
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata, ensure_ascii=False)
    with connect() as con:
        if has_column("audit_events", "tenant_id"):
            con.execute(
                "INSERT INTO audit_events "
                "(tenant_id, actor, action, resource, metadata, created_at) "
                "VALUES (?,?,?,?,?,?)",
                ("brasper", actor, action, resource, metadata, _now()))
        else:
            con.execute(
                "INSERT INTO audit_events "
                "(actor, action, resource, metadata, created_at) VALUES (?,?,?,?,?)",
                (actor, action, resource, metadata, _now()))


def create_appointment(conversation_id: str | None, user_ref: str | None,
                       patient_name: str, document_id: str | None, specialty: str,
                       scheduled_for: str, metadata: dict | str | None = None) -> dict:
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata, ensure_ascii=False)
    now = _now()
    with connect() as con:
        con.execute(
            "INSERT INTO appointments (conversation_id, user_ref, patient_name, "
            "document_id, specialty, scheduled_for, status, metadata, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (conversation_id, user_ref, patient_name, document_id, specialty,
             scheduled_for, "scheduled", metadata, now, now))
        row = con.execute(
            "SELECT * FROM appointments ORDER BY id DESC LIMIT ?",
            (1,)).fetchone()
    return _rowdict(row)


def list_appointments(limit: int = 100) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM appointments ORDER BY scheduled_for DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def export_conversations(tenant_id: str = "brasper", limit: int = 500) -> list[dict]:
    """Conversaciones + sus mensajes."""
    out = []
    if isinstance(tenant_id, int):
        limit, tenant_id = tenant_id, "brasper"
    for conv in list_conversations(tenant_id, limit=limit):
        conv = dict(conv)
        conv["messages"] = get_messages(tenant_id, conv["id"])
        out.append(conv)
    return out


def usage_daily(tenant_id: str | None = None) -> list[dict]:
    """Agregación por día calculada en Python."""
    agg: dict[str, dict] = {}
    for r in usage_events(limit=100000):
        if tenant_id and has_column("usage_events", "tenant_id") and r.get("tenant_id") != tenant_id:
            continue
        # created_at es TEXT en SQLite y datetime en Postgres -> str() antes de cortar.
        day = str(r.get("created_at") or "")[:10]
        if not day:
            continue
        key = day
        a = agg.setdefault(key, {"day": day,
                                 "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        a["calls"] += 1
        a["tokens_in"] += int(r.get("tokens_in") or 0)
        a["tokens_out"] += int(r.get("tokens_out") or 0)
        a["cost_usd"] += float(r.get("cost_usd") or 0)
    rows = sorted(agg.values(), key=lambda x: x["day"], reverse=True)
    for a in rows:
        a["cost_usd"] = round(a["cost_usd"], 6)
    return rows


def purge_old_data(cutoff_iso: str) -> dict:
    """Retención: borra conversaciones inactivas desde `cutoff_iso` (+ sus mensajes) y
    los eventos de usage/auditoría anteriores. `cutoff_iso` es un timestamp ISO; la
    comparación funciona igual en SQLite (TEXT) y Postgres (TIMESTAMPTZ)."""
    counts: dict[str, int] = {}
    with connect() as con:
        old = [_rowdict(r)["id"] for r in con.execute(
            "SELECT id FROM conversations WHERE updated_at < ?", (cutoff_iso,)).fetchall()]
        for cid in old:
            con.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        con.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff_iso,))
        counts["conversations"] = len(old)
        for table in ("usage_events", "audit_events"):
            con.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff_iso,))
    return counts


def count_by_tenant(table: str) -> list[dict]:
    if table not in {"conversations", "appointments", "messages"}:
        raise ValueError(f"tabla no permitida: {table}")
    with connect() as con:
        rows = con.execute(
            f"SELECT COUNT(*) AS count FROM {table}"
        ).fetchall()
    return [{"count": int(rows[0]["count"])}] if rows else [{"count": 0}]


def add_secret_rotation(actor: str | None, secret_path: str,
                        env_name: str, note: str | None = None) -> dict:
    with connect() as con:
        con.execute(
            "INSERT INTO secret_rotations (actor, secret_path, env_name, note, rotated_at) "
            "VALUES (?,?,?,?,?)",
            (actor, secret_path, env_name, note, _now()))
        row = con.execute(
            "SELECT * FROM secret_rotations ORDER BY id DESC LIMIT ?",
            (1,)).fetchone()
    return _rowdict(row)


def list_secret_rotations(limit: int = 100) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM secret_rotations ORDER BY rotated_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_or_create_customer(phone_number: str) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM customers WHERE phone_number=?", (phone_number,)).fetchone()
        if row:
            return _rowdict(row)
        now = _now()
        con.execute(
            "INSERT INTO customers (phone_number, created_at) VALUES (?,?)",
            (phone_number, now)
        )
        row = con.execute("SELECT * FROM customers WHERE phone_number=?", (phone_number,)).fetchone()
        return _rowdict(row)


def update_customer(customer_id: int, updates: dict) -> dict:
    if not updates:
        with connect() as con:
            return _rowdict(con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone())
    set_clause = ", ".join(f"{k}=?" for k in updates.keys())
    values = list(updates.values())
    values.append(customer_id)
    with connect() as con:
        con.execute(f"UPDATE customers SET {set_clause} WHERE id=?", tuple(values))
        return _rowdict(con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone())


def create_quote(customer_id: int | None, conversation_id: str | None,
                 from_currency: str, to_currency: str, amount_send: float,
                 amount_receive: float, exchange_rate: float, fee: float) -> dict:
    with connect() as con:
        con.execute(
            "INSERT INTO quotes (customer_id, conversation_id, from_currency, to_currency, "
            "amount_send, amount_receive, exchange_rate, fee, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (customer_id, conversation_id, from_currency, to_currency, amount_send,
             amount_receive, exchange_rate, fee, _now()))
        row = con.execute("SELECT * FROM quotes ORDER BY id DESC LIMIT ?", (1,)).fetchone()
    return _rowdict(row)
