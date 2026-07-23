"""Suite de verificacion de produccion — SIN pytest y SIN gastar LLM real.

Ejecutar:
    cd backend && ../.venv/bin/python tests/run_checks.py

Usa asserts planos. Imprime PASS/FAIL por caso. sys.exit(1) si algo falla.

Antes de tocar core.db se apunta DB_PATH a un archivo temporal (base limpia y
aislada). El LLM se monkeypatchea con un stub async; ademas el caso de handoff
no llega a llamar al LLM (corte determinista en engine.handle_message).
"""
import asyncio
import hashlib
import hmac
import os
import sys
import tempfile
from pathlib import Path

# --- Aislar la ejecucion: raiz de backend/ en sys.path y DB temporal ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Forzar entorno hermetico (SQLite temporal, sin Redis, tenants desde JSON) aunque
# backend/.env defina Postgres/Redis/DB: load_dotenv en core.tenants los re-inyectaria
# si estuvieran ausentes, asi que los fijamos vacios (override=False no los pisa).
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["TENANTS_SOURCE"] = ""
# El gate corre hermético (SQLite + seed demo). Si backend/.env trae APP_ENV=production
# (p.ej. tras copiar .env.example), sin esto los endpoints rechazarían SQLite y no se
# sembraría el asesor demo. Los casos que necesitan 'production' lo fijan localmente.
os.environ["APP_ENV"] = "development"

# DB temporal ANTES de init_db (import de core.db no crea la DB por si mismo).
from core import db  # noqa: E402

_TMP_DB = Path(tempfile.mkdtemp(prefix="prod_checks_")) / "test_plataforma.db"
db.DB_PATH = _TMP_DB
db.init_db()

from core import auth as auth_mod  # noqa: E402
from core import engine, whatsapp  # noqa: E402
from core import connectors, debounce, jobs, redis_runtime  # noqa: E402
from core import llm  # noqa: E402
from core import observability  # noqa: E402
from core import telegram  # noqa: E402
from core import audio_adapter  # noqa: E402
from core import quotes, brasper_api, lead_onboarding  # noqa: E402
from core import tenants as T  # noqa: E402
import backup  # noqa: E402


# --- Reporte de casos ---
_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        _RESULTS.append((name, True, ""))
    except AssertionError as e:
        _RESULTS.append((name, False, f"assert: {e}"))
    except Exception as e:  # noqa: BLE001
        _RESULTS.append((name, False, f"{type(e).__name__}: {e}"))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Caso 1: aislamiento cruzado entre tenants
# ---------------------------------------------------------------------------
def case_isolation():
    cid = db.get_or_create_conversation("brasper", "user-iso", "webchat")
    db.add_message("brasper", cid, "user", "hola brasper")
    db.add_message("brasper", cid, "assistant", "hola de vuelta")

    # brasper si ve sus propios mensajes
    own = db.get_messages("brasper", cid)
    assert len(own) == 2, f"brasper deberia ver 2 mensajes, vio {len(own)}"

    # clinica_demo NO ve la conversacion de brasper por el mismo cid
    cross = db.get_messages("clinica_demo", cid)
    assert cross == [], f"clinica_demo no deberia ver mensajes de brasper, vio {cross}"

    # list_conversations de clinica_demo no incluye esa conversacion
    clinica_convs = db.list_conversations("clinica_demo")
    assert all(c["id"] != cid for c in clinica_convs), \
        "list_conversations(clinica_demo) no debe incluir la conversacion de brasper"


# ---------------------------------------------------------------------------
# Caso 2: handoff determinista (no usa LLM)
# ---------------------------------------------------------------------------
def case_handoff():
    tenant = T.get_tenant("brasper")
    assert tenant is not None, "tenant brasper no encontrado"
    out = _run(engine.handle_message("user-handoff", "quiero un asesor"))
    assert out["handoff"] is True, f"handoff deberia ser True, fue {out['handoff']}"
    assert out["usage"] is None, f"usage deberia ser None en handoff, fue {out['usage']}"
    # Con takeover el asesor atiende DENTRO del bot: el mensaje lo anuncia y no
    # deriva a un WhatsApp externo.
    assert "asesor" in out["response"].lower(), \
        f"la respuesta de handoff debe mencionar al asesor, fue: {out['response']!r}"
    assert "wa.me" not in out["response"], \
        f"handoff no debe empujar a WhatsApp externo, fue: {out['response']!r}"


# ---------------------------------------------------------------------------
# Caso 3: persistencia + orden cronologico
# ---------------------------------------------------------------------------
def case_persistence_order():
    cid = db.get_or_create_conversation("brasper", "user-order", "webchat")
    db.add_message("brasper", cid, "user", "primero")
    db.add_message("brasper", cid, "assistant", "segundo")
    db.add_message("brasper", cid, "user", "tercero")
    hist = db.get_history("brasper", cid, limit=12)
    contents = [m["content"] for m in hist]
    assert contents == ["primero", "segundo", "tercero"], \
        f"historial fuera de orden cronologico: {contents}"


# ---------------------------------------------------------------------------
# Caso 4: medicion — usage_summary agrega por tenant y suma costo
# ---------------------------------------------------------------------------
def case_usage_measurement():
    db.add_usage("brasper", None, "deepseek", "deepseek-chat", 100, 50, 0.001)
    db.add_usage("brasper", None, "deepseek", "deepseek-chat", 200, 80, 0.002)
    db.add_usage("clinica_demo", None, "deepseek", "deepseek-chat", 300, 90, 0.005)

    summary = db.usage_summary()
    by_tenant = {r["tenant_id"]: r for r in summary}
    assert "brasper" in by_tenant, "usage_summary no incluye brasper"
    assert "clinica_demo" in by_tenant, "usage_summary no incluye clinica_demo"

    b = by_tenant["brasper"]
    assert b["calls"] == 2, f"brasper deberia tener 2 calls, tiene {b['calls']}"
    assert b["tokens_in"] == 300, f"brasper tokens_in esperado 300, fue {b['tokens_in']}"
    assert b["tokens_out"] == 130, f"brasper tokens_out esperado 130, fue {b['tokens_out']}"
    assert abs(b["cost_usd"] - 0.003) < 1e-9, f"brasper cost esperado 0.003, fue {b['cost_usd']}"

    c = by_tenant["clinica_demo"]
    assert c["calls"] == 1, f"clinica_demo deberia tener 1 call, tiene {c['calls']}"
    assert abs(c["cost_usd"] - 0.005) < 1e-9, f"clinica_demo cost esperado 0.005, fue {c['cost_usd']}"

    # filtrado por tenant
    only_b = db.usage_summary("brasper")
    assert len(only_b) == 1 and only_b[0]["tenant_id"] == "brasper", \
        f"usage_summary('brasper') deberia devolver solo brasper, fue {only_b}"


# ---------------------------------------------------------------------------
# Caso 5: conversation_id puede repetirse entre tenants sin 500 ni mezcla
# ---------------------------------------------------------------------------
def case_conversation_id_scoped_by_tenant():
    same = "same-conv-id"
    b = db.get_or_create_conversation("brasper", "user-a", "webchat", same)
    c = db.get_or_create_conversation("clinica_demo", "user-b", "webchat", same)
    assert b == same and c == same, f"ambos tenants deben poder usar el mismo id: {b}, {c}"
    db.add_message("brasper", same, "user", "mensaje brasper")
    db.add_message("clinica_demo", same, "user", "mensaje clinica")
    own_b = db.get_messages("brasper", same)
    own_c = db.get_messages("clinica_demo", same)
    assert [m["content"] for m in own_b] == ["mensaje brasper"], own_b
    assert [m["content"] for m in own_c] == ["mensaje clinica"], own_c


# ---------------------------------------------------------------------------
# Caso 6: resolve_by_phone_number_id
# ---------------------------------------------------------------------------
def case_resolve_pnid():
    # brasper usa phone_number_id_env=WA_PHONE_NUMBER_ID_BRASPER (resuelto por os.getenv)
    os.environ["WA_PHONE_NUMBER_ID_BRASPER"] = "PNID_BRASPER_123"
    try:
        t = T.resolve_by_phone_number_id("PNID_BRASPER_123")
        assert t is not None, "no resolvio ningun tenant para el pnid configurado"
        assert t["id"] == "brasper", f"esperado tenant brasper, fue {t['id']}"

        # pnid inexistente -> None
        none_t = T.resolve_by_phone_number_id("PNID_QUE_NO_EXISTE_999")
        assert none_t is None, f"pnid inexistente deberia dar None, dio {none_t}"
    finally:
        os.environ.pop("WA_PHONE_NUMBER_ID_BRASPER", None)


# ---------------------------------------------------------------------------
# Caso 7: whatsapp.parse_incoming con payload de Meta de ejemplo
# ---------------------------------------------------------------------------
def case_parse_incoming():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "51900000000",
                                "phone_number_id": "PNID_META_777",
                            },
                            "messages": [
                                {
                                    "from": "51955512345",
                                    "id": "wamid.ABC",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Hola, quiero cotizar un envio"},
                                },
                                {
                                    "from": "51955599999",
                                    "id": "wamid.AUD",
                                    "timestamp": "1710000001",
                                    "type": "audio",
                                    "audio": {"id": "MEDIA_123", "mime_type": "audio/ogg"},
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }
    msgs = whatsapp.parse_incoming(payload)
    assert len(msgs) == 2, f"esperado 2 mensajes (texto+audio), fue {len(msgs)}"
    by_type = {m["type"]: m for m in msgs}
    t = by_type["text"]
    assert t["phone_number_id"] == "PNID_META_777", f"phone_number_id incorrecto: {t}"
    assert t["from"] == "51955512345", f"from incorrecto: {t}"
    assert t["text"] == "Hola, quiero cotizar un envio", f"text incorrecto: {t}"
    # El audio no trae 'text' (el webhook debe ramificar por type y no acceder a msg['text']).
    a = by_type["audio"]
    assert a["media_id"] == "MEDIA_123", f"media_id incorrecto: {a}"
    assert a["mime_type"] == "audio/ogg", f"mime_type incorrecto: {a}"
    assert "text" not in a, f"el audio no debe tener 'text': {a}"


# ---------------------------------------------------------------------------
# Caso 8: API protegida con RBAC + tenant_scope
# ---------------------------------------------------------------------------
def case_api_auth_and_scope():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    assert client.get("/api/tenants").status_code == 401, "tenants debe exigir token"
    assert client.get("/api/usage").status_code == 401, "usage debe exigir token"

    owner = {"X-Auth-Token": "demo-owner"}
    r = client.get("/api/tenants", headers=owner)
    assert r.status_code == 200, f"owner deberia listar tenants, status={r.status_code}"
    assert len(r.json()["tenants"]) >= 2, "owner debe ver todos los tenants activos"

    agent = {"X-Auth-Token": "demo-agent-brasper"}
    r = client.get("/api/tenants", headers=agent)
    assert r.status_code == 200, f"agent deberia listar sus tenants, status={r.status_code}"
    ids = [t["id"] for t in r.json()["tenants"]]
    assert ids == ["brasper"], f"agent deberia ver solo brasper, vio {ids}"

    r = client.get("/api/clinica_demo/conversations", headers=agent)
    assert r.status_code == 403, "agent brasper no debe leer clinica_demo"

    billing = {"X-Auth-Token": "demo-billing"}
    r = client.post("/api/brasper/chat", json={"message": "hola"}, headers=billing)
    assert r.status_code == 403, "billing no debe usar chat:test"


# ---------------------------------------------------------------------------
# Caso 9: firma del webhook WhatsApp
# ---------------------------------------------------------------------------
def case_webhook_signature():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    raw = b'{"object":"whatsapp_business_account","entry":[]}'

    os.environ["WHATSAPP_REQUIRE_SIGNATURE"] = "true"
    os.environ["WHATSAPP_APP_SECRET"] = "secret_test"
    try:
        assert client.post("/webhook", content=raw).status_code == 403, \
            "webhook sin firma debe fallar si se exige firma"
        sig = "sha256=" + hmac.new(b"secret_test", raw, hashlib.sha256).hexdigest()
        r = client.post("/webhook", content=raw,
                        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
        assert r.status_code == 200, f"webhook con firma valida debe pasar, status={r.status_code}"
    finally:
        os.environ.pop("WHATSAPP_REQUIRE_SIGNATURE", None)
        os.environ.pop("WHATSAPP_APP_SECRET", None)


# ---------------------------------------------------------------------------
# Caso 10: Telegram webhook exige secret en produccion
# ---------------------------------------------------------------------------
def case_telegram_secret_in_production():
    from fastapi.testclient import TestClient
    from main import app

    async def _fake_process_update(body):
        return {"handled": True}

    old_pu = telegram.process_update  # se restaura en finally: no filtrar el mock a otros casos
    telegram.process_update = _fake_process_update
    client = TestClient(app)
    raw = {"message": {"chat": {"id": 1}, "text": "hola"}}

    old_env = os.environ.get("APP_ENV")
    old_secret = os.environ.get("TELEGRAM_SECRET_BRASPER")
    os.environ["APP_ENV"] = "production"
    os.environ.pop("TELEGRAM_SECRET_BRASPER", None)
    try:
        r = client.post("/telegram/webhook/brasper", json=raw)
        assert r.status_code == 503, f"sin secret en prod debe ser 503, fue {r.status_code}"
        os.environ["TELEGRAM_SECRET_BRASPER"] = "tg-secret"
        r = client.post("/telegram/webhook/brasper", json=raw)
        assert r.status_code == 403, f"con secret pero sin header debe ser 403, fue {r.status_code}"
        r = client.post("/telegram/webhook/brasper", json=raw,
                        headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
        assert r.status_code == 200, f"con header correcto debe ser 200, fue {r.status_code}"
        r = client.post("/telegram/webhook", json=raw,
                        headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
        assert r.status_code == 200, f"ruta single-tenant debe aceptar webhook, fue {r.status_code}"
        r = client.post("/telegram/webhook/otro", json=raw,
                        headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
        assert r.status_code == 404, f"tenant desconocido debe rechazarse, fue {r.status_code}"
    finally:
        telegram.process_update = old_pu
        if old_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = old_env
        if old_secret is None:
            os.environ.pop("TELEGRAM_SECRET_BRASPER", None)
        else:
            os.environ["TELEGRAM_SECRET_BRASPER"] = old_secret


# ---------------------------------------------------------------------------
# Caso 11: tenants en DB con bootstrap desde JSON
# ---------------------------------------------------------------------------
def case_tenant_store_database_mode():
    old_source = os.environ.get("TENANTS_SOURCE")
    os.environ["TENANTS_SOURCE"] = "database"
    try:
        T.ensure_store(overwrite=True)
        tenants = T.all_tenants(include_inactive=True)
        assert "brasper" in tenants, "bootstrap DB debe incluir brasper"

        created = T.upsert_tenant_config("tienda_demo", {
            "name": "Tienda Demo",
            "vertical": "Retail",
            "active": True,
            "fee_usd": 100,
            "llm": {"provider": "deepseek", "model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY"},
            "system_prompt": "Responde breve.",
        })
        assert created["id"] == "tienda_demo", created
        assert T.get_tenant("tienda_demo")["name"] == "Tienda Demo"

        patched = T.patch_tenant_config("tienda_demo", {"vertical": "Ecommerce"})
        assert patched["vertical"] == "Ecommerce", patched

        paused = T.set_tenant_active("tienda_demo", False)
        assert paused["active"] is False, paused
        assert T.get_tenant("tienda_demo") is None, "tenant pausado no debe estar activo"
        assert T.get_tenant("tienda_demo", include_inactive=True)["active"] is False

        refs = T.set_secret_refs("tienda_demo", {"telegram.secret_token_env": "TELEGRAM_SECRET_TIENDA"})
        assert refs["telegram"]["secret_token_env"] == "TELEGRAM_SECRET_TIENDA", refs
    finally:
        if old_source is None:
            os.environ.pop("TENANTS_SOURCE", None)
        else:
            os.environ["TENANTS_SOURCE"] = old_source


# ---------------------------------------------------------------------------
# Caso 12: Admin API de tenants + rechazo de secretos crudos en produccion
# ---------------------------------------------------------------------------
def case_admin_tenant_api():
    from fastapi.testclient import TestClient
    from main import app

    old_source = os.environ.get("TENANTS_SOURCE")
    old_env = os.environ.get("APP_ENV")
    os.environ["TENANTS_SOURCE"] = "database"
    T.ensure_store(overwrite=True)
    client = TestClient(app)
    owner = {"X-Auth-Token": "demo-owner"}

    body = {
        "id": "admin_demo",
        "config": {
            "name": "Admin Demo",
            "vertical": "Servicios",
            "active": True,
            "llm": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key_env": "DEEPSEEK_API_KEY",
            },
            "system_prompt": "Asistente de prueba.",
        },
    }
    try:
        r = client.post("/api/admin/tenants", json=body, headers=owner)
        assert r.status_code == 200, f"crear tenant debe pasar, status={r.status_code}, body={r.text}"
        assert r.json()["tenant"]["id"] == "admin_demo"

        r = client.patch("/api/admin/tenants/admin_demo",
                         json={"config": {"vertical": "Servicios B2B"}}, headers=owner)
        assert r.status_code == 200, f"patch tenant debe pasar, status={r.status_code}, body={r.text}"
        assert r.json()["tenant"]["vertical"] == "Servicios B2B"

        r = client.post("/api/admin/tenants/admin_demo/pause", headers=owner)
        assert r.status_code == 200 and r.json()["tenant"]["active"] is False, r.text
        r = client.post("/api/admin/tenants/admin_demo/resume", headers=owner)
        assert r.status_code == 200 and r.json()["tenant"]["active"] is True, r.text

        r = client.post("/api/admin/tenants/admin_demo/secrets",
                        json={"refs": {"llm.api_key_env": "OPENAI_API_KEY_ADMIN_DEMO"}, "note": "rotacion test"},
                        headers=owner)
        assert r.status_code == 200, f"secret refs debe pasar, status={r.status_code}, body={r.text}"
        assert r.json()["tenant"]["llm"]["api_key_env"] == "OPENAI_API_KEY_ADMIN_DEMO"
        r = client.get("/api/admin/tenants/admin_demo/secrets/rotations", headers=owner)
        assert r.status_code == 200, f"rotations debe pasar, status={r.status_code}, body={r.text}"
        rotations = r.json()["rotations"]
        assert rotations and rotations[0]["secret_path"] == "llm.api_key_env", rotations
        assert rotations[0]["env_name"] == "OPENAI_API_KEY_ADMIN_DEMO", rotations
        assert "sk-" not in rotations[0]["env_name"], rotations

        os.environ["APP_ENV"] = "production"
        raw_secret = {
            "id": "raw_secret_demo",
            "config": {"name": "Raw Secret", "llm": {"api_key": "sk-nope"}},
        }
        r = client.post("/api/admin/tenants", json=raw_secret, headers=owner)
        assert r.status_code == 422, f"secret crudo en prod debe rechazarse, fue {r.status_code}"

        os.environ.pop("APP_ENV", None)
        invalid = {
            "id": "tenant_invalido",
            "config": {"name": "Tenant Invalido", "active": True},
        }
        r = client.post("/api/admin/tenants", json=invalid, headers=owner)
        assert r.status_code == 422, f"tenant activo incompleto debe rechazarse, fue {r.status_code}"
    finally:
        if old_source is None:
            os.environ.pop("TENANTS_SOURCE", None)
        else:
            os.environ["TENANTS_SOURCE"] = old_source
        if old_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = old_env


# ---------------------------------------------------------------------------
# Caso 13: LangGraph ruta LLM con stub, persistencia y usage
# ---------------------------------------------------------------------------
def case_langgraph_llm_path():
    tenant = T.get_tenant("brasper")
    assert tenant is not None, "tenant brasper no encontrado"
    # Sin señal de cotización (eso ahora lo captura el cotizador determinista, caso 26).
    out = _run(engine.handle_message("user-langgraph", "hola, que documentos necesito?"))
    assert out["handoff"] is False, out
    assert out["response"] == "[respuesta simulada]", out
    assert out["usage"]["model"] == tenant.get("llm", {}).get("model"), out["usage"]
    msgs = db.get_messages("brasper", out["conversation_id"])
    assert [m["role"] for m in msgs][-2:] == ["user", "assistant"], msgs
    summary = db.usage_summary("brasper")
    assert summary and summary[0]["calls"] >= 1, summary


# ---------------------------------------------------------------------------
# Caso 14: Redis runtime cae seguro sin REDIS_URL
# ---------------------------------------------------------------------------
def case_redis_runtime_without_redis():
    assert redis_runtime.configured() is False
    token = redis_runtime.acquire_lock("test:lock")
    assert token == "local-no-redis", token
    redis_runtime.release_lock("test:lock", token)
    assert jobs.enqueue("noop", {"ok": True}) is False
    os.environ["CHANNEL_DEBOUNCE_SECONDS"] = "2"
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    redis_runtime._CLIENT = None
    try:
        assert debounce.enabled() is True  # configurado por env, aunque Redis no responda en tests
        assert debounce.buffer_message("t", "webchat", "u", "hola", {}) is False
    finally:
        os.environ.pop("CHANNEL_DEBOUNCE_SECONDS", None)
        os.environ.pop("REDIS_URL", None)
        redis_runtime._CLIENT = None


# ---------------------------------------------------------------------------
# Caso 15: ToolRouter ejecuta conector externo desde LangGraph sin LLM
# ---------------------------------------------------------------------------
def case_tool_router_path():
    tenant = T.get_tenant("brasper")
    assert tenant is not None, "tenant brasper no encontrado"

    async def _fake_call_endpoint(tenant_arg, connector_key, tool_name, variables):
        assert tenant_arg["id"] == "brasper"
        assert connector_key == "erp_demo"
        assert tool_name == "consultar_stock"
        assert variables["sku"] == "SKU123"
        return {"ok": True, "status": 200, "data": {"sku": variables["sku"], "stock": 7}}

    captured: dict = {}

    async def _capture_chat(tenant_arg, messages):
        captured["messages"] = messages
        return await old_chat(tenant_arg, messages)

    old_call = connectors.call_endpoint
    old_chat = llm.chat
    connectors.call_endpoint = _fake_call_endpoint
    llm.chat = _capture_chat
    try:
        out = _run(engine.handle_message(
            "user-tool",
            "consulta stock sku SKU123",
            channel="webchat",
        ))
        assert out["handoff"] is False, out
        # El resultado del conector se le pasa al LLM para redactar (no JSON crudo).
        joined = " ".join(m["content"] for m in captured.get("messages", []))
        assert "consultar_stock" in joined and "SKU123" in joined and "7" in joined, joined
        # Al pasar por el LLM, ahora se mide consumo (antes era None).
        assert out["usage"] is not None, out
        assert out["response"], out
    finally:
        connectors.call_endpoint = old_call
        llm.chat = old_chat


# ---------------------------------------------------------------------------
# Caso 16: CalendarAdapter agenda cita desde LangGraph sin LLM
# ---------------------------------------------------------------------------
def case_calendar_appointment_path():
    tenant = T.get_tenant("clinica_demo")
    assert tenant is not None, "tenant clinica_demo no encontrado"
    out = _run(engine.handle_message(
        "patient-1",
        "quiero agendar cita nombre Juan Perez dni 12345678 especialidad odontologia 2026-07-10 10:30",
        channel="webchat",
    ))
    assert out["handoff"] is False, out
    assert out["usage"] is None, out
    assert "Cita reservada" in out["response"], out["response"]
    appts = db.list_appointments("clinica_demo")
    assert appts, "debe crear una cita"
    assert appts[0]["patient_name"] == "Juan Perez", appts[0]
    assert appts[0]["document_id"] == "12345678", appts[0]
    assert "odontolog" in appts[0]["specialty"].lower(), appts[0]


# ---------------------------------------------------------------------------
# Caso 17: Observabilidad expone metricas protegidas y redacta secretos
# ---------------------------------------------------------------------------
def case_observability_metrics():
    from fastapi.testclient import TestClient
    from main import app

    redacted = observability._redact({"api_key": "sk-test", "nested": {"token": "abc", "ok": True}})
    assert redacted["api_key"] == "***", redacted
    assert redacted["nested"]["token"] == "***", redacted
    assert redacted["nested"]["ok"] is True, redacted
    not_secret = observability._redact({"tokens_in": 10, "tokens_out": 5})
    assert not_secret["tokens_in"] == 10 and not_secret["tokens_out"] == 5, not_secret

    client = TestClient(app)
    assert client.get("/api/ops/metrics").status_code == 401, "metrics debe exigir auth"
    r = client.get("/api/ops/metrics", headers={"X-Auth-Token": "demo-owner"})
    assert r.status_code == 200, f"metrics owner debe pasar, status={r.status_code}"
    data = r.json()
    assert "usage" in data and "conversations" in data and "appointments" in data, data
    assert client.get("/api/ops/alerts").status_code == 401, "alerts debe exigir auth"
    r = client.get("/api/ops/alerts", headers={"X-Auth-Token": "demo-owner"})
    assert r.status_code == 200, f"alerts owner debe pasar, status={r.status_code}"
    assert isinstance(r.json()["alerts"], list), r.json()


# ---------------------------------------------------------------------------
# Caso 18: Backup SQLite local crea archivo restaurable
# ---------------------------------------------------------------------------
def case_sqlite_backup_create():
    out_dir = Path(tempfile.mkdtemp(prefix="backup_check_"))
    path = backup.create_backup(out_dir)
    assert path.exists(), f"backup no creado: {path}"
    assert path.stat().st_size > 0, f"backup vacio: {path}"
    listed = backup.list_backups(out_dir)
    assert path in listed, listed


# ---------------------------------------------------------------------------
# Caso 19: Jobs retry/dead-letter caen seguro sin Redis
# ---------------------------------------------------------------------------
def case_jobs_retry_without_redis():
    assert jobs.handle_failure({"type": "x", "payload": {}}, "boom") is False
    assert jobs.dead_letter_count() == 0


def case_vertical_validation():
    base = {"name": "X", "system_prompt": "hola", "active": True,
            "llm": {"model": "m", "api_key_env": "K"}}
    errs = T.validate_tenant_config({**base, "vertical": "Salud"})
    assert any("salud" in e for e in errs), f"salud sin calendario debe fallar: {errs}"
    ok = T.validate_tenant_config({**base, "vertical": "Salud",
                                   "calendar": {"enabled": True, "specialties": ["general"]}})
    assert not any("salud" in e for e in ok), f"salud completa no debe fallar: {ok}"
    resv = T.validate_tenant_config({**base, "vertical": "Reservas"})
    assert any("reservas" in e for e in resv), f"reservas sin calendario debe fallar: {resv}"
    # retail no impone requisitos duros: un bot de FAQs es válido
    assert T.validate_tenant_config({**base, "vertical": "Retail"}) == [], \
        "retail no debe imponer requisitos de vertical"


def case_export_conversations():
    cid = db.get_or_create_conversation("brasper", "user-export", "webchat")
    db.add_message("brasper", cid, "user", "hola export")
    db.add_message("brasper", cid, "assistant", "ok")
    conv = next((c for c in db.export_conversations("brasper") if c["id"] == cid), None)
    assert conv is not None, "la conversacion exportada debe aparecer"
    assert len(conv["messages"]) == 2, f"debe traer sus 2 mensajes: {conv['messages']}"
    assert all(c["id"] != cid for c in db.export_conversations("clinica_demo")), \
        "export no debe cruzar tenants"


def case_usage_daily():
    db.add_usage("clinica_demo", None, "deepseek", "deepseek-chat", 10, 5, 0.002)
    rows = db.usage_daily("clinica_demo")
    assert rows, "usage_daily debe agregar al menos un dia"
    assert all(r["tenant_id"] == "clinica_demo" for r in rows), "usage_daily filtra por tenant"
    assert rows[0]["calls"] >= 1 and rows[0]["cost_usd"] >= 0.002


def case_production_requires_postgres_redis():
    old = {k: os.environ.get(k) for k in ("APP_ENV", "DATABASE_URL", "REDIS_URL")}
    try:
        os.environ["APP_ENV"] = "production"
        os.environ["DATABASE_URL"] = ""
        os.environ["REDIS_URL"] = ""
        try:
            db.assert_production_infra()
            raise AssertionError("produccion sin Postgres debe fallar el arranque")
        except RuntimeError as e:
            assert "Postgres" in str(e), e
        os.environ["DATABASE_URL"] = "postgresql://demo:demo@example:5432/demo"
        try:
            db.assert_production_infra()
            raise AssertionError("produccion sin Redis debe fallar el arranque")
        except RuntimeError as e:
            assert "REDIS_URL" in str(e), e
        os.environ["REDIS_URL"] = "redis://example:6379/0"
        db.assert_production_infra()  # configurado -> no lanza (no exige conexion aqui)
        os.environ["APP_ENV"] = ""
        os.environ["DATABASE_URL"] = ""
        os.environ["REDIS_URL"] = ""
        db.assert_production_infra()  # desarrollo: SQLite permitido
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def case_retention_purge():
    cid = db.get_or_create_conversation("brasper", "user-old", "webchat")
    db.add_message("brasper", cid, "user", "vieja")
    with db.connect() as con:
        con.execute("UPDATE conversations SET updated_at=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", cid))
    counts = db.purge_old_data("2001-01-01T00:00:00+00:00")
    assert counts["conversations"] >= 1, f"debe purgar la conversacion vieja: {counts}"
    assert db.get_messages("brasper", cid) == [], "sus mensajes deben borrarse"
    fresh = db.get_or_create_conversation("brasper", "user-fresh", "webchat")
    db.purge_old_data("2001-01-01T00:00:00+00:00")
    assert any(c["id"] == fresh for c in db.list_conversations("brasper")), \
        "no debe borrar conversaciones recientes"


def case_human_takeover():
    """En handoff el bot se calla; el asesor responde por el canal y puede devolver al bot."""
    from fastapi.testclient import TestClient
    from main import app
    tenant = T.get_tenant("brasper")

    out1 = _run(engine.handle_message("tk:1", "hola"))
    cid = out1["conversation_id"]
    assert not out1.get("paused") and out1["response"], out1

    db.set_conversation_status("brasper", cid, "handoff")  # asesor toma
    before = len(db.get_messages("brasper", cid))
    out2 = _run(engine.handle_message("tk:1", "sigo ahi?", conversation_id=cid))
    assert out2.get("paused") is True, out2
    assert (out2["response"] or "") == "" and out2["usage"] is None, out2
    msgs = db.get_messages("brasper", cid)
    assert len(msgs) == before + 1 and msgs[-1]["role"] == "user", msgs  # se guardó el user, sin respuesta del bot

    # El asesor responde por el panel -> se guarda y la conversación sigue en handoff.
    client = TestClient(app)
    r = client.post(f"/api/brasper/conversations/{cid}/reply",
                    headers={"X-Auth-Token": "demo-owner"}, json={"text": "Hola, soy tu asesor."})
    assert r.status_code == 200, r.text
    msgs2 = db.get_messages("brasper", cid)
    assert msgs2[-1]["content"] == "Hola, soy tu asesor." and msgs2[-1]["role"] == "assistant", msgs2[-1]
    assert db.conversation_status("brasper", cid) == "handoff"

    # Devolver al bot -> vuelve a responder.
    r2 = client.post(f"/api/brasper/conversations/{cid}/status",
                     headers={"X-Auth-Token": "demo-owner"}, json={"status": "active"})
    assert r2.status_code == 200, r2.text
    out3 = _run(engine.handle_message("tk:1", "hola de nuevo", conversation_id=cid))
    assert not out3.get("paused") and out3["response"], out3


def case_agent_scoping_and_images():
    """El asesor ve solo lo suyo + libres, no puede tocar lo de otro, y envía imágenes."""
    from fastapi.testclient import TestClient
    from main import app
    auth_mod.ensure_seed()
    client = TestClient(app)
    owner = {"X-Auth-Token": "demo-owner"}
    agent = {"X-Auth-Token": "demo-agent-brasper"}  # agent@brasper.com

    a = db.get_or_create_conversation("brasper", "wa:scope-A", "whatsapp")
    db.assign_conversation("brasper", a, "agent@brasper.com")
    b = db.get_or_create_conversation("brasper", "wa:scope-B", "whatsapp")
    db.assign_conversation("brasper", b, "otro@brasper.com")   # de otro asesor
    c = db.get_or_create_conversation("brasper", "tg:scope-C", "telegram")  # libre

    # Owner ve todas.
    ids_owner = {x["id"] for x in client.get("/api/brasper/conversations", headers=owner).json()["conversations"]}
    assert {a, b, c} <= ids_owner, ids_owner
    # Agente ve la suya (A) + la libre (C), NO la de otro (B).
    ids_agent = {x["id"] for x in client.get("/api/brasper/conversations", headers=agent).json()["conversations"]}
    assert a in ids_agent and c in ids_agent and b not in ids_agent, ids_agent

    # El agente NO puede responder una conversación de otro asesor.
    r = client.post(f"/api/brasper/conversations/{b}/reply", headers=agent, json={"text": "hola"})
    assert r.status_code == 403, r.text
    # El agente reclama una libre al responder (queda asignada a él).
    r = client.post(f"/api/brasper/conversations/{c}/reply", headers=agent, json={"text": "te ayudo"})
    assert r.status_code == 200, r.text
    assert db.get_conversation("brasper", c)["assigned_to"] == "agent@brasper.com"

    # Enviar imagen (por URL) -> persiste con la URL; delivery se intenta por el canal.
    r = client.post(f"/api/brasper/conversations/{a}/send-image", headers=agent,
                    json={"image_url": "https://ejemplo.com/comprobante.jpg", "caption": "tu comprobante"})
    assert r.status_code == 200, r.text
    assert any("ejemplo.com/comprobante.jpg" in m["content"] for m in db.get_messages("brasper", a))
    # URL inválida -> 422
    r = client.post(f"/api/brasper/conversations/{a}/send-image", headers=agent,
                    json={"image_url": "no-es-url"})
    assert r.status_code == 422, r.text


def case_upload_file():
    """Subida real de archivo (multipart) por el asesor: persiste + guards de tamaño/tipo."""
    from fastapi.testclient import TestClient
    from main import app
    auth_mod.ensure_seed()
    client = TestClient(app)
    owner = {"X-Auth-Token": "demo-owner"}
    cid = db.get_or_create_conversation("brasper", "tg:99001", "telegram")

    # Simula envío OK de Telegram con file_id (sin red) para probar que la media
    # SALIENTE se guarda como burbuja del asesor.
    async def _fake_upload(t, chat_id, filename, content, mime="", caption=""):
        return {"ok": True, "result": {"photo": [{"file_id": "SMALL"}, {"file_id": "SENTFILEID"}]}}
    old_upload = telegram.send_file_upload
    telegram.send_file_upload = _fake_upload
    try:
        files = {"file": ("foto.png", b"\x89PNG\r\n\x1a\n contenido de prueba", "image/png")}
        r = client.post(f"/api/brasper/conversations/{cid}/upload", headers=owner,
                        files=files, data={"caption": "tu comprobante"})
        assert r.status_code == 200, r.text
        msgs = db.get_messages("brasper", cid)
        assert any("comprobante" in m["content"] for m in msgs)
        out_media = [m for m in msgs if m["role"] == "assistant" and m.get("media")]
        assert out_media and out_media[-1]["media"]["ref"] == "SENTFILEID", \
            f"la subida saliente debe guardarse como media (burbuja del asesor): {out_media}"
        assert out_media[-1]["media"]["provider"] == "telegram", out_media[-1]
    finally:
        telegram.send_file_upload = old_upload

    # Archivo vacío -> 422
    r = client.post(f"/api/brasper/conversations/{cid}/upload", headers=owner,
                    files={"file": ("x.png", b"", "image/png")})
    assert r.status_code == 422, r.text

    # Archivo > 10 MB -> 413
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = client.post(f"/api/brasper/conversations/{cid}/upload", headers=owner,
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413, r.text


def case_incoming_media():
    """Media entrante (Telegram): se parsea, se guarda como mensaje del usuario y deriva."""
    from fastapi.testclient import TestClient
    from main import app
    tenant = T.get_tenant("brasper")

    sent: list = []
    async def _fake_send(t, chat_id, text, reply_markup=None):
        sent.append(text)
        return {"ok": True}
    old_send = telegram.send_message
    telegram.send_message = _fake_send
    try:
        # Foto entrante con caption -> media image + texto = caption
        photo = {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42},
                             "photo": [{"file_id": "small"}, {"file_id": "BIGFILEID"}],
                             "caption": "mi comprobante"}}
        parsed = telegram.parse_update(photo)
        assert parsed["media"]["kind"] == "image" and parsed["media"]["ref"] == "BIGFILEID", parsed
        assert parsed["text"] == "mi comprobante"
        r = _run(telegram.process_update(photo))
        assert r["handled"] and r.get("media") == "image", r
        cid = db.get_or_create_conversation("brasper", "tg:42", "telegram")
        media_msgs = [m for m in db.get_messages("brasper", cid) if m.get("media")]
        assert media_msgs and media_msgs[-1]["role"] == "user", media_msgs
        assert media_msgs[-1]["media"]["ref"] == "BIGFILEID", media_msgs[-1]
        assert db.conversation_status("brasper", cid) == "handoff", "media -> pasa a asesor"
        assert sent, "el usuario recibe acuse de recibo"
        assert "comprobante" in sent[-1].lower(), f"acuse debe mencionar comprobante: {sent[-1]!r}"
        # El comprobante deriva a un asesor concreto (misma ruta que el checkout).
        conv = db.get_conversation("brasper", cid)
        assert conv and conv.get("assigned_to"), f"comprobante debe asignar asesor: {conv}"

        # Documento entrante -> media document con nombre y mime
        doc = {"message": {"chat": {"id": 43, "type": "private"}, "from": {"id": 43},
                           "document": {"file_id": "DOCID", "file_name": "contrato.pdf", "mime_type": "application/pdf"}}}
        p2 = telegram.parse_update(doc)
        assert p2["media"]["kind"] == "document" and p2["media"]["name"] == "contrato.pdf", p2
    finally:
        telegram.send_message = old_send

    # El proxy de media valida el provider (sin red).
    client = TestClient(app)
    r = client.get("/api/brasper/media?provider=nope&ref=x", headers={"X-Auth-Token": "demo-owner"})
    assert r.status_code == 422, r.text


def case_telegram_private_only():
    """El bot de Telegram solo responde en chats privados; ignora grupos/canales."""
    br = T.get_tenant("brasper")
    priv = telegram.parse_update({"message": {"text": "hola", "chat": {"id": 1, "type": "private"}}})
    grp = telegram.parse_update({"message": {"text": "hola", "chat": {"id": -100, "type": "group"}}})
    assert priv["chat_type"] == "private" and grp["chat_type"] == "group", (priv, grp)
    assert telegram._allows_chat(br, "private") is True
    assert telegram._allows_chat(br, "group") is False
    assert telegram._allows_chat(br, "supergroup") is False
    # process_update ignora un grupo SIN llamar al motor ni a la red (retorna temprano).
    r = _run(telegram.process_update(br, {"message": {"text": "hola", "chat": {"id": -100, "type": "supergroup"}}}))
    assert r["handled"] is False and r.get("ignored_chat_type") == "supergroup", r
    # Con allow_groups=true, sí acepta grupos.
    br2 = {**br, "telegram": {**br.get("telegram", {}), "allow_groups": True}}
    assert telegram._allows_chat(br2, "group") is True


def case_jobs_degrade_when_redis_unreachable():
    """Regresión: encolar con Redis configurado pero inalcanzable NO debe romper."""
    old_url = os.environ.get("REDIS_URL")
    old_client = redis_runtime._CLIENT
    try:
        os.environ["REDIS_URL"] = "redis://nonexistent-redis-host-xyzzy:6379/0"
        redis_runtime._CLIENT = None  # fuerza recrear el cliente con la URL mala
        assert jobs.enqueue("tenant.changed", {"x": 1}) is False, "enqueue debe degradar a False"
        assert jobs.dead_letter_count() == 0
        assert jobs.list_dead_letter() == []
        assert jobs.handle_failure({"type": "x", "max_attempts": 1}, "boom") is False
    finally:
        redis_runtime._CLIENT = None
        if old_url is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = old_url
        redis_runtime._CLIENT = old_client


def case_quote_math():
    """Matemática del cotizador portada del bot Brasper (sin LLM, sin red)."""
    from core import quotes
    original = T.get_tenant("brasper")
    tenant = {**original, "quote": {**original["quote"], "api": {"enabled": False}}}
    assert quotes.enabled(tenant), "brasper debe tener quote.enabled"

    # Directo: 500 PEN -> comisión 3% = 15.00, cupón 10% sobre comisión = 1.50,
    # neta 13.50, convertible 486.50, tasa 1.46 -> recibe 710.29 BRL.
    q = quotes.compute(tenant, "PEN", "BRL", 500, "send")
    assert not q.get("error"), q
    assert q["commission_gross"] == 15.0, q
    assert q["coupon_savings_amount"] == 1.5, q
    assert q["commission"] == 13.5, q
    assert q["total_to_send"] == 486.5, q
    assert q["amount_receive"] == 710.29, q

    # Inverso: pedir recibir 710.29 BRL debe requerir enviar ~500 PEN.
    inv = quotes.compute(tenant, "PEN", "BRL", 710.29, "receive")
    assert not inv.get("error"), inv
    assert abs(inv["amount_send"] - 500.0) <= 0.25, inv
    assert abs(inv["amount_receive"] - 710.29) <= 0.05, inv

    # Par inválido y monto inválido.
    bad = quotes.compute(tenant, "PEN", "USD", 100, "send")
    assert bad.get("error") and "PEN" in bad["error"], bad
    zero = quotes.compute(tenant, "PEN", "BRL", 0, "send")
    assert zero.get("error"), zero


def case_quote_graph_path():
    """'Cotizar 500 PEN a BRL' -> respuesta determinista con montos, sin gastar LLM."""
    tenant = T.get_tenant("brasper")
    saved_fetch = brasper_api._fetch

    def _fake_fetch(url):
        if url.endswith("/coin/tax-rate"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "tax": "1.46"}]
        if url.endswith("/coin/commission"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "percentage": 3, "min_amount": 0, "max_amount": 500}]
        if url.endswith("/transactions/coupons/"):
            return [{"is_active": True, "coin_a": "PEN", "coin_b": "BRL", "code": "BRASPER10", "discount_percentage": 10}]
        return []

    brasper_api._fetch = _fake_fetch
    try:
        out = _run(engine.handle_message("user-quote", "Cotizar 500 PEN a BRL"))
        assert out["handoff"] is False, out
        assert out["usage"] is None, "la cotización no debe llamar al LLM"
        assert "710.29" in out["response"].replace(",", ""), out["response"]
        assert "1.4600" in out["response"], out["response"]
        assert "BRASPER10" in out["response"], out["response"]
    finally:
        brasper_api._fetch = saved_fetch

    # Cotización incompleta/ambigua -> ahora la maneja el LLM (entiende typos, guía).
    out2 = _run(engine.handle_message("user-quote", "quiero cotizar"))
    assert out2["usage"] is not None, f"incompleta debe ir al LLM: {out2}"
    assert out2["response"] == "[respuesta simulada]", out2["response"]

    # Typo en la moneda destino ('olesñ'≈soles): antes daba mensaje genérico; ahora -> LLM.
    out_typo = _run(engine.handle_message("user-quote2", "500 reales a olesñ"))
    assert out_typo["usage"] is not None, f"typo debe delegarse al LLM, no mensaje genérico: {out_typo}"

    # clinica_demo no tiene cotizador: el mismo texto va por otra ruta (LLM stub).
    clinica = T.get_tenant("clinica_demo")
    out3 = _run(engine.handle_message("user-quote", "Cotizar 500 PEN a BRL"))
    assert "710" not in out3["response"], out3["response"]

    # Señal débil sin datos ("envío" como sustantivo) NO debe caer al cotizador.
    out4 = _run(engine.handle_message("user-quote", "que documentos necesito para el envio?"))
    assert out4["response"] == "[respuesta simulada]", f"debe ir al LLM: {out4['response']}"


def case_advisor_assignment():
    """Handoff deriva la conversación al asesor con menos carga (agent@brasper.com)."""
    auth_mod.ensure_seed()
    tenant = T.get_tenant("brasper")
    out = _run(engine.handle_message("user-deriv-1", "quiero hablar con un asesor"))
    assert out["handoff"] is True, out
    convs = db.list_conversations("brasper")
    mine = [c for c in convs if c["user_ref"] == "user-deriv-1"]
    assert mine and mine[0]["assigned_to"] == "agent@brasper.com", mine
    load = db.handoff_load_by_agent("brasper")
    assert load.get("agent@brasper.com", 0) >= 1, load


def case_checkout_handoff():
    """Checkout muestra cuentas oficiales y no crea transacción ni hace handoff."""
    tenant = T.get_tenant("brasper")
    cid = db.get_or_create_conversation("brasper", "user-checkout-1", "webchat")
    db.merge_lead_data("brasper", cid, {
        "brasper_user_id": "client-1", "ruta": "PEN->BRL", "commercial_stage": "quoted"
    })
    saved = brasper_api.deposit_accounts
    brasper_api.deposit_accounts = lambda tenant_arg, currency: {"ok": True, "data": [{
        "id": "bank-1", "bank": "Banco Oficial", "company": "Brasper SAC",
        "account": "000-111", "pix": None,
    }]}
    try:
        out = _run(engine.handle_message(
            "user-checkout-1", "listo, ¿cómo pago?", conversation_id=cid
        ))
    finally:
        brasper_api.deposit_accounts = saved
    assert out["handoff"] is False, out
    assert out["usage"] is None, "checkout no debe gastar LLM"
    assert "Banco Oficial" in out["response"] and "comprobante" in out["response"].lower(), out
    assert db.get_lead_data("brasper", cid)["commercial_stage"] == "awaiting_deposit"

    # Un pedido de cotización COMPLETO (monto+monedas) NO es checkout: cotiza igual.
    out3 = _run(engine.handle_message("user-checkout-3", "quiero hacer el envío de 500 PEN a BRL"))
    assert out3["handoff"] is False, f"con monto+moneda debe cotizar, no derivar: {out3}"
    assert "710.29" in out3["response"].replace(",", ""), out3["response"]
    # El CTA de la cotización invita a continuar EN el bot (no manda a WhatsApp externo).
    assert "continuar" in out3["response"].lower(), out3["response"]
    assert "wa.me" not in out3["response"], out3["response"]


def case_client_onboarding_without_transaction():
    """Cotiza primero y pide documento solo al confirmar el envío."""
    tenant = T.get_tenant("brasper")
    saved_upsert, saved_find, saved_accounts = (
        brasper_api.upsert_client, brasper_api.find_client, brasper_api.deposit_accounts)
    calls = []
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": None, "ambiguous": False}
    brasper_api.upsert_client = lambda tenant_arg, lead: (
        calls.append(dict(lead)), {"ok": True, "data": {"id": "client-uuid", "created": True}}
    )[1]
    brasper_api.deposit_accounts = lambda *args, **kwargs: {"ok": True, "data": [{
        "id": "bank-1", "bank": "Banco Oficial", "company": "Brasper SAC", "account": "000-111"
    }]}
    try:
        assert not hasattr(brasper_api, "register_operation"), "la IA no debe exponer creación de operaciones"
        out = _run(engine.handle_message("wa:51999111222", "hola", channel="whatsapp"))
        cid = out["conversation_id"]
        assert "nombre completo" in out["response"].lower(), out
        out = _run(engine.handle_message(
            "wa:51999111222", "Ana María Pérez Soto", channel="whatsapp", conversation_id=cid
        ))
        assert "cuánto" in out["response"].lower(), out

        # La cotización no exige DNI/correo y no queda atrapada en onboarding.
        out = _run(engine.handle_message(
            "wa:51999111222", "Cotizar 500 PEN a BRL", channel="whatsapp", conversation_id=cid
        ))
        assert "cotización" in out["response"].lower() and "documento" not in out["response"].lower(), out

        out = _run(engine.handle_message(
            "wa:51999111222", "continuar", channel="whatsapp", conversation_id=cid
        ))
        assert "tipo de documento" in out["response"].lower(), out
        for answer in ("DNI", "12345678"):
            out = _run(engine.handle_message(
                "wa:51999111222", answer, channel="whatsapp", conversation_id=cid
            ))
        lead = db.get_lead_data("brasper", cid)
        assert lead["brasper_user_id"] == "client-uuid" and lead["telefono"] == "999111222", lead
        assert lead["numero_documento"] == "12345678" and calls, lead
        assert "Banco Oficial" in out["response"] and "correo" not in out["response"].lower(), out
        assert "transacci" not in out["response"].lower(), out
    finally:
        brasper_api.upsert_client, brasper_api.find_client, brasper_api.deposit_accounts = (
            saved_upsert, saved_find, saved_accounts)


def case_returning_client_by_phone():
    """WhatsApp reconoce al cliente por teléfono y no vuelve a pedir sus datos."""
    tenant = T.get_tenant("brasper")
    saved_find = brasper_api.find_client
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": {
        "id": "client-existing", "names": "Carlos", "lastnames": "García",
        "phone": 999222333, "code_phone": "+51", "document_type": "dni",
        "document_number": "87654321",
    }}
    try:
        out = _run(engine.handle_message(
            "wa:51999222333", "hola", channel="whatsapp"
        ))
        lead = db.get_lead_data("brasper", out["conversation_id"])
        assert "Carlos" in out["response"] and "nuevamente" in out["response"], out
        assert lead.get("brasper_user_id") == "client-existing", lead
        assert "documento" not in out["response"].lower(), out
    finally:
        brasper_api.find_client = saved_find


def case_deposit_failure_creates_handoff():
    """Una falla de cuentas se oculta al cliente y deriva realmente al asesor."""
    auth_mod.ensure_seed()
    tenant = T.get_tenant("brasper")
    cid = db.get_or_create_conversation("brasper", "deposit-failure", "webchat")
    db.merge_lead_data("brasper", cid, {
        "brasper_user_id": "client-1", "ruta": "PEN->BRL", "commercial_stage": "quoted"
    })
    saved = brasper_api.deposit_accounts
    brasper_api.deposit_accounts = lambda *args, **kwargs: {"ok": False, "error": "timeout"}
    try:
        out = _run(engine.handle_message(
            "deposit-failure", "continuar", conversation_id=cid
        ))
    finally:
        brasper_api.deposit_accounts = saved
    assert out["handoff"] is True, out
    assert "asesor se comunicará" in out["response"].lower(), out
    assert "consultar" not in out["response"].lower() and "timeout" not in out["response"].lower(), out
    assert db.conversation_status("brasper", cid) == "handoff"


def case_private_brasper_ai_contracts():
    """Clientes y cuentas usan solo endpoints IA privados, nunca listados globales."""
    tenant = T.get_tenant("brasper")
    saved = brasper_api._integration_request
    calls = []

    def fake_request(_tenant, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith("/lookup"):
            return {"ok": True, "data": {"found": True, "ambiguous": False, "client": {
                "id": "client-secure", "names": "Ana", "lastnames": "Pérez",
                "document_verified": True, "is_first_transfer": False,
            }}}
        if path.endswith("/upsert"):
            return {"ok": True, "data": {"id": "client-secure", "created": False,
                                           "is_first_transfer": False}}
        return {"ok": True, "data": []}

    brasper_api._integration_request = fake_request
    try:
        found = brasper_api.find_client(
            tenant, phone="999111222", code_phone="+51")
        assert found["data"]["id"] == "client-secure", found
        upserted = brasper_api.upsert_client(tenant, {
            "nombres": "Ana", "apellidos": "Pérez", "tipo_documento": "dni",
            "numero_documento": "12345678", "codigo_telefono": "+51", "telefono": "999111222",
        })
        assert upserted["ok"] is True, upserted
        brasper_api.deposit_accounts(tenant, "PEN")
    finally:
        brasper_api._integration_request = saved

    paths = [item[1] for item in calls]
    assert paths == [
        "/brasper/ai/clients/lookup",
        "/brasper/ai/clients/upsert",
        "/brasper/ai/deposit-accounts",
    ], paths
    assert all("/user/" not in path for path in paths), paths


def case_no_external_channel_guard():
    """El bot NUNCA deriva a WhatsApp/redes: se sanea historial de entrada y salida del LLM,
    aunque el historial viejo o el propio modelo insistan."""
    from core.agent_graph import sanitize_no_external_channels as clean

    # Oferta de WhatsApp -> se quita esa oración, se conserva el resto.
    r1 = clean("Con gusto te ayudo. O si prefieres, te paso con un asesor por WhatsApp.")
    assert "whatsapp" not in r1.lower() and "ayudo" in r1.lower(), r1
    # CTA viejo con wa.me -> fuera la URL, los montos quedan.
    r2 = clean("Cotización: recibes 710.29 BRL. ¿Deseas continuar? Escríbenos: https://wa.me/519")
    assert "wa.me" not in r2 and "710.29" in r2, r2
    # Mensaje que era SOLO la derivación -> fallback in-chat.
    r3 = clean("Te paso con un asesor por WhatsApp: wa.me/519")
    assert "wa.me" not in r3.lower() and "aquí" in r3.lower(), r3
    # Otras redes también.
    assert "instagram" not in clean("Escríbenos por Instagram @brasper para seguir.").lower()
    # Texto sin canal externo -> intacto.
    ok = "Escribe *continuar* y un asesor te atiende aquí."
    assert clean(ok) == ok, clean(ok)

    # E2E en el grafo: historial contaminado + LLM que insiste en WhatsApp -> salida limpia.
    tenant = T.get_tenant("brasper")
    cid = db.get_or_create_conversation("brasper", "guard-e2e", "webchat")
    db.add_message("brasper", cid, "assistant", "Te paso con un asesor por WhatsApp: wa.me/519")
    old = llm.chat
    async def _wa_chat(t, messages):
        # Verifica de paso que el historial que llega al LLM ya viene saneado.
        hist = " ".join(m["content"] for m in messages if m["role"] == "assistant")
        assert "wa.me" not in hist and "whatsapp" not in hist.lower(), f"historial no saneado: {hist!r}"
        return {"content": "Claro. Si prefieres te paso por WhatsApp al wa.me/519.",
                "tokens_in": 3, "tokens_out": 3, "model": "stub", "provider": "stub", "cost_usd": 0.0}
    llm.chat = _wa_chat
    try:
        out = _run(engine.handle_message("guard-e2e", "hola", conversation_id=cid))
    finally:
        llm.chat = old
    assert "whatsapp" not in out["response"].lower() and "wa.me" not in out["response"].lower(), out


def case_telegram_audio_transcription():
    """Voz entrante en Telegram: se transcribe y el bot RESPONDE (no va directo a handoff).
    Si la transcripción falla, cae a handoff sin romper."""
    tenant = T.get_tenant("brasper")
    assert audio_adapter.provider(tenant) == "whisper_service", "brasper usa whisper_service"
    assert audio_adapter.enabled(tenant), "brasper debe tener transcripción habilitada"

    sent: list = []
    async def _fake_send(t, chat_id, text, reply_markup=None):
        sent.append(text); return {"ok": True}
    async def _fake_typing(t, chat_id):
        return {"ok": True}
    async def _fake_download(t, file_id):
        return (b"AUDIOBYTES", "audio/ogg")
    async def _ok_transcribe(t, content, mime_type="audio/ogg"):
        return {"ok": True, "text": "Cotizar 500 PEN a BRL", "provider": "whisper_service"}
    saved = (telegram.send_message, telegram.send_typing, telegram.download_file,
             audio_adapter.transcribe_bytes)
    telegram.send_message, telegram.send_typing = _fake_send, _fake_typing
    telegram.download_file, audio_adapter.transcribe_bytes = _fake_download, _ok_transcribe
    try:
        voice = {"message": {"chat": {"id": 7788, "type": "private"}, "from": {"id": 7788},
                             "voice": {"file_id": "VOICEID", "mime_type": "audio/ogg"}}}
        r = _run(telegram.process_update(voice))
        assert r.get("transcribed") is True, r
        cid = db.get_or_create_conversation("brasper", "tg:7788", "telegram")
        msgs = db.get_messages("brasper", cid)
        umedia = [m for m in msgs if m["role"] == "user" and m.get("media")]
        assert umedia and umedia[-1]["media"]["kind"] == "voice", umedia
        assert "Cotizar 500 PEN a BRL" in umedia[-1]["content"], umedia[-1]
        assert sent and "710.29" in sent[-1].replace(",", ""), f"el bot responde la cotización: {sent}"

        # Transcripción fallida -> handoff (no rompe, no responde con texto vacío).
        async def _fail_transcribe(t, content, mime_type="audio/ogg"):
            return {"ok": False, "error": "whisper_service inalcanzable"}
        audio_adapter.transcribe_bytes = _fail_transcribe
        voice2 = {"message": {"chat": {"id": 7799, "type": "private"}, "from": {"id": 7799},
                              "voice": {"file_id": "VOICEID2", "mime_type": "audio/ogg"}}}
        r2 = _run(telegram.process_update(voice2))
        assert r2.get("media") == "voice" and not r2.get("transcribed"), r2
        cid2 = db.get_or_create_conversation("brasper", "tg:7799", "telegram")
        assert db.conversation_status("brasper", cid2) == "handoff", "audio no transcrito -> asesor"
    finally:
        (telegram.send_message, telegram.send_typing, telegram.download_file,
         audio_adapter.transcribe_bytes) = saved


def case_audio_adapter_provider_selection():
    """audio_adapter elige backend por config y degrada si no hay nada configurado."""
    # whisper_service por service_url explícito.
    t1 = {"id": "x", "audio": {"provider": "whisper_service", "service_url": "http://ws:8090"}}
    assert audio_adapter.provider(t1) == "whisper_service" and audio_adapter.enabled(t1)
    # openai por api_key inline.
    t2 = {"id": "x", "audio": {"provider": "openai", "api_key": "sk-test"}}
    assert audio_adapter.provider(t2) == "openai" and audio_adapter.enabled(t2)
    # enabled=false gana aunque haya url.
    t3 = {"id": "x", "audio": {"enabled": False, "service_url": "http://ws:8090"}}
    assert not audio_adapter.enabled(t3)
    # Sin key utilizable -> deshabilitado (el audio caerá a handoff).
    t4 = {"id": "x", "audio": {"provider": "openai", "api_key_env": "DEFINITELY_UNSET_KEY_XYZ"}}
    assert not audio_adapter.enabled(t4)


def case_brasper_api_live_quote():
    """La API Brasper es exclusiva: no hay fallback a tasas/comisiones/cupones locales."""
    tenant = T.get_tenant("brasper")
    saved_enabled, saved_fetch = brasper_api.enabled, brasper_api._fetch
    brasper_api.enabled = lambda t: True

    def _fake_fetch(url):
        if url.endswith("/coin/tax-rate"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "tax": "1.50000000"}]  # vivo: 1.50 (config: 1.46)
        if url.endswith("/coin/commission"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "percentage": 3.0, "min_amount": 0, "max_amount": 500}]
        return []  # sin cupón vivo -> no debe usar el cupón local

    brasper_api._fetch = _fake_fetch
    try:
        q = quotes.compute(tenant, "PEN", "BRL", 500, "send")
        assert abs(q["rate"] - 1.50) < 1e-9, f"debe usar la tasa viva 1.50, usó {q['rate']}"
        # Config (1.46) daría 710.29; con 1.50 el neto convertido cambia.
        assert q["amount_receive"] != 710.29, "debe cambiar respecto al config"
        assert q["amount_receive"] == 727.5, q
        assert q["coupon_code"] is None, "no debe usar el cupón local"
        # Si la API cae, rechaza la cotización y nunca usa la tasa local 1.46.
        brasper_api._fetch = lambda url: None
        q2 = quotes.compute(tenant, "PEN", "BRL", 500, "send")
        assert q2.get("error"), q2
        assert "rate" not in q2, f"no debe filtrar tasa local: {q2}"
    finally:
        brasper_api.enabled, brasper_api._fetch = saved_enabled, saved_fetch


def case_new_lead_and_banner():
    """La promo de primer envío aparece solo tras verificar que no existe el cliente."""
    tenant = T.get_tenant("brasper")
    saved_find = brasper_api.find_client
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": None, "ambiguous": False}
    try:
        out = _run(engine.handle_message("lead-nuevo-xyz", "hola"))
        assert out["new_lead"] is True and out.get("banner") is None, out
        assert "nombre completo" in out["response"].lower(), out
        out2 = _run(engine.handle_message(
            "lead-nuevo-xyz", "Ana Pérez", conversation_id=out["conversation_id"]
        ))
        assert out2["new_lead"] is False, out2
        assert out2.get("banner") and "primer envío" in (out2["banner"]["text"] or "").lower(), out2
    finally:
        brasper_api.find_client = saved_find


def case_lead_data_capture():
    """La cotización guarda los datos estructurados del lead (Fase 3)."""
    tenant = T.get_tenant("brasper")
    out = _run(engine.handle_message("lead-data-xyz", "Cotizar 500 PEN a BRL"))
    lead = db.get_lead_data("brasper", out["conversation_id"])
    assert lead.get("ruta") == "PEN->BRL", lead
    assert lead.get("monto_enviar") == 500.0, lead
    assert lead.get("estado_tc") == "activo", lead
    assert lead.get("canal") == "webchat", lead
    assert lead.get("monto_recibir") and lead.get("tasa"), lead
    # is_first_contact ya es False tras el primer mensaje.
    assert db.is_first_contact("brasper", "lead-data-xyz") is False


def case_quote_business_rules():
    """Vigencia de TC (20 min) en el texto + monto alto deriva a asesor."""
    auth_mod.ensure_seed()
    tenant = T.get_tenant("brasper")
    out = _run(engine.handle_message("rules-tc", "Cotizar 500 PEN a BRL"))
    assert "20 min" in out["response"], f"debe indicar vigencia de TC: {out['response']}"
    assert out["handoff"] is False, out
    # Monto alto (>= umbral 5000) -> handoff + asesor asignado.
    out2 = _run(engine.handle_message("rules-high", "Cotizar 8000 PEN a BRL"))
    assert out2["handoff"] is True, out2
    assert "asesor" in out2["response"].lower(), out2["response"]
    assert "710" not in out2["response"] or "8000" in out2["response"].replace(",", ""), "es la cotización de 8000"
    mine = [c for c in db.list_conversations("brasper") if c["user_ref"] == "rules-high"]
    assert mine and mine[0]["assigned_to"], f"monto alto debe asignar asesor: {mine}"


def case_bot_config_e2e():
    """E2E HTTP: PATCH del system_prompt desde la Admin API cambia lo que recibe el LLM."""
    from fastapi.testclient import TestClient
    from main import app

    old_source = os.environ.get("TENANTS_SOURCE")
    os.environ["TENANTS_SOURCE"] = "database"
    captured: dict = {}

    async def _capture_chat(tenant_arg, messages):
        captured["messages"] = messages
        return {"content": "ok", "tokens_in": 5, "tokens_out": 2, "model": "stub",
                "provider": "stub", "cost_usd": 0.0}

    old_chat = llm.chat
    llm.chat = _capture_chat
    try:
        T.ensure_store(overwrite=True)
        client = TestClient(app)
        owner = {"X-Auth-Token": "demo-owner"}
        marker = "PROMPT_CONFIGURADO_DESDE_PANEL_XYZ"
        r = client.patch("/api/admin/tenants/brasper", headers=owner,
                         json={"config": {"system_prompt": marker,
                                          "llm": {"temperature": 0.3}}})
        assert r.status_code == 200, r.text
        assert r.json()["tenant"]["system_prompt"] == marker

        r2 = client.post("/api/brasper/chat", headers=owner,
                         json={"message": "hola necesito informacion", "user_ref": "cfg-e2e"})
        assert r2.status_code == 200, r2.text
        system = " ".join(m["content"] for m in captured["messages"] if m["role"] == "system")
        assert marker in system, f"el LLM debe recibir el prompt configurado: {system[:200]}"

        # El deep-merge del PATCH no debe borrar el cotizador del bootstrap.
        r3 = client.post("/api/brasper/chat", headers=owner,
                         json={"message": "Cotizar 500 PEN a BRL", "user_ref": "cfg-e2e"})
        assert "710.29" in r3.json()["response"].replace(",", ""), r3.json()["response"]
    finally:
        llm.chat = old_chat
        if old_source is None:
            os.environ.pop("TENANTS_SOURCE", None)
        else:
            os.environ["TENANTS_SOURCE"] = old_source


# ---------------------------------------------------------------------------
# Stub del LLM (por si algun caso futuro lo requiere; no gasta LLM real)
# ---------------------------------------------------------------------------
async def _fake_chat(tenant, messages):
    return {
        "content": "[respuesta simulada]",
        "tokens_in": 10,
        "tokens_out": 5,
        "model": tenant.get("llm", {}).get("model", "stub"),
        "provider": tenant.get("llm", {}).get("provider", "stub"),
        "cost_usd": 0.0,
    }


llm.chat = _fake_chat  # monkeypatch: ningun caso llama al LLM real
# Por defecto los tests cotizan con las tasas del CONFIG (deterministas, sin red).
# El caso 39 activa la API con datos simulados para probar la integración en vivo.
brasper_api.enabled = lambda tenant: False


def main() -> int:
    check("1. aislamiento cruzado entre tenants", case_isolation)
    check("2. handoff determinista (sin LLM)", case_handoff)
    check("3. persistencia + orden cronologico", case_persistence_order)
    check("4. medicion usage_summary por tenant", case_usage_measurement)
    check("5. conversation_id aislado por tenant", case_conversation_id_scoped_by_tenant)
    check("6. resolve_by_phone_number_id", case_resolve_pnid)
    check("7. whatsapp.parse_incoming", case_parse_incoming)
    check("8. API protegida con RBAC + tenant_scope", case_api_auth_and_scope)
    check("9. webhook WhatsApp valida firma", case_webhook_signature)
    check("10. webhook Telegram exige secret en produccion", case_telegram_secret_in_production)
    check("11. tenants en DB con bootstrap desde JSON", case_tenant_store_database_mode)
    check("12. Admin API de tenants + secrets por env", case_admin_tenant_api)
    check("13. LangGraph ruta LLM con stub", case_langgraph_llm_path)
    check("14. Redis runtime sin REDIS_URL", case_redis_runtime_without_redis)
    check("15. ToolRouter ejecuta conector desde LangGraph", case_tool_router_path)
    check("16. CalendarAdapter agenda cita desde LangGraph", case_calendar_appointment_path)
    check("17. Observabilidad y metricas protegidas", case_observability_metrics)
    check("18. Backup SQLite local", case_sqlite_backup_create)
    check("19. Jobs retry/dead-letter sin Redis", case_jobs_retry_without_redis)
    check("20. Validaciones por vertical (salud/retail)", case_vertical_validation)
    check("21. Export de conversaciones por tenant", case_export_conversations)
    check("22. Agregacion usage_daily por tenant/dia", case_usage_daily)
    check("23. Retencion: purga de datos antiguos", case_retention_purge)
    check("24. Produccion exige Postgres + Redis (fail-fast)", case_production_requires_postgres_redis)
    check("25. Cotizador Brasper: matematica directa/inversa", case_quote_math)
    check("26. Cotizador en el grafo (sin LLM) + tenant sin cotizador", case_quote_graph_path)
    check("27. Derivacion: handoff asigna asesor con menos carga", case_advisor_assignment)
    check("28. E2E HTTP: bot configurable desde Admin API", case_bot_config_e2e)
    check("29. Jobs degradan si Redis esta inalcanzable (no 500)", case_jobs_degrade_when_redis_unreachable)
    check("30. Telegram solo responde en privado (ignora grupos)", case_telegram_private_only)
    check("31. Takeover humano: bot en pausa + asesor responde por el canal", case_human_takeover)
    check("32. Asesor: ve solo lo suyo, guard anti-colision, envio de imagenes", case_agent_scoping_and_images)
    check("33. Subida de archivo por el asesor (multipart + guards)", case_upload_file)
    check("34. Media entrante: se guarda, se muestra y deriva a asesor", case_incoming_media)
    check("35. Checkout: muestra cuentas oficiales sin crear transaccion", case_checkout_handoff)
    check("36. Guard: el bot nunca deriva a WhatsApp/redes (entrada+salida LLM)", case_no_external_channel_guard)
    check("37. Telegram: voz entrante se transcribe y el bot responde", case_telegram_audio_transcription)
    check("38. audio_adapter: seleccion de backend (whisper_service/openai)", case_audio_adapter_provider_selection)
    check("39. API Brasper exclusiva: TC real sin fallback local", case_brasper_api_live_quote)
    check("40. Lead nuevo: deteccion + banner de primer envio", case_new_lead_and_banner)
    check("41. Datos del lead estructurados (idioma/ruta/monto/TC)", case_lead_data_capture)
    check("42. Reglas: vigencia TC 20min + monto alto deriva a asesor", case_quote_business_rules)
    check("43. Onboarding: crea/actualiza cliente sin transaccion", case_client_onboarding_without_transaction)
    check("44. Cliente recurrente: reconocimiento por telefono", case_returning_client_by_phone)
    check("45. Cuentas no disponibles: handoff real sin error tecnico", case_deposit_failure_creates_handoff)
    check("46. Integracion Brasper: solo endpoints IA privados", case_private_brasper_ai_contracts)

    print("=" * 60)
    print("GATE PRODUCCION — verificacion (sin pytest, sin LLM real)")
    print("=" * 60)
    failed = 0
    for name, ok, detail in _RESULTS:
        status = "PASS" if ok else "FAIL"
        line = f"[{status}] {name}"
        if detail:
            line += f"  ->  {detail}"
        print(line)
        if not ok:
            failed += 1
    print("-" * 60)
    print(f"Total: {len(_RESULTS)}  PASS: {len(_RESULTS) - failed}  FAIL: {failed}")
    print(f"DB temporal: {db.DB_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
