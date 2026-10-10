"""Campañas en la plataforma IA (plan de campañas y usuarios, 10 oct). Sin red ni API financiera."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core import brasper_api, campaign_offers, campaigns, db, engine, features, media_library

ROUTES = ["BRL_PEN", "PEN_BRL", "USD_BRL"]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _approved(asset_id, language, purpose="promotion"):
    # Imagen aprobada solo en su propio idioma (la de español nunca sirve para portugués).
    expected = {"img-es": "es", "img-pt": "pt"}
    return {"asset_id": asset_id, "version": 1} if expected.get(asset_id) == language else None


def _draft(**overrides):
    now = datetime.now(timezone.utc)
    base = {"name": "Primer envío", "discount_percentage": 50, "max_uses": 100, "per_user_limit": 1,
            "routes": ["PEN_BRL", "BRL_PEN"], "start_date": now - timedelta(days=1), "end_date": now + timedelta(days=30),
            "campaign_rules": {"segment": "first_transfer", "priority": 5,
                               "messages": {"es": {"text": "Primer envío con 50% menos de comisión.", "media_id": "img-es"},
                                            "pt": {"text": "Primeiro envio com 50% a menos de comissão.", "media_id": "img-pt"}}}}
    rules = {**base["campaign_rules"], **overrides.pop("campaign_rules", {})}
    return campaigns.CampaignDraft.model_validate({**base, **overrides, "campaign_rules": rules})


def _published(**overrides):
    with patch.object(media_library, "approved", side_effect=_approved):
        saved = campaigns.save(_draft(**overrides), "owner@test")
        campaigns.publish(saved["id"], saved["version"], "owner@test", routes_available=ROUTES)
    return saved


def _disable_all():
    for item in campaigns.inventory():
        campaigns.disable(item["id"])


def campaign_offer_checks():
    """Oferta en la bienvenida: idioma, imagen del mismo idioma, sin repetir, sujeto a comprobación."""
    flags = dict(features.all_flags(), campaigns=True)
    _disable_all()

    # 1) Flag apagado: sin oferta.
    _published()
    out = _run(engine.handle_message("offer-off", "hola", channel="webchat"))
    assert "comisión" not in out["response"] and not out.get("banner")

    with patch.object(features, "all_flags", return_value=flags), \
         patch.object(media_library, "approved", side_effect=_approved):
        # 2) Idioma sin evidencia: se pregunta UNA vez y no se ofrece aún.
        out = _run(engine.handle_message("tg:7700001", "hi", channel="telegram"))
        cid = out["conversation_id"]
        assert campaign_offers.ASK_LANGUAGE in out["response"] and not out.get("banner"), out
        stage = db.get_lead_data(cid).get("onboarding_field")

        # 3) Elige portugués: no se toma como nombre; oferta en pt (texto + aviso + imagen pt), nada en español.
        out = _run(engine.handle_message("tg:7700001", "português", channel="telegram", conversation_id=cid))
        lead = db.get_lead_data(cid)
        assert lead.get("nombres") in (None, "") and lead.get("onboarding_field") == stage, lead
        assert lead.get("idioma_confirmado") == "pt"
        banner = out.get("banner")
        assert banner and banner["asset_id"] == "img-pt", out
        assert "Primeiro envio com 50%" in out["response"] and campaign_offers.DISCLAIMER["pt"] in out["response"]
        assert "Primer envío con 50%" not in out["response"]
        rows = campaign_offers.offered(cid)
        assert len(rows) == 1 and rows[0]["language"] == "pt"

        # 4) No se repite en mensajes siguientes ni al reabrir la conversación (mismo contacto).
        out = _run(engine.handle_message("tg:7700001", "Ana Silva", channel="telegram", conversation_id=cid))
        assert not out.get("banner") and "Primeiro envio com 50%" not in out["response"]
        assert campaign_offers.ASK_LANGUAGE not in out["response"]
        db.set_conversation_status(cid, "closed")
        out = _run(engine.handle_message("tg:7700001", "oi", channel="telegram"))
        assert out["conversation_id"] != cid and not out.get("banner")

        # 5) Imagen retirada después de publicar: solo texto, sin afirmar imagen.
        _disable_all()
        _published(name="Solo texto ES", campaign_rules={"messages": {"es": {"text": "Promo ES", "media_id": "img-es"},
                                                                      "pt": {"text": "Promo PT", "media_id": None}}})
        with patch.object(media_library, "approved", return_value=None):
            out = _run(engine.handle_message("offer-es", "hola", channel="webchat"))
        assert out.get("banner") and out["banner"]["asset_id"] is None, out
        assert "Promo ES" in out["response"] and campaign_offers.DISCLAIMER["es"] in out["response"]

        # 6) Brasper confirma que ya no es primer envío: no se le ofrece.
        cid6 = db.get_or_create_conversation("offer-returning", "webchat")
        db.merge_lead_data(cid6, {"identity_source": "channel_phone_match", "brasper_user_id": "u-ret",
                                  "history_status": "verified", "first_transfer_eligible": False,
                                  "completed_transfers": 3})
        assert campaign_offers.welcome_offer(cid6, db.get_lead_data(cid6), "es", True) == {}

        # 7) Borrador o campaña desactivada: nunca se ofrece.
        _disable_all()
        campaigns.save(_draft(name="Solo borrador"), "owner@test")
        assert campaign_offers.active() == []
        out = _run(engine.handle_message("offer-draft", "hola", channel="webchat"))
        assert not out.get("banner")


def campaign_lifecycle_checks():
    """Persistencia IA: versiones, publicación, rutas, cupos, primer envío único y concurrencia."""
    _disable_all()
    # 1) Validación del borrador: 1–100 %, rutas, ES/PT, primer envío = 1 beneficio por persona.
    for bad in ({"discount_percentage": 0}, {"routes": []}, {"routes": ["PEN_PEN"]}, {"per_user_limit": 2},
                {"campaign_rules": {"messages": {"es": {"text": "solo ES"}}}}):
        try:
            _draft(**bad)
            raise AssertionError(f"debía rechazar {bad}")
        except ValueError:
            pass
    assert _draft(routes=["PEN_BRL", "ALL"]).routes == ["ALL"]

    # 2) Identificador interno generado, versiones y conflicto de edición; el borrador no cambia lo publicado.
    saved = campaigns.save(_draft(name="Versionada"), "owner@test")
    assert saved["code"].startswith("CAMP-") and saved["version"] == 1
    v2 = campaigns.save(_draft(name="Versionada", discount_percentage=40), "owner@test", saved["id"], 1)
    assert v2["version"] == 2 and v2["code"] == saved["code"]
    try:
        campaigns.save(_draft(name="Versionada"), "owner@test", saved["id"], 1)
        raise AssertionError("conflicto de versión")
    except campaigns.Conflict:
        pass
    # Publicación: rutas deben existir en Brasper e imágenes aprobadas en su idioma.
    try:
        campaigns.publish(saved["id"], 2, "owner@test", routes_available=["USD_BRL"])
        raise AssertionError("ruta no habilitada")
    except ValueError as exc:
        assert "Rutas sin tipo de cambio" in str(exc)
    try:
        campaigns.publish(saved["id"], 2, "owner@test", routes_available=[])
        raise AssertionError("sin rutas verificables")
    except ValueError:
        pass
    with patch.object(media_library, "approved", return_value=None):
        try:
            campaigns.publish(saved["id"], 2, "owner@test", routes_available=ROUTES)
            raise AssertionError("imagen sin aprobar")
        except ValueError as exc:
            assert "imagen" in str(exc)
    with patch.object(media_library, "approved", side_effect=_approved):
        campaigns.publish(saved["id"], 1, "owner@test", routes_available=ROUTES)
    campaigns.save(_draft(name="Versionada", discount_percentage=10), "owner@test", saved["id"], 2)
    live = [c for c in campaigns.published_active() if c["campaign_id"] == saved["id"]]
    assert live and live[0]["version"] == 1 and live[0]["draft"].discount_percentage == 50, "borrador invisible"
    campaigns.disable(saved["id"])

    # 3) Elegibilidad: identidad verificada + dato Brasper; si no, no confirmable.
    assert campaigns.eligibility({"brasper_user_id": "x"})["first_transfer"] is None, "nombre/registro no bastan"
    verified = {"identity_source": "channel_phone_match", "brasper_user_id": "u1", "is_first_transfer": True}
    assert campaigns.eligibility(verified) == {"first_transfer": True, "returning": None, "source": "brasper_no_transactions"}
    assert campaigns.eligibility({**verified, "is_first_transfer": False})["first_transfer"] is None

    # 4) Reserva / consumo / liberación con cupo total, límite por persona y primer envío único.
    first = _published(name="Primer envío A", max_uses=3)
    second = _published(name="Primer envío B")

    def client(ref, doc, user):
        cid = db.get_or_create_conversation(ref, "whatsapp" if ref.startswith("wa:") else "telegram")
        db.merge_lead_data(cid, {"identity_source": "channel_phone_match", "brasper_user_id": user,
                                 "is_first_transfer": True, "tipo_documento": "dni", "numero_documento": doc})
        return cid

    a = client("wa:51911000001", "40000001", "user-a")
    b1 = _reserve(first["id"], a, "PxB-101")
    assert b1["state"] == "reserved" and b1["eligibility_source"] == "brasper_no_transactions"
    for target, ref in ((first["id"], "PxB-102"), (second["id"], "PxB-103")):
        try:
            _reserve(target, a, ref)
            raise AssertionError("primer envío repetido")
        except campaigns.BenefitRejected:
            pass
    # Otro canal / cuenta duplicada con el mismo documento: también bloqueado.
    dup = client("tg:880077", "40000001", "user-a-duplicada")
    try:
        _reserve(second["id"], dup, "PxB-104")
        raise AssertionError("cuenta duplicada con el mismo documento")
    except campaigns.BenefitRejected:
        pass
    # Liberar (falló la operación) solo una vez; después puede volver a reservar.
    assert campaigns.release(b1["id"], "agent@test", "Operación cancelada en Brasper")["state"] == "released"
    try:
        campaigns.release(b1["id"], "agent@test", "otra vez")
        raise AssertionError("liberación doble")
    except campaigns.BenefitRejected:
        pass
    b2 = _reserve(second["id"], a, "PxB-105")
    try:
        campaigns.consume(b2["id"], "agent@test", "completada")
        raise AssertionError("sin referencia oficial registrada no se consume")
    except campaigns.BenefitRejected:
        pass
    assert _complete(b2["id"])["state"] == "consumed"
    for action in (campaigns.release, campaigns.consume):
        try:
            action(b2["id"], "agent@test", "nota")
            raise AssertionError("un consumido no cambia")
        except campaigns.BenefitRejected:
            pass

    # 5) Sin elegibilidad confirmable: el asesor debe declarar que verificó el historial.
    unknown = db.get_or_create_conversation("wa:51911000009", "whatsapp")
    db.merge_lead_data(unknown, {"identity_source": "channel_phone_match", "brasper_user_id": "user-u",
                                 "is_first_transfer": False})
    for note in (None, "ok", "   verificado   "):
        try:
            _reserve(first["id"], unknown, "PxB-200", note=note)
            raise AssertionError("sin dato y sin evidencia humana suficiente no se reserva")
        except campaigns.BenefitRejected:
            pass
    verified_b = _reserve(first["id"], unknown, "PxB-200",
                          note="Revisé el historial del cliente en el backoffice de Brasper: sin envíos completados")
    assert verified_b["eligibility_source"] == "advisor_verified"
    assert "backoffice" in campaigns.benefit(verified_b["id"])["evidence"]

    # 6) Concurrencia: muchas reservas simultáneas no superan el cupo total ni duplican primer envío.
    capped = _published(name="Cupo 2", max_uses=2, campaign_rules={"segment": "all"})
    convs = [client(f"wa:5191200000{i}", f"5000000{i}", f"user-c{i}") for i in range(6)]
    case_ids = [_accept(capped["id"], c) for c in convs]

    def attempt(i):
        try:
            campaigns.reserve(case_ids[i], "agent@test", operation_ref=f"PxB-30{i}")
            return True
        except campaigns.BenefitRejected:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert sum(results) == 2, results
    # Misma persona en 5 conversaciones/canales con expedientes propios: un solo primer envío.
    ft = _published(name="Primer envío C")
    same_cases = [_accept(ft["id"], client(f"wa:5191300000{i}", "60000000", "user-same")) for i in range(5)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        wins = sum(pool.map(lambda i: _try(same_cases[i], f"PxB-40{i}"), range(5)))
    assert wins == 1, wins

    # 7) Cotización: nota de ahorro estimado solo con elegibilidad confirmada y si supera el cupón público.
    _disable_all()
    _published(name="Promo cotización", discount_percentage=50)
    lead = {"identity_source": "channel_phone_match", "brasper_user_id": "u-q", "is_first_transfer": True}
    match = campaigns.for_quote(lead, "PEN", "BRL", 1000, 30)
    assert match and match["saving"] == 15.0
    assert campaigns.for_quote({"brasper_user_id": "u-q"}, "PEN", "BRL", 1000, 30) is None
    assert campaigns.for_quote(lead, "USD", "BRL", 1000, 30) is None, "ruta no incluida"
    _disable_all()

    # 8) Migración de datos del diseño anterior: se importan como borrador, conservando ES/PT e identificador.
    legacy = [{"draft": {"code": "PRIMER25", "discount_percentage": 25, "max_uses": 100, "per_user_limit": 1,
                         "origin_currency": "PEN", "destination_currency": "BRL",
                         "start_date": "2026-01-01T00:00:00+00:00", "end_date": "2099-01-01T00:00:00+00:00",
                         "campaign_rules": {"segment": "first_transfer", "messages": {"es": {"text": "ES", "media_id": "img-es"},
                                                                                      "pt": {"text": "PT"}}}}},
              {"draft": {"code": "ROTA"}}]
    report = campaigns.import_legacy(legacy, "owner@test")
    assert report["imported"] == ["PRIMER25"] and len(report["skipped"]) == 1
    assert campaigns.import_legacy(legacy, "owner@test")["imported"] == [], "idempotente"
    item = next(c for c in campaigns.inventory() if c["code"] == "PRIMER25")
    assert item["published_version"] is None and item["draft"]["routes"] == ["PEN_BRL"]
    assert item["draft"]["campaign_rules"]["messages"]["es"]["media_id"] == "img-es"
    # La API financiera no participa: ninguna llamada privada.
    with patch.object(brasper_api, "_integration_request", side_effect=AssertionError("sin API financiera")):
        campaigns.inventory()
        campaigns.published_active()


def _try(case_id, ref):
    try:
        campaigns.reserve(case_id, "agent@test", operation_ref=ref)
        return 1
    except campaigns.BenefitRejected:
        return 0


def _accept(campaign_id, cid, amount=1000.0, ruta="PEN->BRL", gross=30.0, version=None):
    """Cotización vigente con la promoción aceptada -> expediente nuevo (como en el checkout)."""
    from core import cases, util
    if version is None:
        with db.connect() as con:
            version = dict(con.execute("SELECT published_version FROM campaigns WHERE id=?", (campaign_id,)).fetchone())["published_version"]
    current = cases.active_case(cid)
    if current:
        cases.close(current["id"], "test", cancelled=True)
    db.merge_lead_data(cid, {"ruta": ruta, "modo": "send", "monto_enviar": amount, "monto_recibir": round(amount * 1.4, 2),
                             "tasa": 1.4, "comision_bruta": gross, "comision": gross, "comision_tasa": 3.0,
                             "cotizado_en": util.now_iso(),
                             "campaign_estimate": {"campaign_id": campaign_id, "version": version, "saving": 1.0}})
    return cases.open_case(cid)["case"]["id"]


def _reserve(campaign_id, cid, ref, note=None):
    return campaigns.reserve(_accept(campaign_id, cid), "agent@test", operation_ref=ref, verification_note=note)


def _complete(benefit_id):
    from core import cases
    row = campaigns.benefit(benefit_id)
    cases.register(row["case_id"], row["operation_ref"], "agent@test")
    return campaigns.consume(benefit_id, "agent@test", "Completada según el backoffice de Brasper")


def case_and_rules_checks(client=None, owner_headers=None, wa_payload=None):
    """Expediente IA, promoción no prometida sin procedimiento verificado, vencimiento conciliado,
    estados de entrega y validaciones de rutas/moneda/decimales."""
    from core import cases, quotes
    _disable_all()
    # 1) Validaciones nuevas del borrador.
    assert _draft(discount_percentage=12.5).discount_percentage == 12.5
    for bad in ({"discount_percentage": 12.345}, {"routes": ["PEN_BRL", "BRL_PEN"], "campaign_rules": {"minimum_amount": 100}},
                {"routes": ["ALL"], "campaign_rules": {"maximum_discount": 5}}):
        try:
            _draft(**bad)
            raise AssertionError(f"debía rechazar {bad}")
        except ValueError:
            pass
    assert _draft(routes=["PEN_BRL"], campaign_rules={"minimum_amount": 100}).campaign_rules.minimum_amount == 100
    assert _draft(max_uses=None).max_uses is None, "cupo global opcional"
    try:
        campaigns.CampaignDraft.model_validate({**_draft().model_dump(mode="json"), "inventado": 1})
        raise AssertionError("campo desconocido")
    except ValueError:
        pass
    assert campaigns.estimated_saving(_draft(discount_percentage=33.33), 1000, 30) == 10.0  # Decimal ROUND_HALF_UP

    # 2) Cotización: sin procedimiento verificado no se promete el descuento; con él, ahorro estimado.
    flags = dict(features.all_flags(), campaigns=True)
    _published(name="Promo aplicable", discount_percentage=50, campaign_rules={"segment": "all"})
    cid = db.get_or_create_conversation("wa:51914000001", "whatsapp")
    db.merge_lead_data(cid, {"identity_source": "channel_phone_match", "brasper_user_id": "u-case",
                             "is_first_transfer": True, "idioma": "es"})
    with patch.object(features, "all_flags", return_value=flags), \
         patch.object(media_library, "approved", side_effect=_approved):
        from core import lead_onboarding
        with patch.object(lead_onboarding, "refresh_history", return_value=None):
            out = _run(engine.handle_message("wa:51914000001", "cotizar 1000 PEN a BRL", channel="whatsapp",
                                             conversation_id=cid))
            assert "Un asesor confirmará" in out["response"] and "ahorro estimado" not in out["response"], out["response"]
            assert db.get_lead_data(cid)["campaign_estimate"]["state"] == "pending_advisor_confirmation"
            cfg = __import__("core.tenants", fromlist=["x"]).get_config()
            with patch.dict(cfg, {"campaigns": {"discount_applicable": True}}):
                out = _run(engine.handle_message("wa:51914000001", "cotizar 1000 PEN a BRL", channel="whatsapp",
                                                 conversation_id=cid))
                assert "ahorro estimado" in out["response"], out["response"]

    # 3) Expediente: aceptar sobre cotización vigente, comprobante enlazado, registro de referencia.
    opened = cases.open_case(cid)
    assert opened["status"] in {"created", "existing"}
    case = cases.view(cases.active_case(cid))
    assert case["quote"]["ruta"] == "PEN->BRL" and case["campaign"]["campaign_id"]
    assert "Esperando comprobante del cliente" in case["pending"]
    cases.attach_proof(cid, {"provider": "whatsapp", "ref": "media-1", "kind": "image"})
    cases.attach_proof(cid, {"provider": "whatsapp", "ref": "media-1", "kind": "image"})
    case = cases.view(cases.active_case(cid))
    assert case["status"] == "proof_received" and len(case["proofs"]) == 1
    assert db.get_lead_data(cid).get("proof_validated") in (None, False), "un comprobante no confirma el pago"
    db.set_conversation_status(cid, "closed")
    assert cases.active_case(cid)["status"] == "proof_received", "cerrar el chat no cambia el expediente"
    registered = cases.register(case["id"], "PxB-9001", "agent@test")
    assert registered["status"] == "registered" and registered["operation_ref"] == "PxB-9001"
    try:
        cases.register(case["id"], "PxB-9002", "agent@test")
        raise AssertionError("no se registra dos veces")
    except ValueError:
        pass
    # Cotización vencida: no se acepta el snapshot.
    old = (datetime.now(timezone.utc) - timedelta(minutes=quotes._tc_validity_minutes() + 1)).isoformat()
    cid2 = db.get_or_create_conversation("wa:51914000002", "whatsapp")
    db.merge_lead_data(cid2, {"ruta": "PEN->BRL", "monto_enviar": 100, "monto_recibir": 150, "tasa": 1.5,
                              "cotizado_en": old})
    assert cases.open_case(cid2)["status"] == "quote_expired" and cases.active_case(cid2) is None

    # 4) Vencimiento conciliado de una reserva, con historial de transiciones; libera el cupo.
    ft = _published(name="Primer envío V", max_uses=1)
    cid3 = db.get_or_create_conversation("wa:51914000003", "whatsapp")
    db.merge_lead_data(cid3, {"identity_source": "channel_phone_match", "brasper_user_id": "u-exp",
                              "is_first_transfer": True})
    b = _reserve(ft["id"], cid3, "PxB-700")
    try:
        campaigns.expire(b["id"], "agent@test", "")
        raise AssertionError("requiere nota de conciliación")
    except campaigns.BenefitRejected:
        pass
    campaigns.expire(b["id"], "agent@test", "La operación nunca se registró en Brasper")
    assert [t["to_state"] for t in campaigns.transitions(b["id"])] == ["reserved", "expired"]
    assert _reserve(ft["id"], cid3, "PxB-701")["state"] == "reserved", "cupo liberado"

    # 5) Estados de entrega de la oferta: preparado -> enviado / solo texto / incierto.
    from core import campaign_offers
    rows = campaign_offers.offered(cid)
    assert rows and rows[0]["state"] in {"prepared", "sent", "text_only", "uncertain", "failed"}
    key = rows[0]["delivery_key"]
    with db.connect() as con:
        con.execute("UPDATE campaign_offers SET state='prepared' WHERE delivery_key=?", (key,))
    campaign_offers.mark_delivery(key, {"sent": False, "reason": "TimeoutError"})
    assert campaign_offers.offered(cid)[0]["state"] == "uncertain"
    campaign_offers.mark_delivery(key, {"sent": True})
    assert campaign_offers.offered(cid)[0]["state"] == "uncertain", "un estado final no se reescribe"
    _disable_all()


def review_regression_checks():
    """Revisión 10 oct: P1 tabla de ofertas anterior, P2 reserva ligada al expediente, P3 snapshot."""
    import tempfile
    from pathlib import Path
    from core import campaign_offers, cases, quotes, util
    _disable_all()

    # P1) Tabla de ofertas del diseño anterior (8 columnas) con datos: se repara sin perder ni reenviar.
    original = db.DB_PATH
    try:
        db.DB_PATH = Path(tempfile.mkdtemp(prefix="legacy_offers_")) / "legacy.db"
        db.init_db()
        with db.connect() as con:
            con.execute("DROP TABLE campaign_offers")
            con.execute("CREATE TABLE campaign_offers (subject TEXT NOT NULL, coupon_id TEXT NOT NULL, version INTEGER NOT NULL, "
                        "conversation_id TEXT NOT NULL, language TEXT NOT NULL, asset_id TEXT, asset_version INTEGER, "
                        "offered_at TEXT NOT NULL, PRIMARY KEY(subject, coupon_id, version))")
            con.execute("INSERT INTO campaign_offers VALUES ('contact-x','camp-old',1,'c-old','es',NULL,NULL,'2026-10-01')")
        campaign_offers.ensure_schema()
        campaign_offers.ensure_schema()  # idempotente
        with db.connect() as con:
            old = dict(con.execute("SELECT * FROM campaign_offers WHERE subject='contact-x'").fetchone())
        assert old["state"] == "legacy_unverified" and old["delivery_key"] and old["updated_at"] == "2026-10-01", old
        cid = db.get_or_create_conversation("legacy-offer-user", "webchat")
        offer = {"coupon_id": "camp-new", "published_version": 1,
                 "messages": {"es": {"text": "Promo", "media_id": None}, "pt": {"text": "Promo", "media_id": None}}}
        assert campaign_offers._record(cid, offer, "es", with_disclaimer=False), "el registro nuevo funciona"
        campaign_offers.mark_delivery(old["delivery_key"], {"sent": True})
        with db.connect() as con:
            state = dict(con.execute("SELECT state FROM campaign_offers WHERE subject='contact-x'").fetchone())["state"]
        assert state == "legacy_unverified", "una oferta antigua no se marca enviada"
    finally:
        db.DB_PATH = original

    # P2) Reserva ligada al expediente y a la versión aceptada.
    def person(ref, user, doc):
        cid = db.get_or_create_conversation(ref, "whatsapp")
        db.merge_lead_data(cid, {"identity_source": "channel_phone_match", "brasper_user_id": user,
                                 "is_first_transfer": True, "tipo_documento": "dni", "numero_documento": doc})
        return cid

    def rejected(fn, label):
        try:
            fn()
            raise AssertionError(label)
        except campaigns.BenefitRejected:
            pass

    only_pen = _published(name="Solo PEN a BRL", routes=["PEN_BRL"], campaign_rules={"segment": "all", "minimum_amount": 500})
    c1 = person("wa:51915000001", "u-p2a", "70000001")
    rejected(lambda: campaigns.reserve(_accept(only_pen["id"], c1, ruta="BRL->PEN"), "a@t", operation_ref="PxB-801"),
             "ruta incompatible")
    rejected(lambda: campaigns.reserve(_accept(only_pen["id"], c1, amount=100), "a@t", operation_ref="PxB-802"),
             "monto fuera de límites")
    case_ok = _accept(only_pen["id"], c1, amount=1000, gross=30)
    rejected(lambda: campaigns.reserve(case_ok, "a@t", operation_ref="PxB-803", campaign_id="otra"), "campaña distinta")
    # Republicada después de la aceptación: exige volver a cotizar y aceptar.
    with patch.object(media_library, "approved", side_effect=_approved):
        v2 = campaigns.save(_draft(name="Solo PEN a BRL", routes=["PEN_BRL"],
                                   campaign_rules={"segment": "all", "minimum_amount": 500}, discount_percentage=60),
                            "owner@test", only_pen["id"], 1)
        campaigns.publish(only_pen["id"], v2["version"], "owner@test", routes_available=ROUTES)
    rejected(lambda: campaigns.reserve(case_ok, "a@t", operation_ref="PxB-804"), "versión republicada")
    reaccepted = _accept(only_pen["id"], c1, amount=1000, gross=30)
    b = campaigns.reserve(reaccepted, "a@t", operation_ref="PxB-805")
    row = campaigns.benefit(b["id"])
    assert row["case_id"] == reaccepted and row["campaign_version"] == v2["version"]
    assert (row["commission_gross"], row["discount"], row["commission_final"]) == (30.0, 18.0, 12.0), row
    # Expediente sin promoción aceptada y cotización vencida.
    c2 = person("wa:51915000002", "u-p2b", "70000002")
    db.merge_lead_data(c2, {"ruta": "PEN->BRL", "monto_enviar": 1000, "monto_recibir": 1400, "tasa": 1.4,
                            "comision_bruta": 30, "cotizado_en": util.now_iso(), "campaign_estimate": None}, allow_null=True)
    plain = cases.open_case(c2)["case"]["id"]
    rejected(lambda: campaigns.reserve(plain, "a@t", operation_ref="PxB-806"), "sin promoción aceptada")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=quotes._tc_validity_minutes() + 1)).isoformat()
    c3 = person("wa:51915000003", "u-p2c", "70000003")
    db.merge_lead_data(c3, {"ruta": "PEN->BRL", "monto_enviar": 1000, "monto_recibir": 1400, "tasa": 1.4,
                            "comision_bruta": 30, "cotizado_en": stale,
                            "campaign_estimate": {"campaign_id": only_pen["id"], "version": v2["version"]}})
    assert cases.open_case(c3)["status"] == "quote_expired" and cases.active_case(c3) is None

    # P3) Snapshot con desglose; nueva cotización sin campaña borra la anterior; concurrencia de expedientes.
    snap = cases.view(cases.get(reaccepted))
    assert snap["quote"]["comision_bruta"] == 30 and "comision" in snap["quote"]
    assert snap["campaign"]["campaign_id"] == only_pen["id"]
    _disable_all()
    c4 = person("wa:51915000004", "u-p3", "70000004")
    db.merge_lead_data(c4, {"campaign_estimate": {"campaign_id": "vieja", "version": 1}})
    flags = dict(features.all_flags(), campaigns=True)
    with patch.object(features, "all_flags", return_value=flags):
        from core import lead_onboarding
        with patch.object(lead_onboarding, "refresh_history", return_value=None):
            _run(engine.handle_message("wa:51915000004", "cotizar 500 PEN a BRL", channel="whatsapp", conversation_id=c4))
    lead4 = db.get_lead_data(c4)
    assert lead4.get("campaign_estimate") is None and lead4.get("comision_bruta") is not None, lead4
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: cases.open_case(c4), range(6)))
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM sales_cases WHERE conversation_id=? AND status IN "
                        "('accepted','proof_received','registered')", (c4,)).fetchone()[0]
    assert n == 1, n
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i: cases.attach_proof(c4, {"provider": "whatsapp", "ref": f"m-{i}", "kind": "image"}), range(6)))
    assert len(cases.view(cases.active_case(c4))["proofs"]) == 6, "ningún comprobante perdido"

    # P3) Selección por ahorro efectivo después de topes (no por prioridad nominal).
    capped = _published(name="50 con tope 5", discount_percentage=50, routes=["PEN_BRL"],
                        campaign_rules={"segment": "all", "priority": 90, "maximum_discount": 5})
    plain30 = _published(name="30 sin tope", discount_percentage=30, routes=["PEN_BRL"],
                         campaign_rules={"segment": "all", "priority": 1})
    lead = {"identity_source": "channel_phone_match", "brasper_user_id": "u-sel", "is_first_transfer": True}
    pick = campaigns.for_quote(lead, "PEN", "BRL", 1000, 30)
    assert pick["campaign_id"] == plain30["id"] and pick["saving"] == 9.0, (pick["draft"].name, pick["saving"])
    assert campaigns.for_quote(lead, "PEN", "BRL", 100, 10)["campaign_id"] == capped["id"], "con comisión baja gana el 50"
    _disable_all()

