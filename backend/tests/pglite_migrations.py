"""Laboratorio: migraciones Alembic del bot contra PostgreSQL real (PGlite WASM) vía asyncpg.

Herramienta SOLO para validación local en máquinas donde psycopg / PostgreSQL nativo
están bloqueados (Windows con App Control). No es parte del runtime ni de CI.

  * NO usa ``migrations/env.py`` (que lee ``.env`` y ``DATABASE_URL``): construye el
    ``EnvironmentContext`` de Alembic en memoria con una conexión síncrona obtenida
    con ``AsyncConnection.run_sync`` sobre asyncpg, y ejecuta las MISMAS revisiones de
    ``backend/migrations/versions``.
  * NO lee variables de entorno ni ``.env``. Rechaza cualquier host distinto de
    127.0.0.1/localhost y bases que no empiecen por ``postgres`` o ``brasper_test``.
  * El drill BORRA el esquema ``public`` de la base indicada entre escenarios.

Servidor (una sola sesión de backend; una conexión a la vez)::

    node <pglite>/node_modules/@electric-sql/pglite-socket/dist/scripts/server.js \
        --db=memory:// --port=55440

Uso (con un intérprete que tenga sqlalchemy + alembic + asyncpg)::

    python tests/pglite_migrations.py --port 55440 drill --out evidencia.json
    python tests/pglite_migrations.py --port 55440 upgrade head
    python tests/pglite_migrations.py --port 55440 current

Limitaciones: PGlite es PostgreSQL 18 compilado a WASM con UNA sesión compartida; no
prueba concurrencia real (locks entre sesiones) ni el driver psycopg del runtime.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND / "migrations"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_DB_PREFIXES = ("postgres", "brasper_test")
PRE_REV = "0006_lead_data"
HEAD = "0010_contacts_identity_links"


# ------------------------------------------------------------------ guardas
def guard(host: str, db: str) -> None:
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"Rechazado: host {host!r} no es local (solo 127.0.0.1/localhost).")
    if not db.startswith(ALLOWED_DB_PREFIXES):
        raise SystemExit(f"Rechazado: base {db!r} no empieza por postgres/brasper_test.")


async def raw_connect(args) -> asyncpg.Connection:
    guard(args.host, args.db)
    # Credenciales fijas del servidor PGlite local (no hay secretos reales).
    return await retry_connect(lambda: asyncpg.connect(
        host=args.host, port=args.port, user="postgres", password="postgres",
        database=args.db, ssl=False, statement_cache_size=0, timeout=15))


async def retry_connect(factory, attempts: int = 40):
    """PGlite acepta UN cliente: tras cerrar el anterior el servidor tarda en liberarlo."""
    for i in range(attempts):
        try:
            return await factory()
        except (asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionError, OSError):
            if i == attempts - 1:
                raise
            await asyncio.sleep(0.25)
        except Exception as exc:  # noqa: BLE001 - SQLAlchemy envuelve el error de asyncpg
            if "closed in the middle" not in str(exc) or i == attempts - 1:
                raise
            await asyncio.sleep(0.25)


def describe_error(exc: BaseException) -> str:
    """Primer error de PostgreSQL de la cadena (SQLAlchemy a veces falla al formatear el
    error de asyncpg que viene de PGlite y deja un AttributeError encima)."""
    seen, queue = set(), [exc]
    while queue:
        cur = queue.pop(0)
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, asyncpg.PostgresError):
            detail = getattr(cur, "detail", None)
            note = "" if cur is exc else f" (error superficial: {type(exc).__name__}: {exc})"
            return (f"{type(cur).__name__} [{cur.sqlstate}]: {cur.args[0] if cur.args else cur}"
                    + (f" | {detail}" if detail else "") + note)
        queue += [getattr(cur, "orig", None), cur.__cause__, cur.__context__]
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:300] if str(exc) else ''}"


async def raw_close(con: asyncpg.Connection) -> None:
    # Con PGlite close() puede colgar: se intenta un cierre ordenado acotado y luego terminate.
    try:
        await asyncio.wait_for(con.close(), timeout=2)
    except BaseException:  # noqa: BLE001
        try:
            con.terminate()
        except BaseException:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ alembic
def _alembic_cfg() -> tuple[Config, ScriptDirectory]:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("path_separator", "os")
    return cfg, ScriptDirectory.from_config(cfg)


def _run_alembic_sync(sync_conn, action: str, rev: str, first_error: list | None = None) -> None:
    """Equivalente a ``command.upgrade/downgrade`` sin ejecutar ``migrations/env.py``.

    Mismo modo que el env de producción: ``target_metadata=None`` y una transacción
    para toda la corrida (``context.begin_transaction``)."""
    cfg, script = _alembic_cfg()

    def fn(current, context):
        if action == "upgrade":
            return script._upgrade_revs(rev, current)
        if action == "downgrade":
            return script._downgrade_revs(rev, current)
        return []

    with EnvironmentContext(cfg, script, fn=fn, as_sql=False, starting_rev=None,
                            destination_rev=rev if action != "current" else None) as ctx:
        ctx.configure(connection=sync_conn, target_metadata=None)
        with ctx.begin_transaction():
            try:
                ctx.run_migrations()
            except Exception as exc:
                # El ROLLBACK posterior puede fallar en PGlite (CommandComplete sin tag ->
                # AttributeError en asyncpg) y tapar el error real: se guarda el original.
                if first_error is not None:
                    first_error.append(exc)
                raise


async def alembic(args, action: str, rev: str) -> dict:
    guard(args.host, args.db)
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{args.host}:{args.port}/{args.db}"
        "?prepared_statement_cache_size=0",
        poolclass=NullPool, connect_args={"ssl": False, "statement_cache_size": 0})
    conn = await retry_connect(engine.connect)
    out = {"action": action, "target": rev, "ok": True, "error": None}
    first_error: list = []
    try:
        try:
            await conn.run_sync(_run_alembic_sync, action, rev, first_error)
            await conn.commit()
        except Exception as exc:  # noqa: BLE001 - se reporta como evidencia
            out.update(ok=False, error=describe_error(first_error[0] if first_error else exc))
            if first_error and first_error[0] is not exc:
                out["secondary_error"] = f"{type(exc).__name__}: {exc}"
            try:
                await conn.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            await asyncio.wait_for(conn.close(), timeout=2)
        except BaseException:  # noqa: BLE001
            try:
                raw = await conn.get_raw_connection()
                raw.driver_connection.terminate()
                await conn.invalidate()
            except BaseException:  # noqa: BLE001
                pass
        await engine.dispose()
    con = await raw_connect(args)
    try:
        out["alembic_version"] = await _version(con)
    finally:
        await raw_close(con)
    return out


async def _version(con) -> list[str]:
    if not await con.fetchval("SELECT to_regclass('public.alembic_version')"):
        return []
    return [r[0] for r in await con.fetch("SELECT version_num FROM public.alembic_version")]


# ------------------------------------------------------------------ huellas
FINGERPRINT_SQL = {
    "columns": """SELECT table_name||'.'||column_name||':'||data_type||':'||is_nullable||':'||
                  coalesce(column_default,'') FROM information_schema.columns
                  WHERE table_schema='public' ORDER BY 1""",
    "indexes": "SELECT indexname||' '||indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1",
    "constraints": """SELECT c.conrelid::regclass::text||'.'||c.conname||' '||pg_get_constraintdef(c.oid)
                      FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
                      WHERE n.nspname='public' ORDER BY 1""",
}


async def fingerprint(con) -> dict:
    out = {}
    for key, sql in FINGERPRINT_SQL.items():
        rows = [r[0] for r in await con.fetch(sql)]
        out[key] = rows
        out[key + "_md5"] = hashlib.md5("\n".join(rows).encode()).hexdigest()
    return out


async def tables(con) -> list[str]:
    return [r[0] for r in await con.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")]


async def columns(con, table: str) -> list[str]:
    return [r[0] for r in await con.fetch(
        "SELECT attname FROM pg_attribute WHERE attrelid=$1::regclass AND attnum>0 AND NOT attisdropped "
        "ORDER BY attnum", table)]


async def checksum(con, table: str, cols: list[str]) -> dict:
    proj = ", ".join('"' + c + '"' for c in cols)
    row = await con.fetchrow(
        f"SELECT count(*) AS n, md5(coalesce(string_agg(j, E'\\n' ORDER BY j), '')) AS md5 "
        f"FROM (SELECT row_to_json(t)::text AS j FROM (SELECT {proj} FROM {table}) t) s")
    return {"rows": row["n"], "md5": row["md5"]}


# Columnas eliminadas a propósito por 0007 (single-tenant) y tablas borradas por diseño.
DROPPED_BY_DESIGN_COLUMNS = {"tenant_id", "tenant_scope"}
DROPPED_BY_DESIGN_TABLES = {"tenants", "channel_configs", "connector_configs"}


async def data_snapshot(con) -> dict:
    snap = {}
    for t in await tables(con):
        if t == "alembic_version":
            continue
        cols = [c for c in await columns(con, t) if c not in DROPPED_BY_DESIGN_COLUMNS]
        snap[t] = {"columns": cols, **await checksum(con, t, cols)}
    return snap


async def compare_on_base_columns(con, base: dict) -> dict:
    res = {}
    present = set(await tables(con))
    for t, meta in base.items():
        if t in DROPPED_BY_DESIGN_TABLES:
            res[t] = {"expected_dropped": True, "dropped": t not in present}
            continue
        if t not in present:
            res[t] = {"missing": True, "equal": False}
            continue
        now = await checksum(con, t, meta["columns"])
        res[t] = {"base": {"rows": meta["rows"], "md5": meta["md5"]}, "now": now,
                  "equal": now == {"rows": meta["rows"], "md5": meta["md5"]}}
    return res


# ------------------------------------------------------------------ semilla
TS = "2026-07-20T10:00:00+00:00"


async def reset(con) -> None:
    await con.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


async def seed_historical(con, *, dup_public_doc: bool = False, dup_conversation_id: bool = False) -> None:
    """Datos sintéticos en 0006 + artefactos que creaba el runtime del commit 539bc5d
    (``init_db``/``_ensure_columns``/``public_docs.ensure_schema``) ANTES de existir 0009:
    columnas ``connection_id``/``sender``/``agent_email``, tablas ``public_documents`` (sin
    índice único), ``deletion_requests``, ``idempotency_keys``, ``agent_presence``,
    ``conversation_notes``, ``conversation_tags``."""
    async with con.transaction():
        # --- esquema runtime de 539bc5d (no lo crean las migraciones 0001-0008)
        await con.execute("ALTER TABLE conversations ADD COLUMN connection_id TEXT")
        await con.execute("ALTER TABLE messages ADD COLUMN sender TEXT")
        await con.execute("ALTER TABLE messages ADD COLUMN agent_email TEXT")
        await con.execute(
            "CREATE TABLE IF NOT EXISTS public_documents (id SERIAL PRIMARY KEY, slug TEXT NOT NULL, lang TEXT "
            "NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL, body_md TEXT NOT NULL, status TEXT NOT NULL, "
            "author TEXT, created_at TEXT NOT NULL, published_at TEXT, published_by TEXT)")
        await con.execute(
            "CREATE TABLE IF NOT EXISTS deletion_requests (id SERIAL PRIMARY KEY, contact TEXT NOT NULL, channel "
            "TEXT, detail TEXT, status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT "
            "NOT NULL, handled_by TEXT, note TEXT)")
        await con.execute("CREATE TABLE IF NOT EXISTS idempotency_keys (key TEXT PRIMARY KEY, scope TEXT NOT NULL, "
                          "result TEXT, created_at TEXT NOT NULL)")
        await con.execute("CREATE TABLE IF NOT EXISTS agent_presence (email TEXT PRIMARY KEY, status TEXT NOT NULL, "
                          "last_seen TEXT NOT NULL, updated_at TEXT NOT NULL)")
        await con.execute("CREATE TABLE IF NOT EXISTS conversation_notes (id SERIAL PRIMARY KEY, conversation_id "
                          "TEXT NOT NULL, author TEXT, text TEXT NOT NULL, created_at TEXT NOT NULL)")
        await con.execute("CREATE TABLE IF NOT EXISTS conversation_tags (conversation_id TEXT NOT NULL, tag TEXT NOT "
                          "NULL, created_by TEXT, created_at TEXT NOT NULL, PRIMARY KEY (conversation_id, tag))")

        # --- datos históricos
        await con.execute("INSERT INTO panel_users(email,name,role,tenant_scope,token) VALUES "
                          "('admin@lab.test','Admin','admin','brasper','tok-lab-1'),"
                          "('asesor@lab.test','Asesora','advisor','brasper','tok-lab-2')")
        await con.execute("INSERT INTO tenants(id,name,vertical,created_at,updated_at) "
                          "VALUES ('brasper','Brasper','remesas',now(),now())")
        convs = [
            ("c-active01", "whatsapp", "wa:51987654321", "active", None, '{"lang":"es","route":"PEN-BRL"}', "pnid-1"),
            ("c-handoff1", "whatsapp", "wa:5511987654321", "handoff", "asesor@lab.test",
             '{"lang":"pt","amount":"1500","kyc":{"doc":"CPF"}}', "pnid-2"),
            ("c-closed01", "telegram", "tg:123456789", "closed", "asesor@lab.test", '{"lang":"es"}', None),
            ("c-closed02", "whatsapp", "wa:51987654321", "closed", None, None, "pnid-1"),
            ("c-webchat1", "webchat", "webchat:abc123def456ghi789", "active", None, '{"nota":"acentos ñ ç ã"}', None),
        ]
        for i, (cid, ch, ref, st, adv, lead, conn) in enumerate(convs):
            await con.execute(
                "INSERT INTO conversations(id,tenant_id,channel,user_ref,status,started_at,updated_at,assigned_to,"
                "lead_data,connection_id) VALUES ($1,'brasper',$2,$3,$4,$5,$5,$6,$7,$8)",
                cid, ch, ref, st, datetime(2026, 7, 1 + i, 12, tzinfo=timezone.utc), adv, lead, conn)
        if dup_conversation_id:
            # Mismo id en otro tenant (posible solo en el esquema multi-tenant de 0001).
            await con.execute(
                "INSERT INTO conversations(id,tenant_id,channel,user_ref,status,started_at,updated_at) "
                "VALUES ('c-active01','clinica_demo','webchat','u-x','active',now(),now())")
        for cid, *_ in convs:
            for j, (role, sender) in enumerate((("user", None), ("assistant", "bot"), ("assistant", "agent"))):
                await con.execute(
                    "INSERT INTO messages(conversation_id,tenant_id,role,content,created_at,media_json,sender,"
                    "agent_email) VALUES ($1,'brasper',$2,$3,now(),$4,$5,$6)",
                    cid, role, f"msg {j} de {cid} — cotización 1.500,00 BRL", (
                        '{"type":"image","id":"m-1"}' if j == 0 and cid == "c-handoff1" else None),
                    sender, "asesor@lab.test" if sender == "agent" else None)
        await con.execute("INSERT INTO usage_events(tenant_id,conversation_id,provider,model,tokens_in,tokens_out,"
                          "cost_usd,created_at) VALUES ('brasper','c-active01','deepseek','deepseek-chat',120,80,"
                          "0.00012345,now())")
        await con.execute("INSERT INTO audit_events(tenant_id,actor,action,resource,metadata,created_at) VALUES "
                          "('brasper','admin@lab.test','handoff','c-handoff1','{\"to\":\"asesor@lab.test\"}'::jsonb,"
                          "now())")
        await con.execute("INSERT INTO appointments(tenant_id,patient_name,specialty,scheduled_for,created_at,"
                          "updated_at) VALUES ('brasper','legacy','n/a',now(),now(),now())")
        await con.execute("INSERT INTO secret_rotations(tenant_id,actor,secret_path,env_name,rotated_at) VALUES "
                          "('brasper','admin@lab.test','whatsapp.token','WHATSAPP_TOKEN',now())")
        # Historial de documentos públicos (create_draft de 539bc5d: MAX(version)+1 sin lock).
        docs = [("privacidad", "es", 1, "archived"), ("privacidad", "es", 2, "published"),
                ("privacidad", "es", 3, "draft"), ("terminos", "es", 1, "published"),
                ("terminos", "pt", 1, "draft")]
        if dup_public_doc:
            docs.append(("privacidad", "es", 3, "draft"))  # carrera de dos create_draft simultáneos
        for slug, lang, ver, st in docs:
            await con.execute(
                "INSERT INTO public_documents(slug,lang,version,title,body_md,status,author,created_at) "
                "VALUES ($1,$2,$3,$4,$5,$6,'admin@lab.test',$7)", slug, lang, ver, f"{slug} v{ver}", "# texto", st, TS)
        await con.execute("INSERT INTO deletion_requests(contact,channel,detail,created_at,updated_at) "
                          "VALUES ('+51987654321','whatsapp','borrar mis datos',$1,$1)", TS)
        await con.execute("INSERT INTO idempotency_keys VALUES ('wa:wamid.1','webhook',NULL,$1)", TS)
        await con.execute("INSERT INTO agent_presence VALUES ('asesor@lab.test','online',$1,$1)", TS)
        await con.execute("INSERT INTO conversation_notes(conversation_id,author,text,created_at) "
                          "VALUES ('c-handoff1','asesor@lab.test','cliente pide llamada',$1)", TS)
        await con.execute("INSERT INTO conversation_tags VALUES ('c-handoff1','vip','asesor@lab.test',$1)", TS)


# ------------------------------------------------------------------ verificación de head
EXPECTED_TABLES = ["contacts", "contact_aliases", "contact_conflicts", "identity_grants", "conversation_locks",
                   "idempotency_keys", "agent_presence", "public_documents", "deletion_requests",
                   "public_document_heads", "agent_profiles", "agent_profile_versions", "media_library",
                   "media_library_versions", "engagement_settings", "engagement_jobs", "satisfaction",
                   "channel_receipts", "customers", "quotes", "outbound_messages", "channel_events"]
EXPECTED_COLUMNS = {("conversations", "contact_id"), ("conversations", "human_revision"),
                    ("conversations", "connection_id"), ("conversations", "lead_data"),
                    ("conversations", "assigned_to"), ("conversations", "customer_id"),
                    ("messages", "media_json")}
EXPECTED_INDEXES = ["public_documents_version", "contacts_phone", "contact_aliases_contact", "engagement_jobs_due",
                    "contact_aliases_pkey", "conversation_locks_pkey", "identity_grants_pkey",
                    "public_document_heads_pkey", "engagement_jobs_conversation_id_revision_kind_sequence_key",
                    "conversations_pkey", "outbound_provider", "outbound_inflight", "channel_events_state",
                    "outbound_messages_pkey", "channel_events_pkey"]


async def verify_head(con) -> dict:
    present = set(await tables(con))
    cols = {(r[0], r[1]) for r in await con.fetch(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'")}
    idx = {r[0]: r[1] for r in await con.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'")}
    hr = await con.fetchrow("SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                            "WHERE table_name='conversations' AND column_name='human_revision'")
    out = {
        "missing_tables": [t for t in EXPECTED_TABLES if t not in present],
        "dropped_by_design_absent": sorted(DROPPED_BY_DESIGN_TABLES - present) == sorted(DROPPED_BY_DESIGN_TABLES),
        "missing_columns": sorted(f"{t}.{c}" for t, c in EXPECTED_COLUMNS - cols),
        # 0007 solo quita tenant_id de estas tablas; appointments/secret_rotations lo conservan (ver hallazgo).
        "tenant_id_left": sorted(f"{t}.{c}" for t, c in cols if c in DROPPED_BY_DESIGN_COLUMNS
                                and t in {"conversations", "messages", "usage_events", "audit_events",
                                          "panel_users"}),
        "tenant_id_residual_other_tables": sorted(f"{t}.{c}" for t, c in cols if c in DROPPED_BY_DESIGN_COLUMNS
                                                 and t not in {"conversations", "messages", "usage_events",
                                                               "audit_events", "panel_users"}),
        "missing_indexes": [i for i in EXPECTED_INDEXES if i not in idx],
        "public_documents_version_unique": "UNIQUE" in idx.get("public_documents_version", ""),
        "human_revision": dict(hr) if hr else None,
        "human_revision_values": [r[0] for r in await con.fetch(
            "SELECT DISTINCT human_revision FROM conversations ORDER BY 1")],
        "contact_id_nulls": await con.fetchval("SELECT count(*) FROM conversations WHERE contact_id IS NULL"),
        "connection_id_values": {r[0]: r[1] for r in await con.fetch(
            "SELECT id, connection_id FROM conversations ORDER BY id")},
        "conversation_status": {r[0]: r[1] for r in await con.fetch(
            "SELECT status, count(*) FROM conversations GROUP BY status ORDER BY 1")},
        "public_document_heads": [dict(r) for r in await con.fetch(
            "SELECT slug, lang, version FROM public_document_heads ORDER BY 1,2")],
        "engagement_settings": [dict(r) for r in await con.fetch("SELECT id, version FROM engagement_settings")],
        "engagement_settings_payload_is_json": await con.fetchval(
            "SELECT (payload::jsonb ->> 'timezone') FROM engagement_settings WHERE id=1"),
        "lead_data_json_ok": await con.fetchval(
            "SELECT count(*) FROM conversations WHERE lead_data IS NOT NULL AND (lead_data::jsonb) IS NOT NULL"),
    }
    out["ok"] = (not out["missing_tables"] and not out["missing_columns"] and not out["missing_indexes"]
                 and not out["tenant_id_left"] and out["dropped_by_design_absent"]
                 and out["public_documents_version_unique"] and out["human_revision_values"] == [0]
                 and hr is not None and hr["is_nullable"] == "NO")
    return out


# ------------------------------------------------------------------ SQL runtime
_Q = re.compile(r"\?")


def qmark_to_dollar(sql: str) -> str:
    """Equivalente asyncpg de ``db._qmark_to_pg`` (que usa %s para psycopg)."""
    n = 0

    def rep(_):
        nonlocal n
        n += 1
        return f"${n}"
    return _Q.sub(rep, sql)


def affected(status: str) -> int:
    """'INSERT 0 1' / 'UPDATE 1' / 'DELETE 0' -> filas afectadas (rowcount de psycopg)."""
    return int(status.rsplit(" ", 1)[-1])


async def runtime_sql(con) -> dict:
    """Ejecuta, sobre la BD migrada, el SQL literal de contacts.py, db_lock.py,
    identity_link.py, public_docs.ensure_schema y db._creation_lock."""
    res: dict = {}
    sql_log: list[dict] = []

    async def ex(label, sql, *params):
        try:
            status = await con.execute(qmark_to_dollar(sql), *params)
            sql_log.append({"label": label, "ok": True, "status": status})
            return status
        except Exception as exc:  # noqa: BLE001
            sql_log.append({"label": label, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            raise

    async def fetch(label, sql, *params):
        try:
            rows = await con.fetch(qmark_to_dollar(sql), *params)
            sql_log.append({"label": label, "ok": True, "rows": len(rows)})
            return rows
        except Exception as exc:  # noqa: BLE001
            sql_log.append({"label": label, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            raise

    now = datetime.now(timezone.utc).isoformat()

    # --- ensure_schema de runtime sobre la BD ya migrada (deben ser no-op)
    for label, sql in [
        ("contacts.ensure_schema.contacts", "CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, display_name "
         "TEXT, phone_e164 TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"),
        ("contacts.ensure_schema.idx", "CREATE INDEX IF NOT EXISTS contacts_phone ON contacts(phone_e164)"),
        ("contacts.ensure_schema.aliases", "CREATE TABLE IF NOT EXISTS contact_aliases (provider TEXT NOT NULL, "
         "connection_id TEXT NOT NULL DEFAULT '', external_id TEXT NOT NULL, kind TEXT NOT NULL, "
         "contact_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(provider, connection_id, external_id))"),
        ("db_lock.ensure_schema", "CREATE TABLE IF NOT EXISTS conversation_locks (name TEXT PRIMARY KEY, token TEXT "
         "NOT NULL, expires_at TEXT NOT NULL)"),
        ("identity_link.ensure_schema", "CREATE TABLE IF NOT EXISTS identity_grants (conversation_id TEXT PRIMARY "
         "KEY, channel TEXT NOT NULL, subject_hash TEXT NOT NULL, brasper_user_id TEXT NOT NULL, grant_ciphertext "
         "TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)"),
        ("public_docs.ensure_schema.unique", "CREATE UNIQUE INDEX IF NOT EXISTS public_documents_version ON "
         "public_documents(slug,lang,version)"),
        ("public_docs.ensure_schema.heads", "INSERT INTO public_document_heads(slug,lang,version) SELECT slug,lang,"
         "MAX(version) FROM public_documents GROUP BY slug,lang ON CONFLICT(slug,lang) DO NOTHING"),
    ]:
        await ex(label, sql)

    # --- contacts.py
    alias_ins = ("INSERT INTO contact_aliases VALUES (?,?,?,?,?,?) "
                 "ON CONFLICT(provider, connection_id, external_id) DO NOTHING")
    s1 = await ex("contacts.resolve.alias_insert(new)", alias_ins, "whatsapp", "pnid-1", "51987654321", "phone",
                  "ct-1", now)
    s2 = await ex("contacts.resolve.alias_insert(dup)", alias_ins, "whatsapp", "pnid-1", "51987654321", "phone",
                  "ct-OTHER", now)
    await ex("contacts.resolve.contact_insert", "INSERT INTO contacts VALUES (?,?,?,?,?)",
             "ct-1", "Cliente Lab", "+51987654321", now, now)
    alias = await fetch("contacts._alias", "SELECT contact_id FROM contact_aliases WHERE provider=? AND "
                        "connection_id=? AND external_id=?", "whatsapp", "pnid-1", "51987654321")
    await fetch("contacts.resolve.by_phone", "SELECT id FROM contacts WHERE phone_e164=? ORDER BY created_at LIMIT 1",
                "+51987654321")
    await ex("contacts.resolve.phone_update", "UPDATE contacts SET phone_e164=?, updated_at=? WHERE id=? AND "
             "phone_e164 IS NULL", "+51987654321", now, "ct-1")
    await fetch("contacts._conflict.dup", "SELECT 1 FROM contact_conflicts WHERE provider=? AND connection_id=? AND "
                "external_id=? AND existing_contact_id=? AND proposed_contact_id=? AND resolved_at IS NULL",
                "whatsapp", "pnid-2", "51987654321", "ct-1", "ct-2")
    s3 = await ex("contacts._conflict.insert", "INSERT INTO contact_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
                  "cf-1", "whatsapp", "pnid-2", "51987654321", "ct-1", "ct-2", "phone_matches_other_contact", now)
    s4 = await ex("contacts.attach", "UPDATE conversations SET contact_id=? WHERE id=? AND contact_id IS NULL",
                  "ct-1", "c-active01")
    s5 = await ex("contacts.attach(again)", "UPDATE conversations SET contact_id=? WHERE id=? AND contact_id IS NULL",
                  "ct-OTHER", "c-active01")
    await fetch("contacts.backfill", "SELECT id, channel, user_ref, connection_id FROM conversations WHERE "
                "contact_id IS NULL ORDER BY started_at LIMIT ?", 5000)
    await fetch("contacts.conflicts", "SELECT * FROM contact_conflicts WHERE resolved_at IS NULL ORDER BY "
                "created_at DESC LIMIT 200")
    s6 = await ex("contacts.resolve_conflict", "UPDATE contact_conflicts SET resolved_at=?, resolved_by=? WHERE id=? "
                  "AND resolved_at IS NULL", now, "admin@lab.test", "cf-1")
    res["contacts"] = {
        "alias_insert_new_rowcount": affected(s1), "alias_insert_dup_rowcount": affected(s2),
        "alias_kept_first_contact": alias[0]["contact_id"] == "ct-1",
        "conflict_insert_rowcount": affected(s3), "attach_rowcount": affected(s4),
        "attach_again_rowcount": affected(s5), "resolve_conflict_rowcount": affected(s6),
    }
    res["contacts"]["ok"] = (res["contacts"]["alias_insert_new_rowcount"] == 1
                             and res["contacts"]["alias_insert_dup_rowcount"] == 0
                             and res["contacts"]["alias_kept_first_contact"]
                             and affected(s3) == 1 and affected(s4) == 1 and affected(s5) == 0 and affected(s6) == 1)

    # --- db_lock.py
    lock_sql = ("INSERT INTO conversation_locks(name, token, expires_at) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET token=excluded.token, expires_at=excluded.expires_at "
                "WHERE conversation_locks.expires_at < ?")
    t0 = datetime.now(timezone.utc)
    exp0 = (t0 + timedelta(seconds=30)).isoformat()
    a = await ex("db_lock.acquire(free)", lock_sql, "conv:c-active01", "tok-A", exp0, t0.isoformat())
    b = await ex("db_lock.acquire(held)", lock_sql, "conv:c-active01", "tok-B",
                 (t0 + timedelta(seconds=31)).isoformat(), (t0 + timedelta(seconds=1)).isoformat())
    holder_after_b = await con.fetchval("SELECT token FROM conversation_locks WHERE name='conv:c-active01'")
    t_late = t0 + timedelta(seconds=45)
    c = await ex("db_lock.acquire(expired)", lock_sql, "conv:c-active01", "tok-C",
                 (t_late + timedelta(seconds=30)).isoformat(), t_late.isoformat())
    holder_after_c = await con.fetchval("SELECT token FROM conversation_locks WHERE name='conv:c-active01'")
    d1 = await ex("db_lock.release(wrong token)", "DELETE FROM conversation_locks WHERE name=? AND token=?",
                  "conv:c-active01", "tok-A")
    d2 = await ex("db_lock.release", "DELETE FROM conversation_locks WHERE name=? AND token=?",
                  "conv:c-active01", "tok-C")
    # Microsegundos: isoformat() omite ".000000" cuando son 0; comparación de texto sigue siendo cronológica.
    z = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
    lex = await con.fetchval("SELECT $1::text < $2::text AND $2::text < $3::text",
                             z.isoformat(), (z + timedelta(microseconds=5)).isoformat(),
                             (z + timedelta(seconds=1)).isoformat())
    res["db_lock"] = {"status_free": a, "status_held": b, "status_expired": c,
                      "holder_after_held_attempt": holder_after_b, "holder_after_expired_takeover": holder_after_c,
                      "release_wrong_token_rowcount": affected(d1), "release_rowcount": affected(d2),
                      "iso_text_order_chronological": lex,
                      "collation": await con.fetchval("SELECT datcollate FROM pg_database WHERE datname=current_database()")}
    res["db_lock"]["ok"] = (affected(a) == 1 and affected(b) == 0 and affected(c) == 1 and holder_after_b == "tok-A"
                            and holder_after_c == "tok-C" and affected(d1) == 0 and affected(d2) == 1 and lex)

    # --- identity_link.py (_store / grant_for / revoke)
    store = ("INSERT INTO identity_grants VALUES (?,?,?,?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET "
             "channel=excluded.channel, subject_hash=excluded.subject_hash, "
             "brasper_user_id=excluded.brasper_user_id, grant_ciphertext=excluded.grant_ciphertext, "
             "expires_at=excluded.expires_at, created_at=excluded.created_at")
    g1 = await ex("identity_link._store(new)", store, "c-closed01", "telegram", "h1", "uuid-1", "cipher-1", now, now)
    g2 = await ex("identity_link._store(upsert)", store, "c-closed01", "telegram", "h2", "uuid-2", "cipher-2", now, now)
    row = await fetch("identity_link.grant_for", "SELECT channel, subject_hash, brasper_user_id, grant_ciphertext, "
                      "expires_at FROM identity_grants WHERE conversation_id=?", "c-closed01")
    g3 = await ex("identity_link.revoke", "DELETE FROM identity_grants WHERE conversation_id=?", "c-closed01")
    res["identity_link"] = {"insert_rowcount": affected(g1), "upsert_rowcount": affected(g2),
                            "after_upsert": dict(row[0]) if row else None, "revoke_rowcount": affected(g3)}
    res["identity_link"]["ok"] = (affected(g1) == 1 and affected(g2) == 1 and row
                                  and row[0]["subject_hash"] == "h2" and row[0]["grant_ciphertext"] == "cipher-2"
                                  and affected(g3) == 1)

    # --- db._creation_lock (advisory xact lock)
    key = "conv:whatsapp:pnid-1:wa:51987654321"
    async with con.transaction():
        st = await ex("db._creation_lock", "SELECT pg_advisory_xact_lock(hashtext(?))", key)
        held = await con.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid()")
        # Reentrante en la misma transacción (dos llamadas no se bloquean a sí mismas).
        await ex("db._creation_lock(reentrant)", "SELECT pg_advisory_xact_lock(hashtext(?))", key)
    after = await con.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid()")
    res["advisory_lock"] = {"status": st, "advisory_locks_in_tx": held, "advisory_locks_after_commit": after,
                            "hashtext": await con.fetchval("SELECT hashtext($1)", key)}
    res["advisory_lock"]["ok"] = held >= 1 and after == 0

    # --- outbound.py (ensure_schema, deliver, _set, in_flight, apply_status, for_conversation)
    await ex("outbound.ensure_schema.table", "CREATE TABLE IF NOT EXISTS outbound_messages (id TEXT PRIMARY KEY, "
             "conversation_id TEXT NOT NULL, channel TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', recipient "
             "TEXT NOT NULL, kind TEXT NOT NULL, human_revision INTEGER, text_sha256 TEXT, state TEXT NOT NULL, "
             "provider_message_id TEXT, detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    await ex("outbound.ensure_schema.idx1", "CREATE INDEX IF NOT EXISTS outbound_provider ON "
             "outbound_messages(connection_id, provider_message_id)")
    await ex("outbound.ensure_schema.idx2", "CREATE INDEX IF NOT EXISTS outbound_inflight ON "
             "outbound_messages(connection_id, recipient, state)")
    o_ins = "INSERT INTO outbound_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    await ex("outbound.deliver.insert", o_ins, "ob-1", "c-active01", "whatsapp", "pnid-1", "51987654321", "text",
             0, "ab" * 32, "pending", None, None, now, now)
    await ex("outbound.deliver.insert(null human_revision)", o_ins, "ob-2", "c-closed01", "telegram", "", "tg:1",
             "text", None, None, "pending", None, None, now, now)
    infl = await fetch("outbound.in_flight", "SELECT 1 FROM outbound_messages WHERE connection_id=? AND recipient=? "
                       "AND state='pending'", "pnid-1", "51987654321")
    o_set = ("UPDATE outbound_messages SET state=?, detail=?, provider_message_id=COALESCE(?, provider_message_id), "
             "updated_at=? WHERE id=?")
    u1 = await ex("outbound._set(sent,mid)", o_set, "sent", None, "wamid.OUT1", now, "ob-1")
    u2 = await ex("outbound._set(null mid keeps)", o_set, "sent", None, None, now, "ob-1")
    sel = "SELECT id, state FROM outbound_messages WHERE connection_id=? AND provider_message_id=?"
    adv = "UPDATE outbound_messages SET state=?, updated_at=? WHERE id=?"
    fail = ("UPDATE outbound_messages SET state='failed', detail='proveedor informó fallo', updated_at=? "
            "WHERE id=?")
    r = await fetch("outbound.apply_status.select", sel, "pnid-1", "wamid.OUT1")
    u3 = await ex("outbound.apply_status.advance(delivered)", adv, "delivered", now, r[0]["id"])
    u4 = await ex("outbound.apply_status.advance(read)", adv, "read", now, r[0]["id"])
    await ex("outbound._set(ob-2 sent)", o_set, "sent", None, "777", now, "ob-2")
    r2 = await fetch("outbound.apply_status.select(telegram '')", sel, "", "777")
    u5 = await ex("outbound.apply_status.failed", fail, now, r2[0]["id"])
    await fetch("outbound.for_conversation", "SELECT id, channel, kind, state, detail, provider_message_id, "
                "created_at, updated_at FROM outbound_messages WHERE conversation_id=? ORDER BY created_at DESC "
                "LIMIT ?", "c-active01", 50)
    final = {x["id"]: [x["state"], x["provider_message_id"], x["detail"]] for x in await con.fetch(
        "SELECT id, state, provider_message_id, detail FROM outbound_messages ORDER BY id")}
    res["outbound"] = {"in_flight_rows": len(infl), "set_rowcount": affected(u1),
                       "set_null_mid_rowcount": affected(u2), "advance_delivered": affected(u3),
                       "advance_read": affected(u4), "failed_rowcount": affected(u5), "final": final}
    res["outbound"]["ok"] = (len(infl) == 1 and affected(u1) == 1 and affected(u2) == 1 and affected(u3) == 1
                             and affected(u4) == 1 and affected(u5) == 1
                             and final["ob-1"][:2] == ["read", "wamid.OUT1"] and final["ob-2"][0] == "failed")

    # --- channel_events.py (ensure_schema, record, mark, replay, reconcile_echoes, sweep_stale_echoes)
    await ex("channel_events.ensure_schema.table", "CREATE TABLE IF NOT EXISTS channel_events (provider TEXT NOT "
             "NULL, connection_id TEXT NOT NULL DEFAULT '', event_id TEXT NOT NULL, kind TEXT NOT NULL, recipient "
             "TEXT, payload TEXT NOT NULL, state TEXT NOT NULL, received_at TEXT NOT NULL, processed_at TEXT, "
             "PRIMARY KEY(provider, connection_id, event_id))")
    await ex("channel_events.ensure_schema.idx", "CREATE INDEX IF NOT EXISTS channel_events_state ON "
             "channel_events(kind, state)")
    rec = ("INSERT INTO channel_events VALUES (?,?,?,?,?,?,?,?,NULL) "
           "ON CONFLICT(provider, connection_id, event_id) DO NOTHING")
    payload = json.dumps({"id": "wamid.ECHO1", "to": "51987654321", "text": "hola ñ"}, ensure_ascii=False)
    e1 = await ex("channel_events.record(new)", rec, "whatsapp", "pnid-1", "wamid.ECHO1", "echo", "51987654321",
                  payload, "deferred", now)
    e2 = await ex("channel_events.record(retry)", rec, "whatsapp", "pnid-1", "wamid.ECHO1", "echo", "51987654321",
                  payload, "deferred", now)
    e3 = await ex("channel_events.record(other conn)", rec, "whatsapp", "pnid-2", "wamid.ECHO1", "echo",
                  "51987654321", payload, "deferred", now)
    e4 = await ex("channel_events.record(telegram '')", rec, "telegram", "", "sha256:" + "0" * 64, "update", None,
                  "{}", "stored", now)
    await fetch("channel_events.replay", "SELECT provider, connection_id, event_id, payload FROM channel_events "
                "WHERE kind=? AND state='stored' ORDER BY received_at LIMIT ?", "update", 100)
    await fetch("channel_events.reconcile_echoes", "SELECT event_id, payload FROM channel_events WHERE "
                "provider='whatsapp' AND connection_id=? AND kind='echo' AND state='deferred' AND recipient=?",
                "pnid-1", "51987654321")
    m1 = await ex("channel_events.mark", "UPDATE channel_events SET state=?, processed_at=? WHERE provider=? AND "
                  "connection_id=? AND event_id=?", "own_echo", now, "whatsapp", "pnid-1", "wamid.ECHO1")
    limit = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(timespec="seconds")
    stale = await fetch("channel_events.sweep_stale_echoes.select", "SELECT connection_id, event_id, payload FROM "
                        "channel_events WHERE kind='echo' AND state='deferred' AND received_at < ?", limit)
    await ex("outbound.deliver.insert(pending for sweep)", o_ins, "ob-3", "c-active01", "whatsapp", "pnid-1",
             "51987654321", "text", 0, None, "pending", None, None, now, now)
    sw = await ex("channel_events.sweep_stale_echoes.update", "UPDATE outbound_messages SET state='uncertain', "
                  "detail='proceso interrumpido durante el envío', updated_at=? WHERE state='pending' AND "
                  "created_at < ?", now, limit)
    res["channel_events"] = {"record_new": affected(e1), "record_retry": affected(e2),
                             "record_other_connection": affected(e3), "record_telegram": affected(e4),
                             "mark_rowcount": affected(m1), "stale_deferred_rows": len(stale),
                             "sweep_pending_to_uncertain": affected(sw)}
    res["channel_events"]["ok"] = (affected(e1) == 1 and affected(e2) == 0 and affected(e3) == 1
                                   and affected(e4) == 1 and affected(m1) == 1 and len(stale) == 1
                                   and affected(sw) == 1)

    # --- db.py: INSERT de appointments / secret_rotations (0007 no quitó su tenant_id NOT NULL)
    legacy = {}
    ts = datetime(2026, 10, 9, 10, tzinfo=timezone.utc)  # psycopg envía str como 'unknown'; asyncpg exige datetime
    for label, sql, params in [
        ("db.create_appointment", "INSERT INTO appointments (conversation_id, user_ref, patient_name, document_id, "
         "specialty, scheduled_for, status, metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
         (None, None, "lab", None, "n/a", ts, "scheduled", None, ts, ts)),
        ("db.add_secret_rotation", "INSERT INTO secret_rotations (actor, secret_path, env_name, note, rotated_at) "
         "VALUES (?,?,?,?,?)", ("admin@lab.test", "whatsapp.token", "WHATSAPP_TOKEN", None, ts)),
    ]:
        try:
            legacy[label] = {"ok": True, "status": await con.execute(qmark_to_dollar(sql), *params)}
        except Exception as exc:  # noqa: BLE001
            legacy[label] = {"ok": False, "error": describe_error(exc)}
    res["legacy_tenant_id_inserts"] = legacy

    res["sql_log"] = sql_log
    res["invalid_sql"] = [s for s in sql_log if not s["ok"]]
    res["ok"] = all(res[k]["ok"] for k in ("contacts", "db_lock", "identity_link", "advisory_lock",
                                           "outbound", "channel_events")) \
        and not res["invalid_sql"]
    return res


# ------------------------------------------------------------------ drill
async def with_raw(args, fn):
    con = await raw_connect(args)
    try:
        return await fn(con)
    finally:
        await raw_close(con)


async def drill(args) -> dict:
    ev: dict = {"server": {}, "scenarios": {}}

    async def info(con):
        return {"version": await con.fetchval("SELECT version()"),
                "server_version_num": await con.fetchval("SHOW server_version_num"),
                "collation": await con.fetchval("SELECT datcollate FROM pg_database WHERE datname=current_database()")}
    ev["server"] = await with_raw(args, info)

    # ---------------- Escenario A: historial limpio, 0006 -> head de una vez
    A: dict = {}
    await with_raw(args, reset)
    A["upgrade_to_0006"] = await alembic(args, "upgrade", PRE_REV)
    await with_raw(args, seed_historical)
    A["base_data"] = base = await with_raw(args, data_snapshot)
    A["upgrade_to_head"] = await alembic(args, "upgrade", "head")
    A["fingerprint_head_1"] = fp1 = await with_raw(args, fingerprint)
    A["data_head_1"] = d1 = await with_raw(args, data_snapshot)
    A["upgrade_head_again"] = await alembic(args, "upgrade", "head")
    fp2 = await with_raw(args, fingerprint)
    d2 = await with_raw(args, data_snapshot)
    A["second_upgrade_noop"] = {k: fp1[k + "_md5"] == fp2[k + "_md5"] for k in FINGERPRINT_SQL} | {
        "data_identical": d1 == d2}
    A["preservation"] = pres = await with_raw(args, lambda c: compare_on_base_columns(c, base))
    A["preservation_ok"] = all(v.get("equal") or (v.get("expected_dropped") and v.get("dropped"))
                               for v in pres.values())
    A["verify_head"] = await with_raw(args, verify_head)

    # Paso 3: downgrade de 0010 rechaza y deja la BD intacta
    A["downgrade_0010"] = await alembic(args, "downgrade", "0009_autonomous_attention")
    fp3 = await with_raw(args, fingerprint)
    d3 = await with_raw(args, data_snapshot)
    A["after_refused_downgrade_0010"] = {k: fp1[k + "_md5"] == fp3[k + "_md5"] for k in FINGERPRINT_SQL} | {
        "data_identical": d1 == d3}
    A["downgrade_base"] = await alembic(args, "downgrade", "base")
    fp4 = await with_raw(args, fingerprint)
    A["after_refused_downgrade_base"] = {k: fp1[k + "_md5"] == fp4[k + "_md5"] for k in FINGERPRINT_SQL}

    # Paso 4: SQL runtime sobre la BD migrada
    A["runtime_sql"] = await with_raw(args, runtime_sql)
    ev["scenarios"]["A_clean_history"] = A

    # ---------------- Escenario B: 0009 aislado -> su downgrade rechaza
    B: dict = {}
    await with_raw(args, reset)
    B["upgrade_to_0006"] = await alembic(args, "upgrade", PRE_REV)
    await with_raw(args, seed_historical)
    B["upgrade_to_0009"] = await alembic(args, "upgrade", "0009_autonomous_attention")
    fpb = await with_raw(args, fingerprint)
    db_ = await with_raw(args, data_snapshot)
    B["downgrade_0009"] = await alembic(args, "downgrade", "0008_brasper_modeling")
    fpb2 = await with_raw(args, fingerprint)
    db2 = await with_raw(args, data_snapshot)
    B["after_refused_downgrade_0009"] = {k: fpb[k + "_md5"] == fpb2[k + "_md5"] for k in FINGERPRINT_SQL} | {
        "data_identical": db_ == db2}
    B["then_upgrade_head"] = await alembic(args, "upgrade", "head")
    ev["scenarios"]["B_downgrade_0009"] = B

    # ---------------- Escenario C: historial con versión duplicada en public_documents
    C: dict = {}
    await with_raw(args, reset)
    C["upgrade_to_0006"] = await alembic(args, "upgrade", PRE_REV)
    await with_raw(args, lambda c: seed_historical(c, dup_public_doc=True))
    C["upgrade_to_head"] = await alembic(args, "upgrade", "head")
    C["state_after"] = await with_raw(args, lambda c: _small_state(c))
    ev["scenarios"]["C_duplicate_public_document_version"] = C

    # ---------------- Escenario D: mismo id de conversación en dos tenants (0007 ADD PRIMARY KEY)
    D: dict = {}
    await with_raw(args, reset)
    D["upgrade_to_0006"] = await alembic(args, "upgrade", PRE_REV)
    await with_raw(args, lambda c: seed_historical(c, dup_conversation_id=True))
    D["upgrade_to_head"] = await alembic(args, "upgrade", "head")
    D["state_after"] = await with_raw(args, lambda c: _small_state(c))
    ev["scenarios"]["D_duplicate_conversation_id_across_tenants"] = D

    await with_raw(args, reset)
    return ev


async def _small_state(con) -> dict:
    return {"alembic_version": await _version(con),
            "has_tenant_id": bool(await con.fetchval(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='conversations' "
                "AND column_name='tenant_id'")),
            "has_contacts_table": bool(await con.fetchval("SELECT to_regclass('public.contacts')")),
            "conversations": await con.fetchval("SELECT count(*) FROM conversations"),
            "public_documents": await con.fetchval("SELECT count(*) FROM public_documents")}


def summarize(ev: dict) -> dict:
    A = ev["scenarios"]["A_clean_history"]
    B = ev["scenarios"]["B_downgrade_0009"]
    C = ev["scenarios"]["C_duplicate_public_document_version"]
    D = ev["scenarios"]["D_duplicate_conversation_id_across_tenants"]
    return {
        "server": ev["server"],
        "A.upgrade_0006": A["upgrade_to_0006"],
        "A.upgrade_head": A["upgrade_to_head"],
        "A.upgrade_head_again": A["upgrade_head_again"],
        "A.second_upgrade_noop": A["second_upgrade_noop"],
        "A.preservation_ok": A["preservation_ok"],
        "A.preservation_rows": {t: (v.get("now") or {}).get("rows") for t, v in A["preservation"].items()},
        "A.verify_head_ok": A["verify_head"]["ok"],
        "A.verify_head": {k: v for k, v in A["verify_head"].items() if k != "ok"},
        "A.downgrade_0010": A["downgrade_0010"],
        "A.after_refused_downgrade_0010": A["after_refused_downgrade_0010"],
        "A.downgrade_base": A["downgrade_base"],
        "A.after_refused_downgrade_base": A["after_refused_downgrade_base"],
        "A.runtime_sql_ok": A["runtime_sql"]["ok"],
        "A.legacy_tenant_id_inserts": A["runtime_sql"]["legacy_tenant_id_inserts"],
        "A.runtime_sql": {k: v for k, v in A["runtime_sql"].items()
                          if k not in ("sql_log", "ok", "legacy_tenant_id_inserts")},
        "B.upgrade_0009": B["upgrade_to_0009"],
        "B.downgrade_0009": B["downgrade_0009"],
        "B.after_refused_downgrade_0009": B["after_refused_downgrade_0009"],
        "B.then_upgrade_head": B["then_upgrade_head"],
        "C.upgrade_head": C["upgrade_to_head"],
        "C.state_after": C["state_after"],
        "D.upgrade_head": D["upgrade_to_head"],
        "D.state_after": D["state_after"],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--db", default="postgres")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("upgrade", "downgrade"):
        sub.add_parser(name).add_argument("rev")
    sub.add_parser("current")
    s = sub.add_parser("drill", help="escenarios completos (BORRA el esquema public)")
    s.add_argument("--out", help="JSON con la evidencia completa")
    args = p.parse_args()
    guard(args.host, args.db)

    if args.cmd in ("upgrade", "downgrade"):
        print(json.dumps(asyncio.run(alembic(args, args.cmd, args.rev)), ensure_ascii=False))
    elif args.cmd == "current":
        print(json.dumps(asyncio.run(with_raw(args, _version))))
    else:
        ev = asyncio.run(drill(args))
        if args.out:
            Path(args.out).write_text(json.dumps(ev, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(summarize(ev), indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
