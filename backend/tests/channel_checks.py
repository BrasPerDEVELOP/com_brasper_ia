"""Contract fixtures from Meta documentation; no live Meta calls."""
import asyncio
from unittest.mock import patch
from core import db, tenants, whatsapp, channel_receipts, lead_onboarding


def run(client, payload_factory):
    cfg = tenants.get_config()
    old_wa, old_features = cfg.get("whatsapp"), cfg.get("features")
    cfg["whatsapp"] = {"connections": [{"id": "a", "phone_number_id": "TEST_A", "mode": "coex"},
                                       {"id": "b", "phone_number_id": "TEST_B", "mode": "coex"}]}
    cfg["features"] = {**(old_features or {}), "coex": True}
    sent = []
    async def send(to, text, connection=None, **kwargs):
        sent.append((to, (connection or {}).get("id")))
        return {"sent": True}
    try:
        assert tenants.whatsapp_connection_by_id(None) is None
        assert whatsapp._creds(tenants.whatsapp_connection_by_id("deleted"))[:2] == (None, None)
        with patch.object(whatsapp, "send_text", side_effect=send):
            ids = []
            for suffix in ["A", "B"]:
                body = payload_factory("wamid.scoped." + suffix, "Cotizar 100 PEN a BRL")
                value = body["entry"][0]["changes"][0]["value"]
                value["metadata"]["phone_number_id"] = "TEST_" + suffix
                value["messages"][0]["from"] = "51988776655"
                value["contacts"][0]["wa_id"] = "51988776655"
                assert client.post("/webhook", json=body).status_code == 200
            convs = [c for c in db.list_conversations() if c["user_ref"] == "wa:51988776655"]
            assert len(convs) == 2 and {c["connection_id"] for c in convs} == {"a", "b"}
            assert sent[-2:] == [("51988776655", "a"), ("51988776655", "b")]
            ca = next(c for c in convs if c["connection_id"] == "a")
            last_text = db.get_messages(ca["id"])[-1]["content"]
            echo = {"entry": [{"changes": [{"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "TEST_A"}, "message_echoes": [{
                    "id": "wamid.own", "to": "51988776655", "type": "text", "text": {"body": last_text}}]}}]}]}
            channel_receipts.remember("a", "wamid.own")
            assert client.post("/webhook", json=echo).json()["results"][0]["reason"] == "eco de la API"
            assert db.get_conversation(ca["id"])["status"] == "active"
            echo["entry"][0]["changes"][0]["value"]["message_echoes"][0]["id"] = "wamid.human.same.words"
            assert client.post("/webhook", json=echo).json()["results"][0]["takeover"]
            assert db.get_conversation(ca["id"])["status"] == "handoff"
            assert db.get_conversation(next(c["id"] for c in convs if c["connection_id"] == "b"))["status"] == "active"
        bsuid = "PE.syntheticA123"
        body = {"entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "TEST_A"},
            "contacts": [{"user_id": bsuid, "profile": {"name": "Synthetic", "username": "synthetic"}}],
            "messages": [{"id": "wamid.bsuid", "from_user_id": bsuid, "type": "text", "text": {"body": "hola"}}]}}]}]}
        event = whatsapp.parse_incoming(body)[0]
        assert event["from"] == bsuid and event["phone"] is None
        assert event["contact"]["identity"]["user_id"] == bsuid
        assert whatsapp.recipient_fields(bsuid) == {"recipient": bsuid}
        assert lead_onboarding.phone_from_channel("whatsapp", "wa:" + bsuid) is None
        assert whatsapp.recipient_fields("51988776655") == {"to": "51988776655"}
        for invalid in ["username", "PE.synthetic!", "wa:51988776655"]:
            try: whatsapp.recipient_fields(invalid)
            except ValueError: pass
            else: raise AssertionError("invalid recipient accepted")
        async def upload(*args, **kwargs):
            db.invalidate_ai(ca["id"])
            return {"ok": True, "id": "synthetic-media"}
        with patch.object(whatsapp, "upload_media", side_effect=upload), patch.object(whatsapp.httpx, "AsyncClient") as http:
            result = asyncio.run(whatsapp.send_image_upload("51988776655", "x.png", b"test", "image/png", delivery_guard=lambda: False))
            assert not result["sent"] and not http.called
        try:
            db.get_or_create_conversation("different-user", "whatsapp", ca["id"])
        except ValueError: pass
        else: raise AssertionError("conversation ownership bypass")
    finally:
        cfg["whatsapp"] = old_wa
        if old_features is None: cfg.pop("features", None)
        else: cfg["features"] = old_features
