"""Persistencia multi-tenant.

Produccion usa Postgres via DATABASE_URL. SQLite queda como fallback local y
para pruebas sin servicios externos.
"""
import os
import json
import sqlite3
import uuid
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


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
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
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  media_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS usage_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  media_json TEXT,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS usage_events (
  id BIGSERIAL PRIMARY KEY,
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


def _ensure_columns() -> None:
    """Columnas añadidas después del CREATE inicial (bases ya existentes).

    CREATE IF NOT EXISTS no altera tablas viejas; esto aplica el ALTER de forma
    idempotente (equivalente runtime de la migración 0004).
    """
    for ddl in ("ALTER TABLE conversations ADD COLUMN assigned_to TEXT",
                "ALTER TABLE messages ADD COLUMN media_json TEXT",
                "ALTER TABLE conversations ADD COLUMN lead_data TEXT",
                "ALTER TABLE conversations ADD COLUMN customer_id INTEGER"):
        try:
            with connect() as con:
                con.execute(ddl)
        except Exception:  # noqa: BLE001 - la columna ya existe
            pass


def ping() -> bool:
    try:
        with connect() as con:
            con.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def _rowdict(row: Any) -> dict:
    return dict(row) if row is not None else {}


def get_or_create_conversation(user_ref: str, channel: str,
                               conversation_id: str | None = None) -> str:
    with connect() as con:
        if conversation_id:
            row = con.execute(
                "SELECT id FROM conversations WHERE id=?",
                (conversation_id,)).fetchone()
            if row:
                return row["id"]
        # Reutiliza la conversación en curso (activa O en handoff): así los mensajes
        # que llegan mientras un asesor atiende NO abren una conversación nueva ni
        # reactivan al bot. Solo 'closed' inicia una conversación fresca.
        row = con.execute(
            "SELECT id FROM conversations WHERE user_ref=? AND channel=? "
            "AND status!='closed' ORDER BY updated_at DESC LIMIT ?",
            (user_ref, channel, 1)).fetchone()
        if row and not conversation_id:
            return row["id"]
        cid = conversation_id or uuid.uuid4().hex[:12]
        con.execute(
            "INSERT INTO conversations (id, channel, user_ref, started_at, updated_at) "
            "VALUES (?,?,?,?,?)", (cid, channel, user_ref, _now(), _now()))
        return cid


def add_message(conversation_id: str, role: str, content: str,
                media: dict | None = None) -> None:
    media_json = json.dumps(media, ensure_ascii=False) if media else None
    with connect() as con:
        con.execute(
            "INSERT INTO messages (conversation_id, role, content, media_json, created_at) "
            "VALUES (?,?,?,?,?)", (conversation_id, role, content, media_json, _now()))
        con.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (_now(), conversation_id))


def get_history(conversation_id: str, limit: int = 12) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? "
            "ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def set_conversation_status(conversation_id: str, status: str) -> None:
    with connect() as con:
        con.execute("UPDATE conversations SET status=?, updated_at=? WHERE id=?",
                    (status, _now(), conversation_id))


def get_conversation(conversation_id: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM conversations WHERE id=?",
                          (conversation_id,)).fetchone()
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


def is_first_contact(user_ref: str) -> bool:
    """True si este user_ref aún no tiene ningún mensaje suyo (lead nuevo).
    Llamar ANTES de guardar el mensaje entrante."""
    with connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM messages m "
            "JOIN conversations c ON m.conversation_id=c.id "
            "WHERE c.user_ref=? AND m.role='user'",
            (user_ref,)).fetchone()
    n = row["n"] if not isinstance(row, tuple) else row[0]
    return int(n or 0) == 0


def get_lead_data(conversation_id: str) -> dict:
    conv = get_conversation(conversation_id)
    return conv.get("lead_data", {}) if conv else {}


def merge_lead_data(conversation_id: str, updates: dict) -> dict:
    """Fusiona campos del lead (idioma, ruta, monto, KYC…) sin pisar lo ya guardado
    con valores vacíos. Devuelve el lead_data resultante."""
    if not updates:
        return get_lead_data(conversation_id)
    current = get_lead_data(conversation_id)
    for k, v in updates.items():
        if v is not None and v != "":
            current[k] = v
    with connect() as con:
        con.execute("UPDATE conversations SET lead_data=?, updated_at=? WHERE id=?",
                    (json.dumps(current, ensure_ascii=False), _now(), conversation_id))
    return current


def conversation_status(conversation_id: str) -> str | None:
    conv = get_conversation(conversation_id)
    return conv.get("status") if conv else None


def assign_conversation(conversation_id: str, email: str | None) -> None:
    """Deriva la conversación a un asesor del panel (o None para desasignar)."""
    with connect() as con:
        con.execute("UPDATE conversations SET assigned_to=?, updated_at=? WHERE id=?",
                    (email, _now(), conversation_id))


def handoff_load_by_agent() -> dict[str, int]:
    """Conversaciones en handoff activas por asesor (para asignar al menos cargado)."""
    with connect() as con:
        rows = con.execute(
            "SELECT assigned_to, COUNT(*) AS n FROM conversations "
            "WHERE status='handoff' AND assigned_to IS NOT NULL "
            "GROUP BY assigned_to").fetchall()
    return {r["assigned_to"]: int(r["n"]) for r in rows}


def list_conversations(limit: int = 50, assigned_to: str | None = None,
                       include_unassigned: bool = False) -> list[dict]:
    """Conversaciones del sistema. Si `assigned_to` se da (vista de asesor), filtra a
    las suyas; con `include_unassigned=True` incluye las libres (la cola por reclamar)."""
    where = "1=1"
    args: list = []
    if assigned_to is not None:
        if include_unassigned:
            where += " AND (c.assigned_to=? OR c.assigned_to IS NULL)"
        else:
            where += " AND c.assigned_to=?"
        args.append(assigned_to)
    args.append(limit)
    with connect() as con:
        rows = con.execute(
            "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id=c.id "
            "ORDER BY m.id DESC LIMIT 1) AS last_message, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id "
            ") AS message_count "
            f"FROM conversations c WHERE {where} ORDER BY c.updated_at DESC LIMIT ?",
            tuple(args)).fetchall()
    return [dict(r) for r in rows]


def get_messages(conversation_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT role, content, media_json, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY id",
            (conversation_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        raw = d.pop("media_json", None)
        if raw:
            try:
                d["media"] = json.loads(raw)
            except (ValueError, TypeError):
                d["media"] = None
        out.append(d)
    return out


def add_usage(conversation_id: str | None, provider: str, model: str,
              tokens_in: int, tokens_out: int, cost_usd: float) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO usage_events (conversation_id, provider, model, tokens_in, "
            "tokens_out, cost_usd, created_at) VALUES (?,?,?,?,?,?,?)",
            (conversation_id, provider, model, tokens_in, tokens_out, cost_usd, _now()))


def _usage_row(row: Any) -> dict:
    d = _rowdict(row)
    d["calls"] = d.get("calls") or 0
    d["tokens_in"] = d.get("tokens_in") or 0
    d["tokens_out"] = d.get("tokens_out") or 0
    d["cost_usd"] = round(float(d.get("cost_usd") or 0), 6)
    return d


def usage_summary() -> list[dict]:
    q = ("SELECT COUNT(*) AS calls, SUM(tokens_in) AS tokens_in, "
         "SUM(tokens_out) AS tokens_out, SUM(cost_usd) AS cost_usd "
         "FROM usage_events")
    args: tuple = ()
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
        con.execute(
            "INSERT INTO audit_events (actor, action, resource, metadata, created_at) "
            "VALUES (?,?,?,?,?)",
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


def export_conversations(limit: int = 500) -> list[dict]:
    """Conversaciones + sus mensajes."""
    out = []
    for conv in list_conversations(limit=limit):
        conv = dict(conv)
        conv["messages"] = get_messages(conv["id"])
        out.append(conv)
    return out


def usage_daily() -> list[dict]:
    """Agregación por día calculada en Python."""
    agg: dict[str, dict] = {}
    for r in usage_events(limit=100000):
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
