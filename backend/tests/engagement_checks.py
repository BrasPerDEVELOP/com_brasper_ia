"""Checks with isolated database and simulated delivery only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from core import db, engagement as e


from core import util


def run(client, owner, agent):
    original = e.configuration()
    settings = e.Settings(enabled=True, surveys=True, weekdays=list(range(7)),
        start_hour=0, end_hour=24, max_reminders=1, waiting_minutes=1,
        inactivity_minutes=1, allowed_channels=["webchat"])
    now = datetime.now(timezone.utc)
    delivered = []

    async def sender(conv, text):
        delivered.append((conv["id"], text))
        return {"sent": True}

    def make(ref, consent=True, status="active"):
        cid = db.get_or_create_conversation("engagement-test-" + ref, "webchat")
        db.add_message(cid, "user", "hola")
        if consent:
            e.record_consent(cid, "acepto recordatorios")
        db.set_conversation_status(cid, status)
        return cid

    def dispatch():
        return asyncio.run(e.dispatch_one(sender, now=now + timedelta(minutes=2)))

    def job_state(cid):
        with db.connect() as con:
            return con.execute("SELECT state FROM engagement_jobs WHERE conversation_id=? ORDER BY due_at DESC LIMIT 1", (cid,)).fetchone()["state"]

    try:
        e.save(settings, original["version"])
        version = e.configuration()["version"]
        payload = {"settings": settings.model_dump(), "expected_version": version}
        assert client.put("/api/admin/engagement", headers=agent, json=payload).status_code == 403
        invalid = {**payload, "settings": {**settings.model_dump(), "timezone": "invalid/not-a-zone"}}
        assert client.put("/api/admin/engagement", headers=owner, json=invalid).status_code == 422
        invalid["settings"] = {**settings.model_dump(), "allowed_channels": ["whatsapp"]}
        assert client.put("/api/admin/engagement", headers=owner, json=invalid).status_code == 422
        assert client.put("/api/admin/engagement", headers=owner, json={**payload, "expected_version": version - 1}).status_code == 409
        cid = make("once")
        e.schedule(cid, "inactivity", now)
        e.schedule(cid, "inactivity", now)
        e.ensure_schema()  # Durable pending jobs survive process initialization.
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: dispatch(), range(2)))
        assert [c for c, _ in delivered].count(cid) == 1 and job_state(cid) == "sent"
        for ref, action, consent in [("no-consent", None, False), ("human", "human", True),
                                    ("reply", "reply", True), ("revoke", "revoke", True)]:
            cid = make(ref, consent)
            e.schedule(cid, "inactivity", now)
            if action == "human": db.invalidate_ai(cid)
            elif action == "reply": db.add_message(cid, "user", "ya respondí")
            elif action == "revoke": e.record_consent(cid, "no quiero recordatorios")
            dispatch()
            assert cid not in [c for c, _ in delivered]
            assert job_state(cid) in {"cancelled", "suppressed"}
        cid = make("expired")
        e.schedule(cid, "inactivity", now - timedelta(days=2))
        dispatch()
        assert job_state(cid) == "expired"
        cid = make("uncertain")
        e.schedule(cid, "inactivity", now)
        async def timeout(*args): raise TimeoutError("synthetic timeout")
        asyncio.run(e.dispatch_one(timeout, now=now + timedelta(minutes=2)))
        dispatch()
        assert job_state(cid) == "uncertain" and cid not in [c for c, _ in delivered]
        cid = make("survey", status="closed")
        db.merge_lead_data(cid, {"idioma": "pt"})
        e.schedule(cid, "survey", now)
        dispatch()
        assert "atendimento" in delivered[-1][1]
        out = e.receive("engagement-test-survey", "webchat", "2", cid)
        assert out["flow"] == "satisfaction" and "atendente" in out["response"]
        out = e.receive("engagement-test-survey", "webchat", "reclamacao: atendimento ruim", cid)
        assert out["handoff"] and db.get_conversation(cid)["status"] == "handoff"
        assert e.metrics()["satisfaction"]["responses"] >= 1
        cid = make("skip-survey", status="closed")
        e.schedule(cid, "survey", now)
        dispatch()
        assert e.receive("engagement-test-skip-survey", "webchat", "cuánto recibo por 500 soles", cid) is None
        with db.connect() as con:
            assert con.execute("SELECT state FROM satisfaction WHERE conversation_id=?", (cid,)).fetchone()["state"] == "skipped"
        dst = e.Settings(weekdays=[6], timezone="America/New_York", start_hour=3, end_hour=4)
        assert e.next_open(datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), dst) == datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)
        wa = e.Settings(**{**settings.model_dump(), "allowed_channels": ["whatsapp"],
            "whatsapp_window_seconds": 86400, "policy_source": "Meta Coex reviewed 2026-10-08"})
        cid = db.get_or_create_conversation("wa:engagement-synthetic", "whatsapp")
        db.set_connection(cid, "synthetic-connection")
        db.add_message(cid, "user", "acepto recordatorios")
        e.record_consent(cid, "acepto recordatorios")
        conv = db.get_conversation(cid)
        job = {"kind": "inactivity", "revision": conv["human_revision"]}
        assert e._permitted(job, conv, wa, datetime.now(timezone.utc))
        db.add_message(cid, "assistant", "human reply")
        assert not e._permitted(job, conv, wa, now + timedelta(days=2))
        # Consentimiento explícito con puntuación; frases ambiguas no cuentan.
        cid_c = db.get_or_create_conversation("consent-punct", "webchat")
        e.record_consent(cid_c, "Sí, quiero recordatorios!")
        assert db.get_lead_data(cid_c)["followup_consent"]["allowed"] is True
        e.record_consent(cid_c, "tal vez recordatorios")
        assert db.get_lead_data(cid_c)["followup_consent"]["allowed"] is True
        e.record_consent(cid_c, "No, no quiero recordatorios.")
        assert db.get_lead_data(cid_c)["followup_consent"]["allowed"] is True, "frase no exacta no cambia nada"
        e.record_consent(cid_c, "No quiero recordatorios.")
        assert db.get_lead_data(cid_c)["followup_consent"]["allowed"] is False
        # Job reclamado y proceso caído: queda incierto (nunca se reenvía); uno reciente no se toca.
        cid_j = db.get_or_create_conversation("claim-crash", "webchat")
        stale = (now - timedelta(minutes=30)).isoformat()
        with db.connect() as con:
            con.execute("INSERT INTO engagement_jobs VALUES ('crash-job',?,0,'inactivity',9,?,?,'claimed',?)",
                        (cid_j, stale, (now + timedelta(days=1)).isoformat(), "claimed_at:" + stale))
            con.execute("INSERT INTO engagement_jobs VALUES ('live-job',?,0,'inactivity',8,?,?,'claimed',?)",
                        (cid_j, stale, (now + timedelta(days=1)).isoformat(), "claimed_at:" + now.isoformat()))

        asyncio.new_event_loop().run_until_complete(e.dispatch_one(send=None, now=now))
        with db.connect() as con:
            states = {r["id"]: r["state"] for r in con.execute(
                "SELECT id,state FROM engagement_jobs WHERE id IN ('crash-job','live-job')").fetchall()}
        assert states == {"crash-job": "uncertain", "live-job": "claimed"}, states
        # Pregunta durante el comentario de la encuesta: vuelve al chat, no se guarda como comentario.
        cid_s = db.get_or_create_conversation("survey-question", "webchat")
        with db.connect() as con:
            con.execute("INSERT INTO satisfaction VALUES ('sq-job',?,'awaiting_comment',4,NULL,?,?)",
                        (cid_s, util.now_iso(), int(db.get_conversation(cid_s)["human_revision"])))
        assert e.receive("survey-question", "webchat", "¿qué horario de atención tienen?", cid_s) is None
        with db.connect() as con:
            row = con.execute("SELECT state, comment FROM satisfaction WHERE job_id='sq-job'").fetchone()
        assert row["state"] == "done" and row["comment"] is None
    finally:
        e.save(e.Settings(**original["settings"]), e.configuration()["version"])
        with db.connect() as con:
            con.execute("UPDATE engagement_jobs SET state='cancelled' WHERE state='pending'")
