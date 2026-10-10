"""Optional surveys and bounded follow-ups. Durable jobs, closed by default."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import auth, db, handoff_summary, tenants, util


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    surveys: bool = False
    timezone: str = "America/Lima"
    weekdays: list[int] = Field(default_factory=list)
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=18, ge=1, le=24)
    waiting_minutes: int = Field(default=30, ge=1, le=10080)
    inactivity_minutes: int = Field(default=60, ge=1, le=10080)
    max_reminders: int = Field(default=0, ge=0, le=3)
    sla_minutes: int = Field(default=120, ge=1, le=10080)
    expiry_hours: int = Field(default=24, ge=1, le=168)
    allowed_channels: list[str] = Field(default_factory=list)
    whatsapp_window_seconds: int | None = Field(default=None, ge=1, le=86400)
    policy_source: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Zona horaria IANA no válida") from exc
        if self.start_hour >= self.end_hour or any(d not in range(7) for d in self.weekdays):
            raise ValueError("Horario no válido; usa días 0–6 y apertura anterior al cierre")
        if set(self.allowed_channels) - {"whatsapp", "telegram", "webchat"}:
            raise ValueError("Canal no válido")
        if self.enabled and not self.weekdays:
            raise ValueError("Configura los días de atención antes de habilitar")
        if "whatsapp" in self.allowed_channels and (not self.whatsapp_window_seconds or not self.policy_source.strip()):
            raise ValueError("WhatsApp requiere ventana y fuente de política verificadas")
        return self


class Conflict(ValueError):
    pass


def ensure_schema():
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS engagement_settings (id INTEGER PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)")
        con.execute("INSERT INTO engagement_settings VALUES (1,0,?) ON CONFLICT(id) DO NOTHING", (Settings().model_dump_json(),))
        con.execute("CREATE TABLE IF NOT EXISTS engagement_jobs (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
                    "revision INTEGER NOT NULL, kind TEXT NOT NULL, sequence INTEGER NOT NULL, due_at TEXT NOT NULL, "
                    "expires_at TEXT NOT NULL, state TEXT NOT NULL, detail TEXT, "
                    "UNIQUE(conversation_id,revision,kind,sequence))")
        con.execute("CREATE INDEX IF NOT EXISTS engagement_jobs_due ON engagement_jobs(state,due_at)")
        con.execute("CREATE TABLE IF NOT EXISTS satisfaction (job_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
                    "state TEXT NOT NULL, score INTEGER, comment TEXT, updated_at TEXT NOT NULL, revision INTEGER NOT NULL)")


def configuration():
    with db.connect() as con:
        row = con.execute("SELECT * FROM engagement_settings WHERE id=1").fetchone()
    return {"version": row["version"], "settings": json.loads(row["payload"])}


def save(settings: Settings, version: int):
    with db.connect() as con:
        result = con.execute("UPDATE engagement_settings SET payload=?,version=version+1 WHERE id=1 AND version=?",
                             (settings.model_dump_json(), version))
        if result.rowcount != 1:
            raise Conflict("La configuración cambió; recarga antes de guardar")


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def within_hours(now, settings):
    local = now.astimezone(ZoneInfo(settings.timezone))
    return local.weekday() in settings.weekdays and settings.start_hour <= local.hour < settings.end_hour


def next_open(now, settings):
    # UTC traversal avoids nonexistent/repeated wall times at DST boundaries.
    for minute in range(7 * 24 * 60 + 1):
        candidate = now + timedelta(minutes=minute)
        if within_hours(candidate, settings):
            return candidate
    return None


def cancel(cid):
    with db.connect() as con:
        con.execute("UPDATE engagement_jobs SET state='cancelled' WHERE conversation_id=? AND state='pending'", (cid,))


def record_consent(cid, text):
    # Solo frases explícitas; la puntuación y espacios no cambian el sentido ("Sí, quiero recordatorios").
    normalized = " ".join(re.sub(r"[^\w\s]", " ", util.normalize_text(text)).split())
    yes = {"si quiero recordatorios", "acepto recordatorios", "sim quero lembretes", "aceito lembretes"}
    no = {"no quiero recordatorios", "no mas recordatorios", "nao quero lembretes", "nao envie lembretes"}
    if normalized not in yes | no:
        return
    db.merge_lead_data(cid, {"followup_consent": {"allowed": normalized in yes,
        "recorded_at": util.now_iso(), "source": "explicit_customer_message"}})
    if normalized in no:
        cancel(cid)


def schedule(cid, kind, now=None):
    from .lease import guard
    guard()
    settings = Settings(**configuration()["settings"])
    conv = db.get_conversation(cid)
    if not settings.enabled or not conv or kind not in {"survey", "waiting", "inactivity"}:
        return
    if kind == "survey" and not settings.surveys:
        return
    now = now or datetime.now(timezone.utc)
    count = 1 if kind == "survey" else settings.max_reminders
    interval = settings.waiting_minutes if kind == "waiting" else settings.inactivity_minutes
    for sequence in range(1, count + 1):
        due = next_open(now + timedelta(minutes=1 if kind == "survey" else interval * sequence), settings)
        expiry = now + timedelta(hours=settings.expiry_hours)
        if due is None or due >= expiry:
            continue
        with db.connect() as con:
            con.execute("INSERT INTO engagement_jobs VALUES (?,?,?,?,?,?,?,'pending',NULL) "
                        "ON CONFLICT(conversation_id,revision,kind,sequence) DO NOTHING",
                        (uuid4().hex, cid, int(conv.get("human_revision", 0)), kind, sequence, due.isoformat(), expiry.isoformat()))


def _permitted(job, conv, settings, now):
    if not settings.enabled or not conv or int(conv.get("human_revision", 0)) != job["revision"]:
        return False
    lead = conv.get("lead_data") or {}
    consent = lead.get("followup_consent") or {}
    if not isinstance(consent, dict) or consent.get("allowed") is not True or not consent.get("recorded_at") or not consent.get("source"):
        return False
    channel = conv.get("channel")
    if channel not in settings.allowed_channels or not within_hours(now, settings):
        return False
    expected = {"survey": "closed", "waiting": "handoff", "inactivity": "active"}[job["kind"]]
    if conv.get("status") != expected or (job["kind"] == "waiting" and conv.get("assigned_to")):
        return False
    if channel == "whatsapp":
        if not settings.whatsapp_window_seconds or not settings.policy_source or not conv.get("connection_id"):
            return False
        messages = [m for m in db.get_messages(conv["id"]) if m.get("role") == "user"]
        if not messages or (now - utc(messages[-1]["created_at"])).total_seconds() >= settings.whatsapp_window_seconds:
            return False  # No implicit template substitution outside verified window.
    return True


CLAIM_STALE_MINUTES = 10

COPY = {
    "survey": ("¿Cómo fue tu atención? Si deseas, responde del 1 al 5 (5 es la mejor). Puedes omitir la encuesta y seguir consultando.",
               "Como foi seu atendimento? Se quiser, responda de 1 a 5 (5 é a melhor nota). Pode pular a pesquisa e continuar conversando."),
    "waiting": ("Tu solicitud sigue en la cola de atención. Conservamos el contexto para que un asesor continúe por aquí.",
                "Sua solicitação continua na fila de atendimento. Guardamos o contexto para um atendente continuar por aqui."),
    "inactivity": ("Si deseas continuar, puedes responder por aquí. Conservamos el contexto de esta conversación.",
                   "Se quiser continuar, pode responder por aqui. Guardamos o contexto desta conversa."),
}


async def dispatch_one(send=None, now=None):
    fixed_now = now
    now = now or datetime.now(timezone.utc)
    claim_stale = (now - timedelta(minutes=CLAIM_STALE_MINUTES)).isoformat()
    with db.connect() as con:
        con.execute("UPDATE engagement_jobs SET state='expired' WHERE state='pending' AND expires_at<=?", (now.isoformat(),))
        # Reclamado y el proceso murió: no se sabe si salió. Nunca se reenvía; queda incierto.
        con.execute("UPDATE engagement_jobs SET state='uncertain', detail='claim_interrupted' "
                    "WHERE state='claimed' AND detail < ?", ("claimed_at:" + claim_stale,))
        row = con.execute("SELECT * FROM engagement_jobs WHERE state='pending' AND due_at<=? ORDER BY due_at,id LIMIT 1", (now.isoformat(),)).fetchone()
        if not row:
            return False
        job = dict(row)
        claimed = con.execute("UPDATE engagement_jobs SET state='claimed', detail=? WHERE id=? AND state='pending'",
                              ("claimed_at:" + now.isoformat(), job["id"]))
        if claimed.rowcount != 1:
            return False
    state, detail = "suppressed", "policy_or_conversation_changed"
    try:
        settings = Settings(**configuration()["settings"])
        conv = db.get_conversation(job["conversation_id"])
        if _permitted(job, conv, settings, now):
            pt = (conv.get("lead_data") or {}).get("idioma") == "pt"
            text = COPY[job["kind"]][int(pt)]
            # A claim is never automatically retried after an uncertain send.
            if send is None:
                from . import telegram, whatsapp
                async def send(c, message):
                    ref = c["user_ref"]
                    if c["channel"] == "telegram" and ref.startswith("tg:"):
                        return await telegram.send_message(ref[3:], message)
                    if c["channel"] == "whatsapp" and ref.startswith("wa:"):
                        conn = tenants.whatsapp_connection_by_id(c["connection_id"])
                        if not conn:
                            return {"sent": False}
                        return await whatsapp.send_text(ref[3:], message, connection=conn)
                    return {"sent": c["channel"] == "webchat"}
            if not _permitted(job, db.get_conversation(job["conversation_id"]), Settings(**configuration()["settings"]), fixed_now or datetime.now(timezone.utc)):
                return True
            result = await send(conv, text)
            state, detail = ("sent", "delivered") if result.get("sent") or result.get("ok") else ("uncertain", "provider_did_not_confirm")
            if state == "sent":
                db.add_message(conv["id"], "assistant", text)
                if job["kind"] == "survey":
                    with db.connect() as con:
                        con.execute("INSERT INTO satisfaction VALUES (?,?,'awaiting_score',NULL,NULL,?,?) ON CONFLICT(job_id) DO NOTHING",
                                    (job["id"], conv["id"], now.isoformat(), job["revision"]))
                if job["kind"] == "waiting" and job["sequence"] * settings.waiting_minutes >= settings.sla_minutes:
                    db.add_audit_event(None, "conversation.sla_exceeded", f"conversation:{conv['id']}", {})
    except Exception:
        state, detail = "uncertain", "delivery_exception"
    finally:
        with db.connect() as con:
            con.execute("UPDATE engagement_jobs SET state=?,detail=? WHERE id=?", (state, detail, job["id"]))
    return True


def receive(user_ref, channel, text, conversation_id=None):
    """Consume only an outstanding optional survey; unrelated messages resume chat."""
    with db.connect() as con:
        row = con.execute("SELECT s.*,c.user_ref,c.channel FROM satisfaction s JOIN conversations c ON c.id=s.conversation_id "
                          "WHERE c.user_ref=? AND c.channel=? AND s.state IN ('awaiting_score','awaiting_comment') "
                          "ORDER BY s.updated_at DESC LIMIT 1", (user_ref, channel)).fetchone()
    if not row or (conversation_id and conversation_id != row["conversation_id"]):
        return None
    cid = row["conversation_id"]
    record_consent(cid, text)
    if int((db.get_conversation(cid) or {}).get("human_revision", 0)) != row["revision"]:
        with db.connect() as con:
            con.execute("UPDATE satisfaction SET state='cancelled' WHERE job_id=?", (row["job_id"],))
        return None
    if datetime.now(timezone.utc) - utc(row["updated_at"]) > timedelta(hours=24):
        with db.connect() as con:
            con.execute("UPDATE satisfaction SET state='expired' WHERE job_id=?", (row["job_id"],))
        return None
    pt = db.get_lead_data(cid).get("idioma") == "pt"
    normalized = util.normalize_text(text).strip()
    skip = normalized in {"omitir", "pular", "no", "nao", "saltar"}
    score = int(normalized) if row["state"] == "awaiting_score" and normalized in {"1", "2", "3", "4", "5"} else None
    if row["state"] == "awaiting_score" and score is None and not skip:
        with db.connect() as con:
            con.execute("UPDATE satisfaction SET state='skipped' WHERE job_id=?", (row["job_id"],))
        return None
    # A new operational question or human request must not disappear into feedback.
    if row["state"] == "awaiting_comment":
        from . import agent_graph, knowledge, quotes
        if (agent_graph._handoff_hit(text) or quotes.has_intent(text) or agent_graph._status_hit(text)
                or "?" in text or knowledge.has_intent(text)):
            with db.connect() as con:
                con.execute("UPDATE satisfaction SET state='done' WHERE job_id=?", (row["job_id"],))
            return None
    state = "skipped" if skip else "awaiting_comment" if score is not None else "done"
    comment = text[:2000] if row["state"] == "awaiting_comment" and not skip else None
    with db.connect() as con:
        changed = con.execute("UPDATE satisfaction SET state=?,score=COALESCE(?,score),comment=?,updated_at=? WHERE job_id=? AND state=?",
                              (state, score, comment, util.now_iso(), row["job_id"], row["state"]))
        if changed.rowcount != 1:
            return None
    db.add_message(cid, "user", text)
    with db.connect() as con:
        con.execute("UPDATE satisfaction SET revision=? WHERE job_id=?",
                    (int(db.get_conversation(cid).get("human_revision", 0)), row["job_id"]))
    complaint = comment and any(w in normalized for w in ["reclamo", "reclamacao", "queja", "fraude"])
    if complaint:
        db.set_conversation_status(cid, "handoff")
        auth.derive_to_advisor(cid)
        handoff_summary.build(cid, "satisfaction_complaint")
        reply = "Um atendente vai revisar seu relato por aqui." if pt else "Un asesor revisará tu reclamo por aquí."
    elif state == "awaiting_comment":
        reply = "Obrigado! Quer deixar um comentário? É opcional; pode responder pular." if pt else "¡Gracias! ¿Quieres dejar un comentario? Es opcional; puedes responder omitir."
        if score <= 2:
            reply += " Se precisar, peça um atendente." if pt else " Si lo necesitas, pide un asesor."
    else:
        reply = "Obrigado! Pode continuar consultando quando precisar." if pt else "¡Gracias! Puedes seguir consultando cuando lo necesites."
    # Reopen only conversation state, never financial state.
    if not complaint:
        db.set_conversation_status(cid, "active")
    db.add_message(cid, "assistant", reply)
    return {"conversation_id": cid, "response": reply, "handoff": bool(complaint), "usage": None,
            "flow": "satisfaction", "human_revision": int(db.get_conversation(cid).get("human_revision", 0))}


def metrics():
    with db.connect() as con:
        scores = con.execute("SELECT COUNT(*) AS responses,AVG(score) AS average FROM satisfaction WHERE score IS NOT NULL").fetchone()
        jobs = con.execute("SELECT state,COUNT(*) AS count FROM engagement_jobs GROUP BY state").fetchall()
    return {"satisfaction": dict(scores), "jobs": [dict(row) for row in jobs]}
