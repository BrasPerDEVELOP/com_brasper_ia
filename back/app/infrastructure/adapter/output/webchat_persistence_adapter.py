import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class WebchatPersistenceAdapter:
    def __init__(self, db_path: str | None = None):
        base_dir = Path(__file__).resolve().parents[3] / "storage"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or str(base_dir / "webchat.sqlite3")
        self._ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_sessions (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step TEXT NOT NULL,
                    profile_type TEXT,
                    document_type TEXT,
                    document_number TEXT,
                    customer_id TEXT,
                    lead_id TEXT,
                    customer_status TEXT,
                    lead_status TEXT,
                    session_context TEXT NOT NULL,
                    last_user_message_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_leads (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source_channel TEXT NOT NULL,
                    profile_type TEXT,
                    document_type TEXT,
                    document_number TEXT,
                    names TEXT,
                    lastnames TEXT,
                    email TEXT,
                    phone TEXT,
                    country_hint TEXT,
                    customer_found INTEGER NOT NULL DEFAULT 0,
                    customer_id TEXT,
                    lead_stage TEXT,
                    conversation_summary TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    names TEXT,
                    lastnames TEXT,
                    email TEXT,
                    profile_image TEXT,
                    document_number TEXT,
                    document_type TEXT,
                    is_agent INTEGER,
                    role TEXT,
                    phone TEXT,
                    code_phone TEXT,
                    created_at TEXT,
                    created_by TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_clients_document
                ON clients(document_type, document_number);
                """
            )

    def upsert_session(self, session_payload: dict):
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": session_payload["id"],
            "channel": session_payload.get("channel", "webchat"),
            "status": session_payload.get("status", "active"),
            "current_step": session_payload["current_step"],
            "profile_type": session_payload.get("profile_type"),
            "document_type": session_payload.get("document_type"),
            "document_number": session_payload.get("document_number"),
            "customer_id": session_payload.get("customer_id"),
            "lead_id": session_payload.get("lead_id"),
            "customer_status": session_payload.get("customer_status"),
            "lead_status": session_payload.get("lead_status"),
            "session_context": json.dumps(session_payload.get("session_context") or {}),
            "last_user_message_at": session_payload.get("last_user_message_at"),
            "created_at": session_payload.get("created_at", now),
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO web_sessions (
                    id, channel, status, current_step, profile_type, document_type,
                    document_number, customer_id, lead_id, customer_status, lead_status,
                    session_context, last_user_message_at, created_at, updated_at
                ) VALUES (
                    :id, :channel, :status, :current_step, :profile_type, :document_type,
                    :document_number, :customer_id, :lead_id, :customer_status, :lead_status,
                    :session_context, :last_user_message_at, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    current_step = excluded.current_step,
                    profile_type = excluded.profile_type,
                    document_type = excluded.document_type,
                    document_number = excluded.document_number,
                    customer_id = excluded.customer_id,
                    lead_id = excluded.lead_id,
                    customer_status = excluded.customer_status,
                    lead_status = excluded.lead_status,
                    session_context = excluded.session_context,
                    last_user_message_at = excluded.last_user_message_at,
                    updated_at = excluded.updated_at
                """,
                record,
            )

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM web_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["session_context"] = json.loads(payload["session_context"] or "{}")
        return payload

    def upsert_lead(self, lead_payload: dict):
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": lead_payload["id"],
            "session_id": lead_payload["session_id"],
            "source_channel": lead_payload.get("source_channel", "webchat"),
            "profile_type": lead_payload.get("profile_type"),
            "document_type": lead_payload.get("document_type"),
            "document_number": lead_payload.get("document_number"),
            "names": lead_payload.get("names"),
            "lastnames": lead_payload.get("lastnames"),
            "email": lead_payload.get("email"),
            "phone": lead_payload.get("phone"),
            "country_hint": lead_payload.get("country_hint"),
            "customer_found": 1 if lead_payload.get("customer_found") else 0,
            "customer_id": lead_payload.get("customer_id"),
            "lead_stage": lead_payload.get("lead_stage"),
            "conversation_summary": lead_payload.get("conversation_summary"),
            "first_seen_at": lead_payload.get("first_seen_at", now),
            "last_seen_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO web_leads (
                    id, session_id, source_channel, profile_type, document_type,
                    document_number, names, lastnames, email, phone, country_hint,
                    customer_found, customer_id, lead_stage, conversation_summary,
                    first_seen_at, last_seen_at
                ) VALUES (
                    :id, :session_id, :source_channel, :profile_type, :document_type,
                    :document_number, :names, :lastnames, :email, :phone, :country_hint,
                    :customer_found, :customer_id, :lead_stage, :conversation_summary,
                    :first_seen_at, :last_seen_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    profile_type = excluded.profile_type,
                    document_type = excluded.document_type,
                    document_number = excluded.document_number,
                    names = excluded.names,
                    lastnames = excluded.lastnames,
                    email = excluded.email,
                    phone = excluded.phone,
                    country_hint = excluded.country_hint,
                    customer_found = excluded.customer_found,
                    customer_id = excluded.customer_id,
                    lead_stage = excluded.lead_stage,
                    conversation_summary = excluded.conversation_summary,
                    last_seen_at = excluded.last_seen_at
                """,
                record,
            )

    def seed_clients(self, clients: list[dict]):
        if not clients:
            return
        with self._connect() as connection:
            for client in clients:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO clients (
                        id, names, lastnames, email, profile_image, document_number,
                        document_type, is_agent, role, phone, code_phone, created_at,
                        created_by, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client.get("id"),
                        client.get("names"),
                        client.get("lastnames"),
                        client.get("email"),
                        client.get("profile_image"),
                        client.get("document_number"),
                        client.get("document_type"),
                        1 if client.get("is_agent") else 0,
                        client.get("role"),
                        str(client.get("phone")) if client.get("phone") is not None else None,
                        client.get("code_phone"),
                        client.get("created_at"),
                        client.get("created_by"),
                        client.get("updated_at"),
                    ),
                )

    def find_client(self, document_type: str, document_number: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM clients
                WHERE lower(document_type) = lower(?)
                  AND upper(document_number) = upper(?)
                LIMIT 1
                """,
                (document_type, document_number),
            ).fetchone()
        return dict(row) if row else None
