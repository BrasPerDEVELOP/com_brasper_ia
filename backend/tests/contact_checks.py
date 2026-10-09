"""Contactos internos, alias por proveedor/conexión y creación concurrente (C5), sin red."""
import os
from concurrent.futures import ThreadPoolExecutor

from core import contacts, db, redis_runtime


def contact_checks():
    # 1) Mismo teléfono verificado por WhatsApp en dos conexiones -> un solo contacto.
    a = contacts.resolve("whatsapp", "conn-a", "51911222333")
    b = contacts.resolve("whatsapp", "conn-b", "51911222333")
    assert a == b
    with db.connect() as con:
        assert dict(con.execute("SELECT phone_e164 FROM contacts WHERE id=?", (a,)).fetchone())["phone_e164"] == "+51911222333"

    # 2) ID opaco (BSUID) sin teléfono: contacto propio y sin teléfono inventado de sus dígitos.
    opaque = contacts.resolve("whatsapp", "conn-a", "PE.ENT.1234567890")
    assert opaque != a
    with db.connect() as con:
        assert dict(con.execute("SELECT phone_e164 FROM contacts WHERE id=?", (opaque,)).fetchone())["phone_e164"] is None
    # El mismo evento trae BSUID + teléfono: el BSUID nuevo se une al contacto del teléfono.
    linked = contacts.resolve("whatsapp", "conn-a", "PE.ENT.555", phone_hint="51911222333")
    assert linked == a
    # Conflicto: BSUID ya ligado a otro contacto y ahora llega con ese teléfono -> no se fusiona.
    again = contacts.resolve("whatsapp", "conn-a", "PE.ENT.1234567890", phone_hint="51911222333")
    assert again == opaque
    open_conflicts = [c for c in contacts.conflicts() if c["external_id"] == "PE.ENT.1234567890"]
    assert len(open_conflicts) == 1 and open_conflicts[0]["proposed_contact_id"] == a
    contacts.resolve("whatsapp", "conn-a", "PE.ENT.1234567890", phone_hint="51911222333")
    assert len([c for c in contacts.conflicts() if c["external_id"] == "PE.ENT.1234567890"]) == 1, "sin duplicar"
    assert contacts.resolve_conflict(open_conflicts[0]["id"], "owner@test")
    # Telegram/webchat: nunca teléfono; username/nombre no vinculan.
    tg = contacts.resolve("telegram", None, "tg:42424242", display_name="@ana")
    assert tg not in {a, opaque} and contacts.resolve("telegram", None, "tg:42424242") == tg

    # 3) Alias concurrentes del mismo cliente -> un único contacto.
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = set(pool.map(lambda _: contacts.resolve("whatsapp", "conn-c", "5511987650000"), range(8)))
    assert len(ids) == 1

    # 4) Mensajes simultáneos de un cliente nuevo -> una sola conversación abierta, con contacto.
    with ThreadPoolExecutor(max_workers=6) as pool:
        cids = set(pool.map(lambda _: db.get_or_create_conversation("wa:51900000077", "whatsapp",
                                                                      connection_id="conn-a"), range(6)))
    assert len(cids) == 1, cids
    conv = db.get_conversation(cids.pop())
    assert conv["contact_id"] == contacts.resolve("whatsapp", "conn-a", "51900000077")
    # Otra conexión del mismo teléfono: conversación distinta (salida por su número) y mismo contacto.
    other = db.get_conversation(db.get_or_create_conversation("wa:51900000077", "whatsapp", connection_id="conn-b"))
    assert other["id"] != conv["id"] and other["contact_id"] == conv["contact_id"]

    # 5) Backfill histórico idempotente: conversaciones sin contacto lo reciben por alias exacto.
    with db.connect() as con:
        con.execute("INSERT INTO conversations (id, channel, user_ref, started_at, updated_at) "
                    "VALUES ('legacy-c5-1','telegram','tg:777','2025-01-01','2025-01-01')")
        con.execute("INSERT INTO conversations (id, channel, user_ref, started_at, updated_at) "
                    "VALUES ('legacy-c5-2','telegram','tg:777','2025-02-01','2025-02-01')")
    contacts.backfill()
    contacts.backfill()
    c1, c2 = db.get_conversation("legacy-c5-1"), db.get_conversation("legacy-c5-2")
    assert c1["contact_id"] and c1["contact_id"] == c2["contact_id"]

    # 6) Redis configurado pero caído: el lock de conversación sigue siendo exclusivo (base de datos).
    previous = os.environ.get("REDIS_URL", "")
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    redis_runtime._CLIENT = None
    try:
        token = redis_runtime.acquire_lock("c5:lock", wait_seconds=0.2)
        assert token and token.startswith("db:"), token
        assert redis_runtime.acquire_lock("c5:lock", wait_seconds=0.2) is None
        redis_runtime.release_lock("c5:lock", token)
        assert redis_runtime.acquire_lock("c5:lock", wait_seconds=0.2)
    finally:
        os.environ["REDIS_URL"] = previous
        redis_runtime._CLIENT = None
