"""Vinculación verificable Telegram/webchat (C2) sin red: la API se simula en `brasper_api`."""
import asyncio
import dataclasses
import threading
import time
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from core import brasper_api, db, engine, features, identity_link, idempotency, llm, operation_status, tenants


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def identity_checks():
    from cryptography.fernet import Fernet
    token = "A" * 20 + "b-_" + "C" * 20
    other_token = "Z" * 43
    owner = str(uuid4())
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    # 1) Extracción: deep-link de Telegram, comando y token suelto; nunca un fragmento de otra palabra.
    assert identity_link.extract_token(f"/start {token}") == (identity_link.REDACTED, token)
    assert identity_link.extract_token(f"hola\nvincular {token}")[1] == token
    assert identity_link.extract_token("x" + token)[1] is None
    assert identity_link.extract_token("quiero enviar 500 soles")[1] is None
    # Varios códigos: todos redactados y ninguno canjeado; forma de código fuera del patrón: redactada.
    many, flag = identity_link.extract_token(f"vincular {token}\n/start {other_token}")
    assert flag == identity_link.AMBIGUOUS and token not in many and other_token not in many
    loose, none = identity_link.extract_token(f"mi codigo:{token}.")
    assert none is None and token not in loose
    # 2) Solo canales con referencia propia: nunca el visitante genérico ni WhatsApp (tiene teléfono).
    assert identity_link.subject_for("telegram", "tg:12345") == "tg:12345"
    assert identity_link.subject_for("telegram", "tg:-100") is None
    assert identity_link.subject_for("webchat", "webchat-visitor") is None
    assert identity_link.subject_for("whatsapp", "wa:51999") is None

    flags = dict(features.all_flags(), identity_link=True, operation_status=True)
    calls = []

    def redeem(tenant, channel, subject, link_token):
        calls.append(("redeem", channel, subject, link_token))
        if link_token != token or subject != "tg:12345":
            return {"ok": False, "status": 401, "error": "rechazado por la API"}
        return {"ok": True, "status": 200, "data": {"user_id": owner, "grant": "grant-secret-1", "expires_at": expires}}

    def linked(tenant, user_id, grant, channel, subject, reference=""):
        calls.append(("ops", user_id, grant, channel, subject, reference))
        if grant != "grant-secret-1" or user_id != owner or subject != "tg:12345":
            return {"ok": False, "status": 401, "error": "rechazado por la API"}
        return {"ok": True, "data": {"data": [{"code": "PxB-77", "status": "verification"}]}}

    async def no_llm(*_a, **_k):
        raise AssertionError("el token nunca debe llegar al LLM")

    with patch.dict(os.environ, {identity_link.GRANT_KEY_ENV: Fernet.generate_key().decode()}), \
         patch.object(features, "all_flags", return_value=flags), \
         patch.object(brasper_api, "redeem_identity_link", side_effect=redeem), \
         patch.object(brasper_api, "linked_operations", side_effect=linked), \
         patch.object(brasper_api, "operation_status", side_effect=AssertionError("sin teléfono no hay consulta")), \
         patch.object(llm, "chat", side_effect=no_llm):
        # Enlace al portal: solo https configurado, referencia en el fragmento (#), nunca en la query.
        api_cfg = brasper_api._api_cfg(tenants.get_config())
        assert identity_link.portal_hint("telegram", "tg:12345", "es") is None
        with patch.dict(api_cfg, {"identity_link_url": "https://portal.test/vincular-chat"}):
            hint = identity_link.portal_hint("telegram", "tg:12345", "pt")
            assert "https://portal.test/vincular-chat#canal=telegram&ref=tg%3A12345" in hint and "?" not in hint
            assert identity_link.portal_hint("webchat", "webchat-visitor", "es") is None
        # 3) Sin vínculo: estado -> asesor, sin llamar a la API privada; el nombre escrito no vincula.
        out = _run(engine.handle_message("tg:12345", "Soy Ana Pérez, ¿ya llegó mi envío?", channel="telegram"))
        cid = out["conversation_id"]
        assert out["handoff"] and not [c for c in calls if c[0] == "ops"], out
        db.set_conversation_status(cid, "active")

        # 4) Canje correcto: el token no se guarda en mensajes; grant cifrado y atado al chat.
        out = _run(engine.handle_message("tg:12345", f"/start {token}", channel="telegram", conversation_id=cid))
        assert "vinculado" in out["response"] and out["flow"] == "identity_link", out
        stored = " ".join(m["content"] for m in db.get_messages(cid))
        assert token not in stored and identity_link.REDACTED in stored
        with db.connect() as con:
            raw = dict(con.execute("SELECT * FROM identity_grants WHERE conversation_id=?", (cid,)).fetchone())
        assert "grant-secret-1" not in str(raw) and raw["brasper_user_id"] == owner
        assert "grant-secret-1" not in str(db.get_lead_data(cid))

        # 4b) Dos códigos en un mensaje: ninguno se canjea ni queda en el historial.
        before_redeems = len([c for c in calls if c[0] == "redeem"])
        out = _run(engine.handle_message("tg:12345", f"vincular {other_token} y {token}", channel="telegram",
                                         conversation_id=cid))
        assert "más de un código" in out["response"], out
        assert len([c for c in calls if c[0] == "redeem"]) == before_redeems
        stored = " ".join(m["content"] for m in db.get_messages(cid))
        assert other_token not in stored and token not in stored

        # 5) Consulta privada con grant: estado oficial del dueño, sin derivación.
        out = _run(engine.handle_message("tg:12345", "¿ya llegó mi envío PxB-77?", channel="telegram", conversation_id=cid))
        assert "en verificación" in out["response"] and not out["handoff"], out
        assert calls[-1] == ("ops", owner, "grant-secret-1", "telegram", "tg:12345", "PxB-77")

        # 6) Token reutilizado: idempotencia devuelve el resultado registrado sin un segundo canje.
        before = len([c for c in calls if c[0] == "redeem"])
        identity_link.redeem(cid, "telegram", "tg:12345", token, "es")
        assert len([c for c in calls if c[0] == "redeem"]) == before

        # 7) Otro chat no puede usar el grant de esta conversación ni canjear el token ajeno.
        assert identity_link.grant_for(cid, "telegram", "tg:99999") is None
        other = db.get_or_create_conversation("tg:99999", "telegram")
        assert "no es válido" in identity_link.redeem(other, "telegram", "tg:99999", other_token, "es")
        assert operation_status.lookup(other, "telegram", "tg:99999", "estado", "es") is None

        # 8) Grant vencido: se borra y vuelve a derivar.
        with db.connect() as con:
            con.execute("UPDATE identity_grants SET expires_at=? WHERE conversation_id=?",
                        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), cid))
        assert operation_status.lookup(cid, "telegram", "tg:12345", "estado", "es") is None
        with db.connect() as con:
            assert con.execute("SELECT 1 FROM identity_grants WHERE conversation_id=?", (cid,)).fetchone() is None

        # 9) La API revoca el grant (401): el bot lo olvida.
        idempotency_key = "identity.redeem:" + identity_link._digest(token)
        with db.connect() as con:
            con.execute("DELETE FROM idempotency_keys WHERE key=?", (idempotency_key,))
        identity_link.redeem(cid, "telegram", "tg:12345", token, "es")
        with patch.object(brasper_api, "linked_operations", return_value={"ok": False, "status": 401}):
            assert operation_status.lookup(cid, "telegram", "tg:12345", "estado", "es") is None
        assert identity_link.grant_for(cid, "telegram", "tg:12345") is None

        # 10) Clave rotada: el grant guardado deja de servir (no se descifra con otra clave).
        with db.connect() as con:
            con.execute("DELETE FROM idempotency_keys WHERE key=?", (idempotency_key,))
        identity_link.redeem(cid, "telegram", "tg:12345", token, "es")
        with patch.dict(os.environ, {identity_link.GRANT_KEY_ENV: Fernet.generate_key().decode()}):
            assert identity_link.grant_for(cid, "telegram", "tg:12345") is None

    # 11) Timeout del canje: no se repite la escritura; el resultado tardío queda guardado.
    release = threading.Event()

    def slow_redeem(tenant, channel, subject, link_token):
        release.wait(5)
        return {"ok": True, "data": {"user_id": owner, "grant": "late-grant", "expires_at": expires}}

    slow_token = "S" * 43
    cid3 = db.get_or_create_conversation("tg:555", "telegram")
    with patch.dict(os.environ, {identity_link.GRANT_KEY_ENV: Fernet.generate_key().decode()}), \
         patch.object(features, "all_flags", return_value=flags), \
         patch.object(brasper_api, "redeem_identity_link", side_effect=slow_redeem) as remote, \
         patch.dict(identity_link.tool_contracts.REGISTRY, {"identity.redeem": dataclasses.replace(
             identity_link.tool_contracts.REGISTRY["identity.redeem"], timeout=0.2)}):
        assert "No pude verificar" in identity_link.redeem(cid3, "telegram", "tg:555", slow_token, "es")
        assert "No pude verificar" in identity_link.redeem(cid3, "telegram", "tg:555", slow_token, "es")
        assert remote.call_count == 1, "un timeout no se reintenta contra la API"
        release.set()
        for _ in range(50):
            if identity_link.grant_for(cid3, "telegram", "tg:555"):
                break
            time.sleep(0.05)
        assert identity_link.grant_for(cid3, "telegram", "tg:555")["grant"] == "late-grant"
        assert "late-grant" not in str(idempotency.recall("identity.redeem:" + identity_link._digest(slow_token)))

    # 12) Flag apagado o sin clave: no hay vinculación ni consulta privada.
    with patch.dict(os.environ, {identity_link.GRANT_KEY_ENV: ""}):
        assert identity_link.portal_hint("telegram", "tg:12345", "es") is None
        assert "no admite" in identity_link.redeem(cid, "telegram", "tg:12345", token, "es")
    assert tenants.get_config() is not None
