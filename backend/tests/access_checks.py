"""Permisos backend por rol, canal, número y sector; adjuntos privados (C6/C7)."""
from unittest.mock import AsyncMock, patch

from core import access, auth, db, telegram, whatsapp


def access_checks(client, owner_headers):
    def make(email, role, scope=None):
        if not auth.user_from_email(email):
            auth.create_user(email, email.split("@")[0], role, token=f"tok-{email}")
        if scope is not None:
            access.set_scope(email, scope)
        return {"X-Auth-Token": f"tok-{email}"}

    tg_agent = make("tg-agent@test", "agent", {"channels": ["telegram"]})
    wa_a_agent = make("wa-a-agent@test", "agent", {"channels": ["whatsapp"], "connections": ["conn-a"]})
    vip_agent = make("vip-agent@test", "agent", {"sectors": ["empresas"]})
    analyst = make("analyst@test", "analyst")

    tg = db.get_or_create_conversation("tg:880001", "telegram")
    wa_a = db.get_or_create_conversation("wa:51988800001", "whatsapp", connection_id="conn-a")
    wa_b = db.get_or_create_conversation("wa:51988800002", "whatsapp", connection_id="conn-b")
    vip = db.get_or_create_conversation("tg:880002", "telegram")
    db.add_tag(vip, "sector:empresas", "owner@test")
    db.add_message(tg, "user", "📎 comprobante", media={"provider": "telegram", "ref": "file-proof-1", "kind": "photo"})

    def ids(headers):
        r = client.get("/api/conversations?limit=500", headers=headers)
        assert r.status_code == 200, r.text
        return {c["id"] for c in r.json()["conversations"]}

    # 1) Listado filtrado en el backend por canal / número / sector.
    assert tg in ids(tg_agent) and not ids(tg_agent) & {wa_a, wa_b}
    assert wa_a in ids(wa_a_agent) and not ids(wa_a_agent) & {wa_b, tg, vip}
    assert vip in ids(vip_agent) and not ids(vip_agent) & {tg, wa_a, wa_b}
    assert {tg, wa_a, wa_b, vip} <= ids(owner_headers)

    # 2) Detalle, respuesta, notas y adjuntos fuera de alcance -> 403 aunque conozca el id.
    assert client.get(f"/api/conversations/{wa_b}", headers=wa_a_agent).status_code == 403
    assert client.post(f"/api/conversations/{wa_b}/reply", json={"text": "hola"}, headers=wa_a_agent).status_code == 403
    assert client.get(f"/api/conversations/{tg}/notes", headers=vip_agent).status_code == 403
    assert client.get("/api/media", params={"provider": "telegram", "ref": "file-proof-1", "conversation_id": tg},
                      headers=wa_a_agent).status_code == 403
    assert client.get(f"/api/conversations/{wa_b}/deliveries", headers=wa_a_agent).status_code == 403

    # 3) Comprobante privado: el analista ve la conversación pero no el adjunto; el asesor con alcance sí.
    with patch.object(telegram, "download_file", AsyncMock(return_value=(b"img", "image/jpeg"))):
        r = client.get("/api/media", params={"provider": "telegram", "ref": "file-proof-1", "conversation_id": tg},
                       headers=analyst)
        assert r.status_code == 403, r.text
        r = client.get("/api/media", params={"provider": "telegram", "ref": "file-proof-1", "conversation_id": tg},
                       headers=tg_agent)
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
        # Una referencia que no pertenece a la conversación no se sirve aunque exista en otra.
        assert client.get("/api/media", params={"provider": "telegram", "ref": "file-proof-1", "conversation_id": vip},
                          headers=owner_headers).status_code == 404

    # 4) Asignación: no a un asesor sin alcance; un asesor no reasigna conversaciones ajenas.
    r = client.post(f"/api/conversations/{wa_b}/assign", json={"email": "wa-a-agent@test"}, headers=owner_headers)
    assert r.status_code == 422, r.text
    assert client.post(f"/api/conversations/{wa_a}/assign", json={"email": "wa-a-agent@test"},
                       headers=owner_headers).status_code == 200
    r = client.post(f"/api/conversations/{wa_a}/assign", json={"email": "tg-agent@test"}, headers=tg_agent)
    assert r.status_code == 403
    db.set_conversation_status(tg, "handoff")
    with patch.object(whatsapp, "send_text", AsyncMock(return_value={"sent": True})):
        assert client.post(f"/api/conversations/{tg}/assign", json={"email": "tg-agent@test"},
                           headers=tg_agent).status_code == 200

    # 5) Derivación automática solo a asesores con alcance.
    db.assign_conversation(wa_b, None)
    chosen = auth.derive_to_advisor(wa_b)
    assert chosen not in {"tg-agent@test", "wa-a-agent@test", "vip-agent@test"}, chosen

    # 6) Administración del alcance: solo quien gestiona usuarios; valores inválidos rechazados.
    assert client.put("/api/admin/users/tg-agent@test/scope", json={"channels": ["fax"]},
                      headers=owner_headers).status_code == 422
    assert client.put("/api/admin/users/tg-agent@test/scope", json={"channels": ["webchat"]},
                      headers=tg_agent).status_code == 403
    r = client.put("/api/admin/users/tg-agent@test/scope", json={"channels": ["telegram", "webchat"]},
                   headers=owner_headers)
    assert r.status_code == 200 and r.json()["access_scope"]["channels"] == ["telegram", "webchat"]
    listed = client.get("/api/admin/users", headers=owner_headers).json()["users"]
    assert all("token" not in u for u in listed)
    # Alcance corrupto en la base: se cierra en vez de abrir todo.
    with db.connect() as con:
        con.execute("UPDATE panel_users SET access_scope='{broken' WHERE email='vip-agent@test'")
    assert not ids(vip_agent)
