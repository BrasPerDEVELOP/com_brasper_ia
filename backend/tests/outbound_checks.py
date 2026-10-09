"""Salidas (enviado/cancelado/incierto/fallido), estados fuera de orden, ecos Coex diferidos y
replay de sincronización (C5), con proveedores simulados: ningún mensaje real."""
import asyncio
from unittest.mock import patch

from core import channel_events, db, features, outbound, tenants


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _out(cid):
    return {"conversation_id": cid, "human_revision": int(db.get_conversation(cid)["human_revision"])}


def outbound_checks():
    from api import routes
    cid = db.get_or_create_conversation("wa:51955500011", "whatsapp", connection_id="conn-x")
    calls = []

    async def ok():
        calls.append("ok")
        return {"sent": True, "status": 200, "message_id": "wamid.OWN1"}

    # 1) Humano interviene antes del envío: cancelado y el proveedor no se llama.
    stale = _out(cid)
    db.invalidate_ai(cid, pause=False)
    res = _run(outbound.deliver(stale, "whatsapp", "51955500011", ok, connection_id="conn-x", text="hola"))
    assert res["state"] == "cancelled" and not calls

    # 2) Enviado, fallido (4xx), incierto (excepción / 5xx).
    res = _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", ok, connection_id="conn-x", text="hola"))
    assert res["state"] == "sent" and calls == ["ok"]

    async def rejected():
        return {"sent": False, "status": 400, "detail": "bad recipient"}

    async def boom():
        raise TimeoutError("provider timeout")

    async def server_error():
        return {"sent": False, "status": 503}

    assert _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", rejected, connection_id="conn-x"))["state"] == "failed"
    assert _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", boom, connection_id="conn-x"))["state"] == "uncertain"
    assert _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", server_error, connection_id="conn-x"))["state"] == "uncertain"
    states = [r["state"] for r in outbound.for_conversation(cid)]
    assert sorted(states) == ["cancelled", "failed", "sent", "uncertain", "uncertain"], states

    # 3) Estados del proveedor fuera de orden: solo avanzan; fallo tardío tras leído se ignora.
    assert outbound.apply_status("conn-x", "wamid.OWN1", "read")
    assert not outbound.apply_status("conn-x", "wamid.OWN1", "delivered")
    assert not outbound.apply_status("conn-x", "wamid.OWN1", "failed")
    assert not outbound.apply_status("conn-y", "wamid.OWN1", "read"), "otra conexión no toca el registro"
    assert [r for r in outbound.for_conversation(cid) if r["provider_message_id"] == "wamid.OWN1"][0]["state"] == "read"

    # 4) Eco que llega mientras el envío está en vuelo: se difiere y se resuelve por id.
    cfg = tenants.get_config()
    conn = {"id": "conn-x", "mode": "coex"}
    flags = dict(features.all_flags(), coex=True)
    with patch.object(features, "all_flags", return_value=flags):
        db.set_conversation_status(cid, "active")
        before = int(db.get_conversation(cid)["human_revision"])
        seen = {}

        async def send_with_echo(echo_id):
            seen["r"] = await routes._handle_whatsapp_echo(cfg, {"id": echo_id, "to": "51955500011", "text": "hola"}, conn)
            return {"sent": True, "status": 200, "message_id": "wamid.OWN2"}

        _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", lambda: send_with_echo("wamid.OWN2"),
                              connection_id="conn-x", text="hola"))
        assert seen["r"].get("deferred"), seen
        conv = db.get_conversation(cid)
        assert int(conv["human_revision"]) == before and conv["status"] != "handoff", "eco propio no pausa"

        # Mismo texto pero otro id: actividad humana (el texto igual no prueba nada).
        _run(outbound.deliver(_out(cid), "whatsapp", "51955500011", lambda: send_with_echo("wamid.HUMAN"),
                              connection_id="conn-x", text="hola"))
        assert seen["r"].get("deferred")
        assert int(db.get_conversation(cid)["human_revision"]) > before, "eco humano invalida respuestas"

        # Envío incierto con eco en vuelo: no se puede probar que sea nuestro -> humano.
        cid2 = db.get_or_create_conversation("wa:51955500022", "whatsapp", connection_id="conn-x")
        rev2 = int(db.get_conversation(cid2)["human_revision"])

        async def echo_then_fail():
            await routes._handle_whatsapp_echo(cfg, {"id": "wamid.UNK", "to": "51955500022", "text": "x"}, conn)
            raise TimeoutError()

        assert _run(outbound.deliver(_out(cid2), "whatsapp", "51955500022", echo_then_fail,
                                     connection_id="conn-x"))["state"] == "uncertain"
        assert int(db.get_conversation(cid2)["human_revision"]) > rev2

        # Sin envío en vuelo: el eco humano se aplica de inmediato.
        cid3 = db.get_or_create_conversation("wa:51955500033", "whatsapp", connection_id="conn-x")
        res = _run(routes._handle_whatsapp_echo(cfg, {"id": "wamid.H3", "to": "51955500033", "text": "yo"}, conn))
        assert res.get("takeover") and db.get_conversation(cid3)["status"] == "handoff"

    # 5) Caída a mitad del envío: ecos diferidos viejos -> humano; envío 'pending' viejo -> incierto.
    cid4 = db.get_or_create_conversation("wa:51955500044", "whatsapp", connection_id="conn-x")
    rev4 = int(db.get_conversation(cid4)["human_revision"])
    old = "2020-01-01T00:00:00+00:00"
    with db.connect() as con:
        con.execute("INSERT INTO outbound_messages VALUES ('crash1',?,'whatsapp','conn-x','51955500044','text',0,NULL,"
                    "'pending',NULL,NULL,?,?)", (cid4, old, old))
    channel_events.defer_echo("conn-x", {"id": "wamid.LOST", "to": "51955500044", "text": "?"})
    with db.connect() as con:
        con.execute("UPDATE channel_events SET received_at=? WHERE event_id='wamid.LOST'", (old,))
    assert channel_events.sweep_stale_echoes() == 1
    assert int(db.get_conversation(cid4)["human_revision"]) > rev4
    assert [r for r in outbound.for_conversation(cid4) if r["id"] == "crash1"][0]["state"] == "uncertain"

    # 6) Sincronización Coex: se guarda una vez (reintentos idempotentes) y se reproduce después.
    payload = {"messaging_product": "whatsapp", "history": [{"threads": []}]}
    assert channel_events.record("whatsapp", "conn-x", "history", payload)
    assert not channel_events.record("whatsapp", "conn-x", "history", payload)
    failing = channel_events.replay("history", lambda p: (_ for _ in ()).throw(ValueError("mapper")))
    assert failing["failed"] >= 1 and failing["processed"] == 0, "un mapeador que falla no pierde el evento"
    assert channel_events.replay("history", lambda p: "mapped")["processed"] == failing["failed"]
    assert channel_events.replay("history", lambda p: "mapped")["processed"] == 0
