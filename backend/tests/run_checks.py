"""Suite de verificacion de produccion — SIN pytest y SIN gastar LLM real.

Ejecutar:
    cd backend && ../.venv/bin/python tests/run_checks.py        # macOS / Linux
    cd backend && ..\\.venv\\Scripts\\python.exe tests\\run_checks.py  # Windows

Usa asserts planos. Imprime PASS/FAIL por caso. sys.exit(1) si algo falla.

Arquitectura cubierta: bot single-tenant Brasper (backend/), LangGraph,
cotizador determinista (API Brasper en vivo o tasas de config), onboarding,
handoff a asesores, canales (WhatsApp / Telegram / webchat) y panel (Admin API).

Aislamiento:
  - DB SQLite temporal (core.db.DB_PATH) antes de init_db.
  - config/tenants.json se COPIA a un temporal (core.tenants.CONFIG_PATH): la Admin
    API escribe en disco y no debe tocar el archivo versionado.
  - El LLM se monkeypatchea con un stub async; la API Brasper se apaga por defecto
    (cotiza con las tasas del config) y los casos que la prueban la simulan.
"""
import asyncio
import hashlib
import hmac
import os
import shutil
import sys
import tempfile
from pathlib import Path

# --- Aislar la ejecucion: raiz de backend/ en sys.path y DB temporal ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Entorno hermetico (SQLite temporal, sin Redis) aunque backend/.env defina
# Postgres/Redis: load_dotenv (override=False) no pisa variables ya definidas.
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["APP_ENV"] = "development"
# Un .env local de operación (admin de producción, tenants desde DB, debounce, login con
# código) no debe cambiar el resultado del gate: se neutraliza antes de cargar módulos.
for _name in ("PANEL_ADMIN_EMAIL", "PANEL_ADMIN_TOKEN", "PANEL_ADMIN_NAME", "PANEL_LOGIN_CODE",
              "SEED_DEMO_USERS", "TENANTS_SOURCE", "TENANTS_BOOTSTRAP_OVERWRITE",
              "CHANNEL_DEBOUNCE_SECONDS", "BRASPER_IA_GRANT_KEY",
              "WHATSAPP_REQUIRE_SIGNATURE", "WHATSAPP_APP_SECRET", "META_APP_SECRET",
              "BRASPER_IA_SERVICE_USERNAME", "BRASPER_IA_SERVICE_PASSWORD"):
    os.environ[_name] = ""

_TMP_DIR = Path(tempfile.mkdtemp(prefix="prod_checks_"))

# Config temporal ANTES de importar modulos que la lean.
from core import tenants as T  # noqa: E402

_TMP_CONFIG = _TMP_DIR / "tenants.json"
shutil.copy2(T.CONFIG_PATH, _TMP_CONFIG)
T.CONFIG_PATH = _TMP_CONFIG
T.reload_config()

# DB temporal ANTES de init_db.
from core import db  # noqa: E402

_TMP_DB = _TMP_DIR / "test_plataforma.db"
db.DB_PATH = _TMP_DB
db.init_db()

from core import auth as auth_mod  # noqa: E402
from core import engine, whatsapp  # noqa: E402
from core import connectors, debounce, jobs, redis_runtime  # noqa: E402
from core import llm  # noqa: E402
from core import observability  # noqa: E402
from core import telegram  # noqa: E402
from core import audio_adapter  # noqa: E402
from core import calendar_adapter  # noqa: E402
from core import quotes, brasper_api, lead_onboarding  # noqa: E402
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
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


OWNER = {"X-Auth-Token": "demo-owner"}
AGENT = {"X-Auth-Token": "demo-agent-brasper"}   # agent@brasper.com
BILLING = {"X-Auth-Token": "demo-billing"}


# ---------------------------------------------------------------------------
# Caso 1: configuracion single-tenant Brasper
# ---------------------------------------------------------------------------
def case_config_single_tenant():
    cfg = T.get_config()
    assert cfg["id"] == "brasper", cfg.get("id")
    assert cfg.get("active") is True, "brasper debe estar activo"
    assert (cfg.get("quote") or {}).get("enabled") is True, "brasper debe tener cotizador"
    assert ("PEN", "BRL") in quotes.pairs() and ("BRL", "PEN") in quotes.pairs(), quotes.pairs()
    assert cfg.get("llm", {}).get("model"), "falta modelo LLM"
    # Secretos solo por referencia a env (nunca valores crudos en el JSON versionado).
    assert "api_key" not in cfg.get("llm", {}), "api_key cruda en tenants.json"
    assert "token" not in cfg.get("whatsapp", {}), "token WhatsApp crudo en tenants.json"
    assert "bot_token" not in cfg.get("telegram", {}), "bot_token crudo en tenants.json"
    # El prompt refuerza las reglas de launch: no inventar tasas, no derivar fuera.
    prompt = cfg.get("system_prompt", "").lower()
    assert "no inventes tasas" in prompt, "el prompt debe prohibir inventar tasas"
    assert "whatsapp" in prompt and "nunca" in prompt, "el prompt debe prohibir derivar a WhatsApp"


# ---------------------------------------------------------------------------
# Caso 2: persistencia + orden cronologico
# ---------------------------------------------------------------------------
def case_persistence_order():
    cid = db.get_or_create_conversation("user-order", "webchat")
    db.add_message(cid, "user", "primero")
    db.add_message(cid, "assistant", "segundo")
    db.add_message(cid, "user", "tercero")
    hist = db.get_history(cid, limit=12)
    contents = [m["content"] for m in hist]
    assert contents == ["primero", "segundo", "tercero"], \
        f"historial fuera de orden cronologico: {contents}"
    msgs = db.get_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"], msgs


# ---------------------------------------------------------------------------
# Caso 3: la conversacion se reutiliza por usuario/canal; 'closed' abre una nueva
# ---------------------------------------------------------------------------
def case_conversation_reuse():
    a = db.get_or_create_conversation("user-reuse", "webchat")
    b = db.get_or_create_conversation("user-reuse", "webchat")
    assert a == b, "mismo usuario+canal debe reutilizar la conversacion activa"
    db.set_conversation_status(a, "handoff")
    c = db.get_or_create_conversation("user-reuse", "webchat")
    assert c == a, "en handoff tambien se reutiliza (el asesor sigue viendo el hilo)"
    db.set_conversation_status(a, "closed")
    d = db.get_or_create_conversation("user-reuse", "webchat")
    assert d != a, "cerrada -> conversacion nueva"
    # Un conversation_id explicito se respeta y es idempotente.
    e = db.get_or_create_conversation("user-reuse-2", "webchat", "conv-explicita")
    assert e == "conv-explicita", e
    assert db.get_or_create_conversation("user-reuse-2", "webchat", "conv-explicita") == e
    # Otro canal del mismo usuario es otra conversacion.
    tg = db.get_or_create_conversation("user-reuse", "telegram")
    assert tg not in {a, d}, tg


# ---------------------------------------------------------------------------
# Caso 4: medicion de consumo (usage_summary / usage_daily / usage_events)
# ---------------------------------------------------------------------------
def case_usage_measurement():
    before = db.usage_summary()[0]
    db.add_usage(None, "deepseek", "deepseek-chat", 100, 50, 0.001)
    db.add_usage(None, "deepseek", "deepseek-chat", 200, 80, 0.002)
    after = db.usage_summary()[0]
    assert after["calls"] - before["calls"] == 2, (before, after)
    assert after["tokens_in"] - before["tokens_in"] == 300, (before, after)
    assert after["tokens_out"] - before["tokens_out"] == 130, (before, after)
    assert abs((after["cost_usd"] - before["cost_usd"]) - 0.003) < 1e-6, (before, after)
    daily = db.usage_daily()
    assert daily and daily[0]["calls"] >= 2 and daily[0]["cost_usd"] >= 0.003, daily
    events = db.usage_events(limit=5)
    assert events and events[0]["model"] == "deepseek-chat", events


# ---------------------------------------------------------------------------
# Caso 5: resolve_by_phone_number_id (WhatsApp Cloud API)
# ---------------------------------------------------------------------------
def case_resolve_pnid():
    os.environ["WA_PHONE_NUMBER_ID_BRASPER"] = "PNID_BRASPER_123"
    try:
        t = T.resolve_by_phone_number_id("PNID_BRASPER_123")
        assert t is not None and t["id"] == "brasper", t
        assert T.resolve_by_phone_number_id("PNID_QUE_NO_EXISTE_999") is None
    finally:
        os.environ.pop("WA_PHONE_NUMBER_ID_BRASPER", None)


# ---------------------------------------------------------------------------
# Caso 6: whatsapp.parse_incoming con payload de Meta de ejemplo
# ---------------------------------------------------------------------------
def case_parse_incoming():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "51900000000",
                                 "phone_number_id": "PNID_META_777"},
                    "messages": [
                        {"from": "51955512345", "id": "wamid.ABC", "timestamp": "1710000000",
                         "type": "text", "text": {"body": "Hola, quiero cotizar un envio"}},
                        {"from": "51955599999", "id": "wamid.AUD", "timestamp": "1710000001",
                         "type": "audio", "audio": {"id": "MEDIA_123", "mime_type": "audio/ogg"}},
                    ],
                },
            }],
        }],
    }
    msgs = whatsapp.parse_incoming(payload)
    assert len(msgs) == 2, f"esperado 2 mensajes (texto+audio), fue {len(msgs)}"
    by_type = {m["type"]: m for m in msgs}
    t = by_type["text"]
    assert t["phone_number_id"] == "PNID_META_777", t
    assert t["from"] == "51955512345", t
    assert t["text"] == "Hola, quiero cotizar un envio", t
    a = by_type["audio"]
    assert a["media_id"] == "MEDIA_123" and a["mime_type"] == "audio/ogg", a
    assert "text" not in a, f"el audio no debe tener 'text': {a}"


# ---------------------------------------------------------------------------
# Caso 7: API protegida con RBAC
# ---------------------------------------------------------------------------
def case_api_auth_rbac():
    auth_mod.ensure_seed()
    client = _client()
    assert client.get("/api/tenants").status_code == 401, "tenants debe exigir token"
    assert client.get("/api/usage").status_code == 401, "usage debe exigir token"
    assert client.get("/api/conversations").status_code == 401, "conversations debe exigir token"

    r = client.get("/api/tenants", headers=OWNER)
    assert r.status_code == 200, r.text
    ids = [t["id"] for t in r.json()["tenants"]]
    assert ids == ["brasper"], ids

    r = client.get("/api/me", headers=AGENT)
    assert r.status_code == 200 and r.json()["role"] == "agent", r.text
    # Agente: opera conversaciones, no configura.
    assert client.get("/api/conversations", headers=AGENT).status_code == 200
    assert client.patch("/api/admin/tenants", headers=AGENT,
                        json={"config": {"fee_usd": 1}}).status_code == 403
    # Billing: consumo si, chat/operacion no.
    assert client.get("/api/usage", headers=BILLING).status_code == 200
    assert client.post("/api/chat", json={"message": "hola"}, headers=BILLING).status_code == 403
    assert client.get("/api/conversations", headers=BILLING).status_code == 403
    # Token invalido -> 401 (no 403).
    assert client.get("/api/tenants", headers={"X-Auth-Token": "no-existe"}).status_code == 401


# ---------------------------------------------------------------------------
# Caso 8: firma del webhook WhatsApp
# ---------------------------------------------------------------------------
def case_webhook_signature():
    client = _client()
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
# Caso 9: Telegram webhook exige secret en produccion
# ---------------------------------------------------------------------------
def case_telegram_secret_in_production():
    async def _fake_process_update(body):
        return {"handled": True}

    old_pu = telegram.process_update
    telegram.process_update = _fake_process_update
    client = _client()
    raw = {"message": {"chat": {"id": 1, "type": "private"}, "text": "hola"}}
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
        hdr = {"X-Telegram-Bot-Api-Secret-Token": "tg-secret"}
        assert client.post("/telegram/webhook/brasper", json=raw, headers=hdr).status_code == 200
        assert client.post("/telegram/webhook", json=raw, headers=hdr).status_code == 200, \
            "ruta single-tenant debe aceptar webhook"
        assert client.post("/telegram/webhook/otro", json=raw, headers=hdr).status_code == 404, \
            "tenant desconocido debe rechazarse"
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
# Caso 10: Admin API single-tenant (patch, pausa, secretos por env)
# ---------------------------------------------------------------------------
def case_admin_tenant_api():
    client = _client()
    original_fee = T.get_config().get("fee_usd")
    original_key_env = T.get_config()["llm"]["api_key_env"]
    old_env = os.environ.get("APP_ENV")
    try:
        r = client.get("/api/admin/tenants", headers=OWNER)
        assert r.status_code == 200 and r.json()["tenants"][0]["id"] == "brasper", r.text

        r = client.patch("/api/admin/tenants", headers=OWNER,
                         json={"config": {"fee_usd": 950, "llm": {"temperature": 0.3}}})
        assert r.status_code == 200, r.text
        assert r.json()["tenant"]["fee_usd"] == 950, r.json()
        cfg = T.get_config()
        assert cfg["fee_usd"] == 950 and cfg["llm"]["temperature"] == 0.3, cfg
        # Deep-merge: el PATCH parcial no borra el resto de la config.
        assert cfg["llm"]["model"] and cfg["quote"]["enabled"] is True, cfg

        r = client.post("/api/admin/tenants/pause", headers=OWNER)
        assert r.status_code == 200 and r.json()["tenant"]["active"] is False, r.text
        r = client.post("/api/admin/tenants/resume", headers=OWNER)
        assert r.status_code == 200 and r.json()["tenant"]["active"] is True, r.text

        r = client.post("/api/admin/tenants/secrets", headers=OWNER,
                        json={"refs": {"llm.api_key_env": "DEEPSEEK_API_KEY_ROTADA"},
                              "note": "rotacion test"})
        assert r.status_code == 200, r.text
        assert r.json()["tenant"]["llm"]["api_key_env"] == "DEEPSEEK_API_KEY_ROTADA"
        r = client.get("/api/admin/tenants/secrets/rotations", headers=OWNER)
        assert r.status_code == 200, r.text
        rotations = r.json()["rotations"]
        assert rotations and rotations[0]["secret_path"] == "llm.api_key_env", rotations
        assert rotations[0]["env_name"] == "DEEPSEEK_API_KEY_ROTADA", rotations
        # Ruta de secreto no permitida -> 422.
        r = client.post("/api/admin/tenants/secrets", headers=OWNER,
                        json={"refs": {"llm.api_key": "X"}})
        assert r.status_code == 422, r.text
        # Otro tenant no existe en single-tenant -> 404.
        r = client.post("/api/admin/tenants", headers=OWNER,
                        json={"id": "otro_cliente", "config": {"name": "Otro"}})
        assert r.status_code == 404, r.text

        # En produccion se rechazan secretos crudos en la config.
        os.environ["APP_ENV"] = "production"
        r = client.patch("/api/admin/tenants", headers=OWNER,
                         json={"config": {"llm": {"api_key": "sk-nope"}}})
        assert r.status_code == 422, f"secret crudo en prod debe rechazarse, fue {r.status_code}"
        assert "api_key" not in T.get_config()["llm"], "el secreto crudo no debe persistirse"
    finally:
        if old_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = old_env
        # Restaura la config temporal para los casos siguientes.
        T.upsert_tenant_config("brasper", {"fee_usd": original_fee,
                                           "llm": {"api_key_env": original_key_env}})


# ---------------------------------------------------------------------------
# Caso 11: LangGraph ruta LLM con stub (sin cotizacion, sin handoff)
# ---------------------------------------------------------------------------
def case_langgraph_llm_path():
    tenant = T.get_config()
    # Pregunta general sin intencion detectable (las de documentos ya las resuelve la FAQ con fuente).
    out = _run(engine.handle_message("user-langgraph", "hola, tengo una duda general sobre su servicio"))
    assert out["handoff"] is False, out
    assert out["response"] == "[respuesta simulada]", out
    assert out["usage"]["model"] == tenant.get("llm", {}).get("model"), out["usage"]
    msgs = db.get_messages(out["conversation_id"])
    assert [m["role"] for m in msgs][-2:] == ["user", "assistant"], msgs
    assert db.usage_summary()[0]["calls"] >= 1


# ---------------------------------------------------------------------------
# Caso 12: fallo del LLM -> respuesta cortes + handoff (el bot nunca queda mudo)
# ---------------------------------------------------------------------------
def case_llm_failure_degrades_to_handoff():
    auth_mod.ensure_seed()
    old = llm.chat

    async def _broken(tenant, messages):
        raise llm.LLMError("Model Not Exist")

    llm.chat = _broken
    try:
        out = _run(engine.handle_message("user-llm-down", "hola, una consulta general"))
    finally:
        llm.chat = old
    assert out["handoff"] is True and out["usage"] is None, out
    assert "asesor" in out["response"].lower(), out["response"]
    assert "Model Not Exist" not in out["response"], "no exponer errores tecnicos al cliente"
    assert db.conversation_status(out["conversation_id"]) == "handoff"


# ---------------------------------------------------------------------------
# Caso 13: Redis runtime cae seguro sin REDIS_URL
# ---------------------------------------------------------------------------
def case_redis_runtime_without_redis():
    assert redis_runtime.configured() is False
    # Sin Redis el lock pasa a la base: exclusión real, liberación por dueño y TTL.
    token = redis_runtime.acquire_lock("test:lock")
    assert token and token.startswith("db:"), token
    assert redis_runtime.acquire_lock("test:lock", wait_seconds=0.1) is None, "segundo dueño bloqueado"
    redis_runtime.release_lock("test:lock", "db:not-the-owner")
    assert redis_runtime.acquire_lock("test:lock", wait_seconds=0.1) is None, "solo el dueño libera"
    redis_runtime.release_lock("test:lock", token)
    again = redis_runtime.acquire_lock("test:lock", ttl_seconds=0, wait_seconds=0.1)
    assert again and redis_runtime.acquire_lock("test:lock", wait_seconds=0.5), "un lock vencido se recupera"
    assert jobs.enqueue("noop", {"ok": True}) is False
    os.environ["CHANNEL_DEBOUNCE_SECONDS"] = "2"
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    redis_runtime._CLIENT = None
    try:
        assert debounce.enabled() is True
        assert debounce.buffer_message("brasper", "webchat", "u", "hola", {}) is False
    finally:
        os.environ.pop("CHANNEL_DEBOUNCE_SECONDS", None)
        os.environ["REDIS_URL"] = ""
        redis_runtime._CLIENT = None


# ---------------------------------------------------------------------------
# Caso 14: ToolRouter ejecuta un conector declarado y el LLM redacta el resultado
# ---------------------------------------------------------------------------
def case_tool_router_path():
    fake_connectors = [{
        "key": "erp_demo", "name": "ERP Demo", "base_url": "https://erp.example",
        "endpoints": [{"tool": "consultar_stock", "method": "GET",
                       "path": "/stock/{{sku}}", "desc": "Consulta stock por SKU"}],
    }]

    async def _fake_call_endpoint(tenant_arg, connector_key, tool_name, variables):
        assert tenant_arg["id"] == "brasper"
        assert connector_key == "erp_demo" and tool_name == "consultar_stock"
        assert variables["sku"] == "SKU123"
        return {"ok": True, "status": 200, "data": {"sku": variables["sku"], "stock": 7}}

    captured: dict = {}
    old_chat = llm.chat

    async def _capture_chat(tenant_arg, messages):
        captured["messages"] = messages
        return await old_chat(tenant_arg, messages)

    old_list, old_call = connectors.list_connectors, connectors.call_endpoint
    connectors.list_connectors = lambda tenant: fake_connectors
    connectors.call_endpoint = _fake_call_endpoint
    llm.chat = _capture_chat
    try:
        out = _run(engine.handle_message("user-tool", "consulta stock sku SKU123"))
        assert out["handoff"] is False, out
        joined = " ".join(m["content"] for m in captured.get("messages", []))
        assert "consultar_stock" in joined and "SKU123" in joined and "7" in joined, joined
        assert out["usage"] is not None and out["response"], out
    finally:
        connectors.list_connectors, connectors.call_endpoint = old_list, old_call
        llm.chat = old_chat
    # Sin conectores declarados (config real de Brasper) el mismo texto va al LLM.
    assert connectors.list_connectors(T.get_config()) == [], "brasper no declara externalApis"


# ---------------------------------------------------------------------------
# Caso 15: CalendarAdapter (verticales con citas) es puro y Brasper no lo usa
# ---------------------------------------------------------------------------
def case_calendar_adapter():
    clinic = {"id": "clinica", "calendar": {"enabled": True, "specialties": ["odontologia"]}}
    assert calendar_adapter.enabled(clinic) and not calendar_adapter.enabled(T.get_config())
    assert calendar_adapter.has_intent("quiero agendar una cita")
    req = calendar_adapter.extract_request(
        clinic, "quiero agendar cita nombre Juan Perez dni 12345678 especialidad odontologia 2026-07-10 10:30", [])
    assert req["missing"] == [], req
    f = req["fields"]
    assert f["patient_name"] == "Juan Perez" and f["document_id"] == "12345678", f
    assert "odontolog" in f["specialty"] and f["scheduled_for"].startswith("2026-07-10T10:30"), f
    partial = calendar_adapter.extract_request(clinic, "quiero una cita", [])
    assert "fecha y hora" in partial["missing"] and "nombre completo" in partial["missing"], partial
    # Brasper (sin calendario): la frase va al LLM, no al agendador.
    out = _run(engine.handle_message("user-cita", "quiero agendar una cita"))
    assert out["response"] == "[respuesta simulada]" and out["usage"] is not None, out
    assert db.list_appointments() == [], "brasper no debe crear citas"


# ---------------------------------------------------------------------------
# Caso 16: Observabilidad expone metricas protegidas y redacta secretos
# ---------------------------------------------------------------------------
def case_observability_metrics():
    redacted = observability._redact({"api_key": "sk-test", "nested": {"token": "abc", "ok": True}})
    assert redacted["api_key"] == "***" and redacted["nested"]["token"] == "***", redacted
    assert redacted["nested"]["ok"] is True, redacted
    not_secret = observability._redact({"tokens_in": 10, "tokens_out": 5})
    assert not_secret["tokens_in"] == 10 and not_secret["tokens_out"] == 5, not_secret

    client = _client()
    assert client.get("/api/ops/metrics").status_code == 401, "metrics debe exigir auth"
    r = client.get("/api/ops/metrics", headers=OWNER)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "usage" in data and "conversations" in data and "jobs" in data, data
    assert client.get("/api/ops/alerts").status_code == 401, "alerts debe exigir auth"
    r = client.get("/api/ops/alerts", headers=OWNER)
    assert r.status_code == 200 and isinstance(r.json()["alerts"], list), r.text
    r = client.get("/api/ops/usage-daily", headers=OWNER)
    assert r.status_code == 200, r.text
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["db"]["ok"] is True, r.text


# ---------------------------------------------------------------------------
# Caso 17: Backup SQLite local crea archivo restaurable
# ---------------------------------------------------------------------------
def case_sqlite_backup_create():
    out_dir = _TMP_DIR / "backups"
    path = backup.create_backup(out_dir)
    assert path.exists() and path.stat().st_size > 0, path
    assert path in backup.list_backups(out_dir)


# ---------------------------------------------------------------------------
# Caso 18: Jobs retry/dead-letter caen seguro sin Redis
# ---------------------------------------------------------------------------
def case_jobs_retry_without_redis():
    assert jobs.handle_failure({"type": "x", "payload": {}}, "boom") is False
    assert jobs.dead_letter_count() == 0


# ---------------------------------------------------------------------------
# Caso 19: Export de conversaciones + retencion (purga)
# ---------------------------------------------------------------------------
def case_export_and_retention():
    cid = db.get_or_create_conversation("user-export", "webchat")
    db.add_message(cid, "user", "hola export")
    db.add_message(cid, "assistant", "ok")
    conv = next((c for c in db.export_conversations() if c["id"] == cid), None)
    assert conv is not None and len(conv["messages"]) == 2, conv
    client = _client()
    r = client.get("/api/export?limit=5", headers=OWNER)
    assert r.status_code == 200, r.text

    old = db.get_or_create_conversation("user-old", "webchat")
    db.add_message(old, "user", "vieja")
    with db.connect() as con:
        con.execute("UPDATE conversations SET updated_at=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", old))
    counts = db.purge_old_data("2001-01-01T00:00:00+00:00")
    assert counts["conversations"] >= 1, counts
    assert db.get_messages(old) == [], "sus mensajes deben borrarse"
    assert any(c["id"] == cid for c in db.list_conversations()), "no debe borrar recientes"


# ---------------------------------------------------------------------------
# Caso 20: produccion exige Postgres + Redis (fail-fast)
# ---------------------------------------------------------------------------
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
        db.assert_production_infra()  # configurado -> no lanza
        os.environ["APP_ENV"] = "development"
        os.environ["DATABASE_URL"] = ""
        os.environ["REDIS_URL"] = ""
        db.assert_production_infra()  # desarrollo: SQLite permitido
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Caso 21: cotizador Brasper — matematica directa/inversa (tasas de config)
# ---------------------------------------------------------------------------
def case_quote_math():
    assert quotes.enabled(), "brasper debe tener quote.enabled"
    # 500 PEN -> comision 3% = 15.00, cupon 10% sobre comision = 1.50, neta 13.50,
    # convertible 486.50, tasa 1.46 -> recibe 710.29 BRL.
    q = quotes.compute("PEN", "BRL", 500, "send")
    assert not q.get("error"), q
    assert q["commission_gross"] == 15.0 and q["coupon_savings_amount"] == 1.5, q
    assert q["commission"] == 13.5 and q["total_to_send"] == 486.5, q
    assert q["amount_receive"] == 710.29 and q["rate"] == 1.46, q
    # Inverso: recibir 710.29 BRL requiere enviar ~500 PEN.
    inv = quotes.compute("PEN", "BRL", 710.29, "receive")
    assert not inv.get("error"), inv
    assert abs(inv["amount_send"] - 500.0) <= 0.25, inv
    assert abs(inv["amount_receive"] - 710.29) <= 0.05, inv
    # Par no soportado y monto invalido.
    bad = quotes.compute("PEN", "USD", 100, "send")
    assert bad.get("error") and "PEN" in bad["error"], bad
    assert quotes.compute("PEN", "BRL", 0, "send").get("error")
    # Reglas de texto: referencial + vigencia + CTA dentro del chat.
    text = quotes.reply(q, "es")
    assert "referencial" in text.lower() and "20 min" in text and "continuar" in text, text
    assert "wa.me" not in text and "whatsapp" not in text.lower(), text


# ---------------------------------------------------------------------------
# Caso 22: extraccion del pedido (monedas, paises, modo recibir, inferencia)
# ---------------------------------------------------------------------------
def case_quote_request_extraction():
    r = quotes.extract_request("Cotizar 500 PEN a BRL")
    assert (r["origin"], r["destination"], r["amount"], r["mode"]) == ("PEN", "BRL", 500.0, "send"), r
    r = quotes.extract_request("quiero enviar 300 soles a Brasil")
    assert (r["origin"], r["destination"], r["amount"]) == ("PEN", "BRL", 300.0), r
    r = quotes.extract_request("quiero recibir 1000 soles")
    assert (r["origin"], r["destination"], r["mode"]) == ("BRL", "PEN", "receive"), r
    r = quotes.extract_request("quanto custa enviar 1.500,50 reais para o Peru")
    assert (r["origin"], r["destination"], r["amount"]) == ("BRL", "PEN", 1500.5), r
    # Seguimiento: solo cambia el monto -> conserva corredor y modo previos.
    prev = {"origin": "BRL", "destination": "PEN", "mode": "receive"}
    r = quotes.extract_request("y para 2000?", prev=prev)
    assert r.get("followup") and (r["origin"], r["destination"], r["mode"]) == ("BRL", "PEN", "receive"), r
    assert r["amount"] == 2000.0 and r["missing"] == [], r
    # Una direccion nueva explicita NO es seguimiento.
    r = quotes.extract_request("enviar 100 USD a BRL", prev=prev)
    assert not r.get("followup") and (r["origin"], r["destination"]) == ("USD", "BRL"), r
    # Senales: fuerte sin datos, debil con datos, debil sin datos.
    assert quotes.has_intent("quiero cotizar")
    assert quotes.has_intent("enviar 500 soles")
    assert not quotes.has_intent("que documentos necesito para el envio?")
    assert not quotes.has_intent("hola buenas")


# ---------------------------------------------------------------------------
# Caso 23: cotizador en el grafo (sin LLM) + aclaraciones deterministas
# ---------------------------------------------------------------------------
def case_quote_graph_path():
    out = _run(engine.handle_message("user-quote", "Cotizar 500 PEN a BRL"))
    assert out["handoff"] is False, out
    assert out["usage"] is None, "la cotizacion no debe llamar al LLM"
    flat = out["response"].replace(",", "")
    assert "710.29" in flat and "1.4600" in out["response"] and "BRASPER10" in out["response"], out["response"]

    # Seguimiento en la misma conversacion: "y para 2000 soles?" -> mismo corredor.
    # 2000 PEN: comision 2% = 40, cupon 10% = 4 -> neta 36 -> 1964 * 1.46 = 2867.44
    out2 = _run(engine.handle_message("user-quote", "¿y para 2000 soles?",
                                      conversation_id=out["conversation_id"]))
    assert out2["usage"] is None, out2
    assert "2867.44" in out2["response"].replace(",", ""), out2["response"]

    # Pedido incompleto: aclaracion determinista (no LLM, no "no tengo la tasa").
    out3 = _run(engine.handle_message("user-quote-inc", "quiero cotizar"))
    assert out3["usage"] is None and "monto" in out3["response"].lower(), out3
    assert "no tengo" not in out3["response"].lower(), out3["response"]

    # Destino ambiguo (BRL -> PEN o USD): pregunta SOLO el dato faltante.
    out4 = _run(engine.handle_message("user-quote-amb", "500 reales a olesñ"))
    assert out4["usage"] is None, out4
    assert "PEN" in out4["response"] and "USD" in out4["response"], out4["response"]

    # Senal debil sin datos ("envio" como sustantivo) NO cae al cotizador: la resuelve la
    # FAQ aprobada con fuente (sin LLM), no el cotizador ni una alucinacion.
    out5 = _run(engine.handle_message("user-quote-doc", "que documentos necesito para el envio?"))
    assert out5["usage"] is None and "DNI" in out5["response"] and "Fuente" in out5["response"], out5["response"]


# ---------------------------------------------------------------------------
# Caso 24: handoff determinista por keyword (sin LLM) + asignacion de asesor
# ---------------------------------------------------------------------------
def case_handoff_and_advisor_assignment():
    auth_mod.ensure_seed()
    out = _run(engine.handle_message("user-handoff", "quiero un asesor"))
    assert out["handoff"] is True and out["usage"] is None, out
    assert "asesor" in out["response"].lower(), out["response"]
    assert "wa.me" not in out["response"], out["response"]
    convs = [c for c in db.list_conversations() if c["user_ref"] == "user-handoff"]
    assert convs and convs[0]["status"] == "handoff", convs
    assert convs[0]["assigned_to"] == "agent@brasper.com", convs
    assert db.handoff_load_by_agent().get("agent@brasper.com", 0) >= 1
    # Portugues tambien.
    out_pt = _run(engine.handle_message("user-handoff-pt", "quero falar com alguém"))
    assert out_pt["handoff"] is True, out_pt


# ---------------------------------------------------------------------------
# Caso 25: takeover humano — bot en pausa, asesor responde, devolver al bot
# ---------------------------------------------------------------------------
def case_human_takeover():
    out1 = _run(engine.handle_message("tk:1", "hola, una consulta"))
    cid = out1["conversation_id"]
    assert not out1.get("paused") and out1["response"], out1

    db.set_conversation_status(cid, "handoff")  # asesor toma
    before = len(db.get_messages(cid))
    out2 = _run(engine.handle_message("tk:1", "sigo ahi?", conversation_id=cid))
    assert out2.get("paused") is True and (out2["response"] or "") == "", out2
    assert out2["usage"] is None, out2
    msgs = db.get_messages(cid)
    assert len(msgs) == before + 1 and msgs[-1]["role"] == "user", msgs

    client = _client()
    r = client.post(f"/api/conversations/{cid}/reply", headers=OWNER,
                    json={"text": "Hola, soy tu asesor."})
    assert r.status_code == 200, r.text
    msgs2 = db.get_messages(cid)
    assert msgs2[-1]["content"] == "Hola, soy tu asesor." and msgs2[-1]["role"] == "assistant", msgs2[-1]
    assert db.conversation_status(cid) == "handoff"
    r = client.get(f"/api/conversations/{cid}", headers=OWNER)
    assert r.status_code == 200 and r.json()["status"] == "handoff", r.text

    r2 = client.post(f"/api/conversations/{cid}/status", headers=OWNER, json={"status": "active"})
    assert r2.status_code == 200, r2.text
    out3 = _run(engine.handle_message("tk:1", "hola de nuevo", conversation_id=cid))
    assert not out3.get("paused") and out3["response"], out3
    assert client.post(f"/api/conversations/{cid}/status", headers=OWNER,
                       json={"status": "otro"}).status_code == 422


# ---------------------------------------------------------------------------
# Caso 26: asesor ve solo lo suyo + libres, guard anti-colision, envio de imagen
# ---------------------------------------------------------------------------
def case_agent_scoping_and_images():
    auth_mod.ensure_seed()
    client = _client()
    a = db.get_or_create_conversation("wa:scope-A", "whatsapp")
    db.assign_conversation(a, "agent@brasper.com")
    b = db.get_or_create_conversation("wa:scope-B", "whatsapp")
    db.assign_conversation(b, "otro@brasper.com")
    c = db.get_or_create_conversation("tg:700300", "telegram")  # libre

    ids_owner = {x["id"] for x in client.get("/api/conversations", headers=OWNER).json()["conversations"]}
    assert {a, b, c} <= ids_owner, ids_owner
    ids_agent = {x["id"] for x in client.get("/api/conversations", headers=AGENT).json()["conversations"]}
    assert a in ids_agent and c in ids_agent and b not in ids_agent, ids_agent

    r = client.post(f"/api/conversations/{b}/reply", headers=AGENT, json={"text": "hola"})
    assert r.status_code == 403, r.text
    old_send = telegram.send_message

    async def _fake_send(chat_id, text, reply_markup=None):
        return {"ok": True}

    telegram.send_message = _fake_send
    try:
        r = client.post(f"/api/conversations/{c}/reply", headers=AGENT, json={"text": "te ayudo"})
    finally:
        telegram.send_message = old_send
    assert r.status_code == 200 and r.json()["delivery"]["sent"] is True, r.text
    assert db.get_conversation(c)["assigned_to"] == "agent@brasper.com"

    old_img = whatsapp.send_image

    async def _fake_image(to, link, caption="", **kw):
        return {"sent": True}

    whatsapp.send_image = _fake_image
    try:
        r = client.post(f"/api/conversations/{a}/send-image", headers=AGENT,
                        json={"image_url": "https://ejemplo.com/comprobante.jpg", "caption": "tu comprobante"})
    finally:
        whatsapp.send_image = old_img
    assert r.status_code == 200, r.text
    assert any("ejemplo.com/comprobante.jpg" in m["content"] for m in db.get_messages(a))
    r = client.post(f"/api/conversations/{a}/send-image", headers=AGENT, json={"image_url": "no-es-url"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Caso 27: subida de archivo por el asesor (multipart + guards)
# ---------------------------------------------------------------------------
def case_upload_file():
    auth_mod.ensure_seed()
    client = _client()
    cid = db.get_or_create_conversation("tg:99001", "telegram")

    async def _fake_upload(chat_id, filename, content, mime="", caption=""):
        return {"ok": True, "result": {"photo": [{"file_id": "SMALL"}, {"file_id": "SENTFILEID"}]}}

    old_upload = telegram.send_file_upload
    telegram.send_file_upload = _fake_upload
    try:
        files = {"file": ("foto.png", b"\x89PNG\r\n\x1a\n contenido de prueba", "image/png")}
        r = client.post(f"/api/conversations/{cid}/upload", headers=OWNER,
                        files=files, data={"caption": "tu comprobante"})
        assert r.status_code == 200, r.text
        msgs = db.get_messages(cid)
        out_media = [m for m in msgs if m["role"] == "assistant" and m.get("media")]
        assert out_media and out_media[-1]["media"]["ref"] == "SENTFILEID", out_media
        assert out_media[-1]["media"]["provider"] == "telegram", out_media[-1]
    finally:
        telegram.send_file_upload = old_upload
    r = client.post(f"/api/conversations/{cid}/upload", headers=OWNER,
                    files={"file": ("x.png", b"", "image/png")})
    assert r.status_code == 422, r.text
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = client.post(f"/api/conversations/{cid}/upload", headers=OWNER,
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413, r.text


# ---------------------------------------------------------------------------
# Caso 28: media entrante (Telegram) se guarda, deriva a asesor y da acuse
# ---------------------------------------------------------------------------
def case_incoming_media():
    auth_mod.ensure_seed()
    sent: list = []

    async def _fake_send(chat_id, text, reply_markup=None):
        sent.append(text)
        return {"ok": True}

    old_send = telegram.send_message
    telegram.send_message = _fake_send
    try:
        photo = {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42},
                             "photo": [{"file_id": "small"}, {"file_id": "BIGFILEID"}],
                             "caption": "mi comprobante"}}
        parsed = telegram.parse_update(photo)
        assert parsed["media"]["kind"] == "image" and parsed["media"]["ref"] == "BIGFILEID", parsed
        assert parsed["text"] == "mi comprobante"
        r = _run(telegram.process_update(photo))
        assert r["handled"] and r.get("media") == "image", r
        cid = db.get_or_create_conversation("tg:42", "telegram")
        media_msgs = [m for m in db.get_messages(cid) if m.get("media")]
        assert media_msgs and media_msgs[-1]["role"] == "user", media_msgs
        assert media_msgs[-1]["media"]["ref"] == "BIGFILEID", media_msgs[-1]
        assert db.conversation_status(cid) == "handoff", "media -> pasa a asesor"
        assert sent and "comprobante" in sent[-1].lower(), sent
        conv = db.get_conversation(cid)
        assert conv and conv.get("assigned_to"), f"comprobante debe asignar asesor: {conv}"
        assert conv["lead_data"].get("commercial_stage") == "proof_received", conv["lead_data"]

        doc = {"message": {"chat": {"id": 43, "type": "private"}, "from": {"id": 43},
                           "document": {"file_id": "DOCID", "file_name": "contrato.pdf",
                                        "mime_type": "application/pdf"}}}
        p2 = telegram.parse_update(doc)
        assert p2["media"]["kind"] == "document" and p2["media"]["name"] == "contrato.pdf", p2
    finally:
        telegram.send_message = old_send
    client = _client()
    r = client.get("/api/media?provider=nope&ref=x", headers=OWNER)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Caso 29: Telegram solo responde en privado (ignora grupos salvo allow_groups)
# ---------------------------------------------------------------------------
def case_telegram_private_only():
    priv = telegram.parse_update({"message": {"text": "hola", "chat": {"id": 1, "type": "private"}}})
    grp = telegram.parse_update({"message": {"text": "hola", "chat": {"id": -100, "type": "group"}}})
    assert priv["chat_type"] == "private" and grp["chat_type"] == "group", (priv, grp)
    assert telegram.allows_chat("private") is True
    assert telegram.allows_chat("group") is False and telegram.allows_chat("supergroup") is False
    r = _run(telegram.process_update(
        {"message": {"text": "hola", "chat": {"id": -100, "type": "supergroup"}}}))
    assert r["handled"] is False and r.get("ignored_chat_type") == "supergroup", r
    # Con telegram.allow_groups=true si acepta grupos.
    T.upsert_tenant_config("brasper", {"telegram": {"allow_groups": True}})
    try:
        assert telegram.allows_chat("group") is True
    finally:
        T.upsert_tenant_config("brasper", {"telegram": {"allow_groups": False}})
    assert telegram.allows_chat("group") is False


# ---------------------------------------------------------------------------
# Caso 30: jobs degradan si Redis esta configurado pero inalcanzable (no 500)
# ---------------------------------------------------------------------------
def case_jobs_degrade_when_redis_unreachable():
    old_client = redis_runtime._CLIENT
    try:
        os.environ["REDIS_URL"] = "redis://nonexistent-redis-host-xyzzy:6379/0"
        redis_runtime._CLIENT = None
        assert jobs.enqueue("tenant.changed", {"x": 1}) is False
        assert jobs.dead_letter_count() == 0 and jobs.list_dead_letter() == []
        assert jobs.handle_failure({"type": "x", "max_attempts": 1}, "boom") is False
    finally:
        os.environ["REDIS_URL"] = ""
        redis_runtime._CLIENT = old_client


# ---------------------------------------------------------------------------
# Caso 31: guard — el bot nunca deriva a WhatsApp/redes (entrada + salida LLM)
# ---------------------------------------------------------------------------
def case_no_external_channel_guard():
    from core.agent_graph import sanitize_no_external_channels as clean

    r1 = clean("Con gusto te ayudo. O si prefieres, te paso con un asesor por WhatsApp.")
    assert "whatsapp" not in r1.lower() and "ayudo" in r1.lower(), r1
    r2 = clean("Cotización: recibes 710.29 BRL. ¿Deseas continuar? Escríbenos: https://wa.me/519")
    assert "wa.me" not in r2 and "710.29" in r2, r2
    r3 = clean("Te paso con un asesor por WhatsApp: wa.me/519")
    assert "wa.me" not in r3.lower() and "aquí" in r3.lower(), r3
    assert "instagram" not in clean("Escríbenos por Instagram @brasper para seguir.").lower()
    ok = "Escribe *continuar* y un asesor te atiende aquí."
    assert clean(ok) == ok, clean(ok)

    cid = db.get_or_create_conversation("guard-e2e", "webchat")
    db.add_message(cid, "assistant", "Te paso con un asesor por WhatsApp: wa.me/519")
    old = llm.chat

    async def _wa_chat(t, messages):
        hist = " ".join(m["content"] for m in messages if m["role"] == "assistant")
        assert "wa.me" not in hist and "whatsapp" not in hist.lower(), f"historial no saneado: {hist!r}"
        return {"content": "Claro. Si prefieres te paso por WhatsApp al wa.me/519.",
                "tokens_in": 3, "tokens_out": 3, "model": "stub", "provider": "stub", "cost_usd": 0.0}

    llm.chat = _wa_chat
    try:
        out = _run(engine.handle_message("guard-e2e", "hola, una duda", conversation_id=cid))
    finally:
        llm.chat = old
    assert "whatsapp" not in out["response"].lower() and "wa.me" not in out["response"].lower(), out


# ---------------------------------------------------------------------------
# Caso 32: Telegram — voz entrante se transcribe y el bot responde
# ---------------------------------------------------------------------------
def case_telegram_audio_transcription():
    tenant = T.get_config()
    assert audio_adapter.provider(tenant) == "whisper_service", "brasper usa whisper_service"
    assert audio_adapter.enabled(tenant), "brasper debe tener transcripcion habilitada"
    sent: list = []

    async def _fake_send(chat_id, text, reply_markup=None):
        sent.append(text)
        return {"ok": True}

    async def _fake_typing(chat_id):
        return {"ok": True}

    async def _fake_download(file_id):
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
        cid = db.get_or_create_conversation("tg:7788", "telegram")
        umedia = [m for m in db.get_messages(cid) if m["role"] == "user" and m.get("media")]
        assert umedia and umedia[-1]["media"]["kind"] == "voice", umedia
        assert "Cotizar 500 PEN a BRL" in umedia[-1]["content"], umedia[-1]
        assert sent and "710.29" in sent[-1].replace(",", ""), f"el bot responde la cotizacion: {sent}"

        async def _fail_transcribe(t, content, mime_type="audio/ogg"):
            return {"ok": False, "error": "whisper_service inalcanzable"}

        audio_adapter.transcribe_bytes = _fail_transcribe
        voice2 = {"message": {"chat": {"id": 7799, "type": "private"}, "from": {"id": 7799},
                              "voice": {"file_id": "VOICEID2", "mime_type": "audio/ogg"}}}
        r2 = _run(telegram.process_update(voice2))
        assert r2.get("media") == "voice" and not r2.get("transcribed"), r2
        cid2 = db.get_or_create_conversation("tg:7799", "telegram")
        assert db.conversation_status(cid2) == "handoff", "audio no transcrito -> asesor"
    finally:
        (telegram.send_message, telegram.send_typing, telegram.download_file,
         audio_adapter.transcribe_bytes) = saved


# ---------------------------------------------------------------------------
# Caso 33: audio_adapter elige backend por config y degrada sin credenciales
# ---------------------------------------------------------------------------
def case_audio_adapter_provider_selection():
    t1 = {"id": "x", "audio": {"provider": "whisper_service", "service_url": "http://ws:8090"}}
    assert audio_adapter.provider(t1) == "whisper_service" and audio_adapter.enabled(t1)
    t2 = {"id": "x", "audio": {"provider": "openai", "api_key": "sk-test"}}
    assert audio_adapter.provider(t2) == "openai" and audio_adapter.enabled(t2)
    t3 = {"id": "x", "audio": {"enabled": False, "service_url": "http://ws:8090"}}
    assert not audio_adapter.enabled(t3)
    t4 = {"id": "x", "audio": {"provider": "openai", "api_key_env": "DEFINITELY_UNSET_KEY_XYZ"}}
    assert not audio_adapter.enabled(t4)


# ---------------------------------------------------------------------------
# Caso 34: API Brasper exclusiva — TC en vivo, sin fallback a valores locales
# ---------------------------------------------------------------------------
def case_brasper_api_live_quote():
    tenant = T.get_config()
    saved_enabled, saved_fetch = brasper_api.enabled, brasper_api._fetch
    brasper_api.enabled = lambda t: True

    def _fake_fetch(url):
        if url.endswith("/coin/tax-rate"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "tax": "1.50000000"}]  # vivo 1.50 (config 1.46)
        if url.endswith("/coin/commission"):
            return [{"coin_a": "PEN", "coin_b": "BRL", "percentage": 3.0, "min_amount": 0, "max_amount": 500}]
        return []  # sin cupon vivo -> no debe usar el cupon local

    brasper_api._fetch = _fake_fetch
    try:
        q = quotes.compute("PEN", "BRL", 500, "send")
        assert abs(q["rate"] - 1.50) < 1e-9, f"debe usar la tasa viva 1.50, uso {q['rate']}"
        assert q["amount_receive"] == 727.5, q
        assert q["coupon_code"] is None, "no debe usar el cupon local"
        rates = brasper_api.live_rates(tenant)
        assert rates and rates[0]["pair"] == "PEN->BRL" and rates[0]["rate"] == 1.5, rates
        # Si la API cae: rechaza la cotizacion y nunca filtra la tasa local 1.46.
        brasper_api._fetch = lambda url: None
        q2 = quotes.compute("PEN", "BRL", 500, "send")
        assert q2.get("error") and "rate" not in q2, q2
        # El panel ve el estado real: 503 si la API no devuelve tasas.
        client = _client()
        r = client.get("/api/admin/quote-rates", headers=OWNER)
        assert r.status_code == 503, r.text
        brasper_api._fetch = _fake_fetch
        r = client.get("/api/admin/quote-rates", headers=OWNER)
        assert r.status_code == 200 and r.json()["rates"][0]["rate"] == 1.5, r.text
    finally:
        brasper_api.enabled, brasper_api._fetch = saved_enabled, saved_fetch
    # Con la API apagada el panel lo dice explicitamente (409), no inventa tasas.
    assert _client().get("/api/admin/quote-rates", headers=OWNER).status_code == 409


# ---------------------------------------------------------------------------
# Caso 35: contacto nuevo — el nombre no acredita identidad ni primer envio
# ---------------------------------------------------------------------------
def case_new_lead_and_banner():
    saved_find = brasper_api.find_client
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": None, "ambiguous": False}
    try:
        out = _run(engine.handle_message("lead-nuevo-xyz", "hola"))
        assert out["new_lead"] is True and out.get("banner") is None, out
        assert "nombre completo" in out["response"].lower(), out
        out2 = _run(engine.handle_message("lead-nuevo-xyz", "Ana Pérez",
                                          conversation_id=out["conversation_id"]))
        assert out2["new_lead"] is False, out2
        assert out2.get("banner") is None, "un nombre nuevo no demuestra elegibilidad"
        assert not db.get_lead_data(out["conversation_id"]).get("brasper_user_id")
        client = _client()
        r = client.post("/api/chat", headers=OWNER,
                        json={"message": "hola", "user_ref": "lead-web-1"})
        assert r.status_code == 200 and r.json()["new_lead"] is True, r.text
    finally:
        brasper_api.find_client = saved_find


# ---------------------------------------------------------------------------
# Caso 36: la cotizacion persiste datos del lead y la fila en `quotes` (fee real)
# ---------------------------------------------------------------------------
def case_lead_data_and_quote_persisted():
    out = _run(engine.handle_message("lead-data-xyz", "Cotizar 500 PEN a BRL"))
    lead = db.get_lead_data(out["conversation_id"])
    assert lead.get("ruta") == "PEN->BRL" and lead.get("modo") == "send", lead
    assert lead.get("monto_enviar") == 500.0 and lead.get("monto_recibir") == 710.29, lead
    assert lead.get("tasa") == 1.46 and lead.get("estado_tc") == "activo", lead
    assert lead.get("canal") == "webchat" and lead.get("aplica_promo") is True, lead
    assert db.is_first_contact("lead-data-xyz") is False
    with db.connect() as con:
        row = con.execute("SELECT * FROM quotes WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                          (out["conversation_id"], 1)).fetchone()
    assert row is not None, "la cotizacion debe guardarse en quotes"
    q = dict(row)
    assert (q["from_currency"], q["to_currency"]) == ("PEN", "BRL"), q
    assert q["amount_send"] == 500.0 and q["amount_receive"] == 710.29, q
    assert q["exchange_rate"] == 1.46, q
    assert q["fee"] == 13.5, f"fee debe ser la comision neta cobrada, fue {q['fee']}"
    # El panel expone el lead estructurado junto con los mensajes.
    r = _client().get(f"/api/conversations/{out['conversation_id']}", headers=OWNER)
    assert r.status_code == 200 and r.json()["lead"]["ruta"] == "PEN->BRL", r.text


# ---------------------------------------------------------------------------
# Caso 37: reglas de negocio — vigencia TC 20 min + monto alto deriva a asesor
# ---------------------------------------------------------------------------
def case_quote_business_rules():
    auth_mod.ensure_seed()
    out = _run(engine.handle_message("rules-tc", "Cotizar 500 PEN a BRL"))
    assert "20 min" in out["response"] and out["handoff"] is False, out
    out2 = _run(engine.handle_message("rules-high", "Cotizar 8000 PEN a BRL"))
    assert out2["handoff"] is True and out2["usage"] is None, out2
    assert "asesor" in out2["response"].lower(), out2["response"]
    assert "8000.00" in out2["response"].replace(",", ""), "es la cotizacion de 8000"
    mine = [c for c in db.list_conversations() if c["user_ref"] == "rules-high"]
    assert mine and mine[0]["assigned_to"] and mine[0]["status"] == "handoff", mine


# ---------------------------------------------------------------------------
# Caso 38: checkout muestra cuentas oficiales sin crear transaccion
# ---------------------------------------------------------------------------
def case_checkout_deposit_accounts():
    cid = db.get_or_create_conversation("user-checkout-1", "webchat")
    db.merge_lead_data(cid, {"brasper_user_id": "client-1", "ruta": "PEN->BRL",
                             "commercial_stage": "quoted"})
    saved = brasper_api.deposit_accounts
    brasper_api.deposit_accounts = lambda tenant_arg, currency: {"ok": True, "data": [{
        "id": "bank-1", "bank": "Banco Oficial", "company": "Brasper SAC",
        "account": "000-111", "pix": None,
    }]}
    try:
        out = _run(engine.handle_message("user-checkout-1", "listo, ¿cómo pago?", conversation_id=cid))
    finally:
        brasper_api.deposit_accounts = saved
    assert out["handoff"] is False and out["usage"] is None, out
    assert "Banco Oficial" in out["response"] and "comprobante" in out["response"].lower(), out
    lead = db.get_lead_data(cid)
    assert lead["commercial_stage"] == "awaiting_deposit" and lead["deposit_accounts_shown"] == ["bank-1"], lead
    # Un pedido de cotizacion COMPLETO con verbo de envio NO es checkout: cotiza.
    out3 = _run(engine.handle_message("user-checkout-3", "quiero hacer el envío de 500 PEN a BRL"))
    assert out3["handoff"] is False and "710.29" in out3["response"].replace(",", ""), out3
    assert "continuar" in out3["response"].lower() and "wa.me" not in out3["response"], out3


# ---------------------------------------------------------------------------
# Caso 39: onboarding progresivo — cotiza primero, documento solo al continuar
# ---------------------------------------------------------------------------
def case_client_onboarding_without_transaction():
    saved = (brasper_api.upsert_client, brasper_api.find_client, brasper_api.deposit_accounts)
    calls = []
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": None, "ambiguous": False}
    brasper_api.upsert_client = lambda tenant_arg, lead: (
        calls.append(dict(lead)), {"ok": True, "data": {"id": "client-uuid", "created": True}})[1]
    brasper_api.deposit_accounts = lambda *args, **kwargs: {"ok": True, "data": [{
        "id": "bank-1", "bank": "Banco Oficial", "company": "Brasper SAC", "account": "000-111"}]}
    try:
        assert not hasattr(brasper_api, "register_operation"), "la IA no debe crear operaciones"
        out = _run(engine.handle_message("wa:51999111222", "hola", channel="whatsapp"))
        cid = out["conversation_id"]
        assert "nombre completo" in out["response"].lower(), out
        out = _run(engine.handle_message("wa:51999111222", "Ana María Pérez Soto",
                                         channel="whatsapp", conversation_id=cid))
        assert "cuánto" in out["response"].lower(), out
        out = _run(engine.handle_message("wa:51999111222", "Cotizar 500 PEN a BRL",
                                         channel="whatsapp", conversation_id=cid))
        assert "cotización" in out["response"].lower() and "documento" not in out["response"].lower(), out
        out = _run(engine.handle_message("wa:51999111222", "continuar",
                                         channel="whatsapp", conversation_id=cid))
        assert "tipo de documento" in out["response"].lower(), out
        out = _run(engine.handle_message("wa:51999111222", "pasaporte lunar",
                                         channel="whatsapp", conversation_id=cid))
        assert "no reconocí" in out["response"].lower(), out
        for answer in ("DNI", "12345678"):
            out = _run(engine.handle_message("wa:51999111222", answer,
                                             channel="whatsapp", conversation_id=cid))
        lead = db.get_lead_data(cid)
        assert lead["brasper_user_id"] == "client-uuid" and lead["telefono"] == "999111222", lead
        assert lead["numero_documento"] == "12345678" and calls, lead
        assert calls[0]["nombres"] == "Ana María" and calls[0]["apellidos"] == "Pérez Soto", calls[0]
        assert "Banco Oficial" in out["response"] and "correo" not in out["response"].lower(), out
        assert "transacci" not in out["response"].lower(), out
        # El cliente queda vinculado en la tabla customers (por telefono del canal).
        conv = db.get_conversation(cid)
        assert conv.get("customer_id"), conv
    finally:
        brasper_api.upsert_client, brasper_api.find_client, brasper_api.deposit_accounts = saved


# ---------------------------------------------------------------------------
# Caso 40: cliente recurrente reconocido por telefono (WhatsApp)
# ---------------------------------------------------------------------------
def case_returning_client_by_phone():
    saved_find = brasper_api.find_client
    brasper_api.find_client = lambda *args, **kwargs: {"ok": True, "data": {
        "id": "client-existing", "names": "Carlos", "lastnames": "García",
        "phone": 999222333, "code_phone": "+51", "document_type": "dni",
        "document_number": "87654321",
    }}
    try:
        out = _run(engine.handle_message("wa:51999222333", "hola", channel="whatsapp"))
        lead = db.get_lead_data(out["conversation_id"])
        assert "Carlos" in out["response"] and "nuevamente" in out["response"], out
        assert lead.get("brasper_user_id") == "client-existing", lead
        assert "documento" not in out["response"].lower(), out
    finally:
        brasper_api.find_client = saved_find


# ---------------------------------------------------------------------------
# Caso 41: falla de cuentas -> handoff real sin exponer error tecnico
# ---------------------------------------------------------------------------
def case_deposit_failure_creates_handoff():
    auth_mod.ensure_seed()
    cid = db.get_or_create_conversation("deposit-failure", "webchat")
    db.merge_lead_data(cid, {"brasper_user_id": "client-1", "ruta": "PEN->BRL",
                             "commercial_stage": "quoted"})
    saved = brasper_api.deposit_accounts
    brasper_api.deposit_accounts = lambda *args, **kwargs: {"ok": False, "error": "timeout"}
    try:
        out = _run(engine.handle_message("deposit-failure", "continuar", conversation_id=cid))
    finally:
        brasper_api.deposit_accounts = saved
    assert out["handoff"] is True, out
    assert "asesor se comunicará" in out["response"].lower(), out
    assert "timeout" not in out["response"].lower(), out
    assert db.conversation_status(cid) == "handoff"
    assert db.get_conversation(cid).get("assigned_to"), "debe asignar asesor"


# ---------------------------------------------------------------------------
# Caso 42: integracion Brasper usa solo endpoints IA privados + borrado guardado
# ---------------------------------------------------------------------------
def case_private_brasper_ai_contracts():
    tenant = T.get_config()
    saved = brasper_api._integration_request
    calls = []

    def fake_request(_tenant, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith("/lookup"):
            return {"ok": True, "data": {"found": True, "ambiguous": False, "client": {
                "id": "client-secure", "names": "Ana", "lastnames": "Pérez",
                "document_verified": True, "is_first_transfer": False}}}
        if path.endswith("/upsert"):
            return {"ok": True, "data": {"id": "client-secure", "created": False}}
        if method == "DELETE":
            return {"ok": True, "data": None, "status": 204}
        return {"ok": True, "data": []}

    brasper_api._integration_request = fake_request
    try:
        found = brasper_api.find_client(tenant, phone="999111222", code_phone="+51")
        assert found["data"]["id"] == "client-secure", found
        upserted = brasper_api.upsert_client(tenant, {
            "nombres": "Ana", "apellidos": "Pérez", "tipo_documento": "dni",
            "numero_documento": "12345678", "codigo_telefono": "+51", "telefono": "999111222"})
        assert upserted["ok"] is True, upserted
        brasper_api.deposit_accounts(tenant, "PEN")
        # Sin telefono no se intenta crear nada.
        assert brasper_api.upsert_client(tenant, {"nombres": "X"})["ok"] is False
        client = _client()
        r = client.delete("/api/admin/brasper/clients/abc-123?expected_name=Ana", headers=OWNER)
        assert r.status_code == 200 and r.json()["deleted"] is True, r.text
        assert client.delete("/api/admin/brasper/clients/abc-123", headers=OWNER).status_code == 422, \
            "el nombre esperado es un guard obligatorio"
        assert client.delete("/api/admin/brasper/clients/abc-123?expected_name=Ana",
                             headers=AGENT).status_code == 403
    finally:
        brasper_api._integration_request = saved
    paths = [item[1] for item in calls]
    assert paths == ["/brasper/ai/clients/lookup", "/brasper/ai/clients/upsert",
                     "/brasper/ai/deposit-accounts", "/user/abc-123"], paths
    # Sin secreto de integracion, la escritura no se intenta (y no rompe).
    old_secret = os.environ.pop("BRASPER_IA_SHARED_SECRET", None)
    try:
        assert brasper_api.deposit_accounts(tenant, "PEN")["ok"] is False
    finally:
        if old_secret is not None:
            os.environ["BRASPER_IA_SHARED_SECRET"] = old_secret


# ---------------------------------------------------------------------------
# Caso 43: borrado de conversacion con guard de identidad (panel)
# ---------------------------------------------------------------------------
def case_conversation_delete_guard():
    client = _client()
    cid = db.get_or_create_conversation("user-del", "webchat")
    db.add_message(cid, "user", "borrame")
    r = client.delete(f"/api/conversations/{cid}?expected_user_ref=otro", headers=OWNER)
    assert r.status_code == 409, r.text
    assert client.delete(f"/api/conversations/{cid}?expected_user_ref=user-del",
                         headers=AGENT).status_code == 403
    r = client.delete(f"/api/conversations/{cid}?expected_user_ref=user-del", headers=OWNER)
    assert r.status_code == 200 and r.json()["deleted"], r.text
    assert db.get_conversation(cid) is None and db.get_messages(cid) == []
    r = client.delete(f"/api/conversations/{cid}?expected_user_ref=user-del", headers=OWNER)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Caso 44: E2E HTTP — el prompt configurado desde la Admin API llega al LLM
# ---------------------------------------------------------------------------
def case_bot_config_e2e():
    captured: dict = {}
    original_prompt = T.get_config()["system_prompt"]

    async def _capture_chat(tenant_arg, messages):
        captured["messages"] = messages
        return {"content": "ok", "tokens_in": 5, "tokens_out": 2, "model": "stub",
                "provider": "stub", "cost_usd": 0.0}

    old_chat = llm.chat
    llm.chat = _capture_chat
    try:
        client = _client()
        marker = "PROMPT_CONFIGURADO_DESDE_PANEL_XYZ"
        r = client.patch("/api/admin/tenants", headers=OWNER,
                         json={"config": {"system_prompt": marker, "llm": {"temperature": 0.3}}})
        assert r.status_code == 200 and r.json()["tenant"]["system_prompt"] == marker, r.text
        r2 = client.post("/api/chat", headers=OWNER,
                         json={"message": "hola necesito informacion", "user_ref": "cfg-e2e"})
        assert r2.status_code == 200, r2.text
        system = " ".join(m["content"] for m in captured["messages"] if m["role"] == "system")
        assert marker in system, f"el LLM debe recibir el prompt configurado: {system[:200]}"
        assert "idioma" in system.lower(), "la linea de idioma se antepone al prompt"
        # El deep-merge no borra el cotizador.
        r3 = client.post("/api/chat", headers=OWNER,
                         json={"message": "Cotizar 500 PEN a BRL", "user_ref": "cfg-e2e"})
        assert "710.29" in r3.json()["response"].replace(",", ""), r3.json()["response"]
        assert client.post("/api/chat", headers=OWNER,
                           json={"message": "   ", "user_ref": "cfg-e2e"}).status_code == 422
    finally:
        llm.chat = old_chat
        T.upsert_tenant_config("brasper", {"system_prompt": original_prompt})


# ---------------------------------------------------------------------------
# Caso 45: endpoint publico de compatibilidad del webchat (ia.finzeler.com)
# ---------------------------------------------------------------------------
def case_webchat_compat_endpoint():
    client = _client()
    r = client.post("/consulta-webchat", json={"message": "Cotizar 500 PEN a BRL",
                                               "session_id": "sess-compat-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_id"] == "sess-compat-1", body
    assert "710.29" in body["response"].replace(",", ""), body["response"]
    assert client.post("/consulta-webchat", json={"message": ""}).status_code == 422
    r = client.post("/consulta-webchat?conversation_id=sess-compat-1",
                    json={"message": "¿y para 1000 soles?"})
    assert r.status_code == 200 and r.json()["conversation_id"] == "sess-compat-1", r.text
    # 1000 PEN: comision 2% = 20, cupon 10% = 2 -> 982 * 1.46 = 1433.72
    assert "1433.72" in r.json()["response"].replace(",", ""), r.json()["response"]


# ---------------------------------------------------------------------------
# Stub del LLM: ningun caso llama al LLM real
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


llm.chat = _fake_chat
# Por defecto se cotiza con las tasas del CONFIG (deterministas, sin red). El caso
# 34 enciende la API con datos simulados para probar la integracion en vivo.
brasper_api.enabled = lambda tenant: False
# Secreto de integracion simulado: los casos que lo necesitan parchean el request.
os.environ.setdefault("BRASPER_IA_SHARED_SECRET", "test-secret")


def case_panel_inbox_v2():
    """Panel v2: filtros/since/after, sender bot vs asesor, notas internas,
    respuestas rapidas, cache de adjuntos y web vitals."""
    import time
    client = _client()
    # Dos conversaciones: una en cola (handoff sin asesor) y una con el bot.
    c1 = db.get_or_create_conversation("wa:51900000001", "whatsapp")
    db.add_message(c1, "user", "quiero enviar 300 reales")
    db.add_message(c1, "assistant", "Perfeito, cotizacion lista")
    db.set_conversation_status(c1, "handoff")
    db.merge_lead_data(c1, {"nombre": "Marcia Teste", "monto_enviar": "R$ 300"})
    time.sleep(0.01)
    c2 = db.get_or_create_conversation("tg:777001", "telegram")
    db.add_message(c2, "user", "hola")
    db.add_message(c2, "assistant", "Hola, soy el asistente")

    # Lista: campos nuevos y filtros.
    r = client.get("/api/conversations", headers=OWNER)
    assert r.status_code == 200, r.text
    rows = {c["id"]: c for c in r.json()["conversations"]}
    assert rows[c1]["lead_name"] == "Marcia Teste" and rows[c1]["last_role"] == "assistant", rows[c1]
    assert rows[c1]["waiting_since"] and rows[c2]["waiting_since"] is None
    ids = lambda resp: {c["id"] for c in resp.json()["conversations"]}  # noqa: E731
    assert c1 in ids(client.get("/api/conversations?status=handoff", headers=OWNER))
    assert c1 not in ids(client.get("/api/conversations?status=active", headers=OWNER))
    assert c2 in ids(client.get("/api/conversations?channel=telegram", headers=OWNER))
    assert c1 in ids(client.get("/api/conversations?assigned=none", headers=OWNER))
    assert ids(client.get("/api/conversations?q=marcia", headers=OWNER)) == {c1}
    assert ids(client.get("/api/conversations?q=51900000001", headers=OWNER)) == {c1}
    assert client.get("/api/conversations?status=raro", headers=OWNER).status_code == 422
    # since: solo lo actualizado despues del cursor.
    since = rows[c1]["updated_at"]
    r_since = client.get("/api/conversations", params={"since": since}, headers=OWNER)  # "+00:00" va codificado
    later = ids(r_since)
    assert c2 in later, later
    assert all(c["updated_at"] >= since for c in r_since.json()["conversations"]), "since debe ser inclusivo y filtrar lo anterior"
    old_ones = [c for c in r.json()["conversations"] if c["updated_at"] < since]
    assert all(c["id"] not in later for c in old_ones), "since no debe traer conversaciones anteriores"
    # paginacion por cursor.
    r = client.get("/api/conversations?limit=1", headers=OWNER)
    assert r.json()["next_before"] is not None and len(r.json()["conversations"]) == 1
    # El agente no puede filtrar por conversaciones de otro.
    assert client.get("/api/conversations?assigned=owner@agencia.com", headers=AGENT).status_code == 403

    # sender: el bot es 'bot'; el asesor que responde es 'agent' con su email.
    old_send = whatsapp.send_text

    async def _fake_wa(*a, **k):
        return {"sent": True}
    whatsapp.send_text = _fake_wa
    try:
        before = client.get(f"/api/conversations/{c1}", headers=OWNER).json()
        assert before["partial"] is False and before["notes"] == []
        assert [m["sender"] for m in before["messages"]] == ["user", "bot"], before["messages"]
        last_ts = before["messages"][-1]["created_at"]
        time.sleep(0.01)
        r = client.post(f"/api/conversations/{c1}/reply", headers=OWNER, json={"text": "Hola, te atiendo"})
        assert r.status_code == 200, r.text
        inc = client.get(f"/api/conversations/{c1}", params={"after": last_ts}, headers=OWNER).json()
        # after es inclusivo (segundos): trae el nuevo y, como mucho, los del mismo segundo.
        assert inc["partial"] is True and 1 <= len(inc["messages"]) <= len(before["messages"]) + 1, inc
        assert all(m["created_at"] >= last_ts for m in inc["messages"]), inc
        assert inc["messages"][-1]["sender"] == "agent" and inc["messages"][-1]["agent_email"] == "owner@agencia.com"
    finally:
        whatsapp.send_text = old_send

    # Notas internas: se guardan, no generan mensaje al cliente, respetan el guard de asesor.
    n_msgs = len(db.get_messages(c1))
    r = client.post(f"/api/conversations/{c1}/notes", headers=OWNER, json={"text": "Cliente VIP, priorizar"})
    assert r.status_code == 200 and r.json()["note"]["author"] == "owner@agencia.com", r.text
    assert len(db.get_messages(c1)) == n_msgs, "la nota no debe ser un mensaje"
    assert client.post(f"/api/conversations/{c1}/notes", headers=OWNER, json={"text": "  "}).status_code == 422
    notes = client.get(f"/api/conversations/{c1}/notes", headers=OWNER).json()["notes"]
    assert len(notes) == 1 and notes[0]["text"] == "Cliente VIP, priorizar"
    # c1 quedo asignada al owner al responder: el agente no puede anotar ahi.
    assert client.post(f"/api/conversations/{c1}/notes", headers=AGENT, json={"text": "x"}).status_code == 403

    # Respuestas rapidas: predeterminadas con variables documentadas.
    r = client.get("/api/quick-replies", headers=AGENT)
    assert r.status_code == 200 and r.json()["quick_replies"], r.text
    assert "nombre" in r.json()["variables"]
    assert all("{" in q["text"] or q["text"] for q in r.json()["quick_replies"])

    # Adjuntos: el proxy manda Cache-Control privado (el panel no re-descarga en cada poll).
    old_dl = telegram.download_file

    async def _fake_dl(ref):
        return b"\x89PNGfake", "image/png"
    telegram.download_file = _fake_dl
    try:
        db.add_message(c1, "user", "Synthetic media", media={"provider": "telegram", "ref": "abc", "kind": "image"})
        r = client.get(f"/api/media?provider=telegram&ref=abc&conversation_id={c1}", headers=OWNER)
        assert r.status_code == 200 and r.headers.get("cache-control") == "private, no-store", r.headers
        assert r.headers.get("content-security-policy") == "sandbox"
        assert r.headers["content-type"].startswith("image/png")
        assert client.get(f"/api/media?provider=telegram&ref=abc&conversation_id={c1}", headers=AGENT).status_code == 403
        assert client.get(f"/api/media?provider=telegram&ref=abc&conversation_id={c2}", headers=OWNER).status_code == 404
    finally:
        telegram.download_file = old_dl

    # Web vitals: cualquier usuario del panel reporta; aparecen en /api/ops/metrics.
    assert client.post("/api/ops/web-vitals", json={"name": "LCP", "value": 1200}).status_code == 401
    r = client.post("/api/ops/web-vitals", headers=AGENT, json={"name": "LCP", "value": 1200, "path": "/conversaciones", "rating": "good"})
    assert r.status_code == 200, r.text
    assert client.post("/api/ops/web-vitals", headers=AGENT, json={"name": "XYZ", "value": 1}).status_code == 422
    snap = client.get("/api/ops/metrics", headers=OWNER).json()
    assert snap["web_vitals"]["LCP"]["samples"] >= 1 and snap["web_vitals"]["LCP"]["p75"] == 1200.0, snap["web_vitals"]


# ---------------------------------------------------------------------------
# Casos 47-56: plan de atencion autonoma (conocimiento, estado, anti-bucle,
# webhook/identidad/coex, presencia+claim, etiquetas, audios, documentos
# publicos, contratos de herramientas, metricas por flujo)
# ---------------------------------------------------------------------------
from core import audio_flow, audio_review, features, handoff_summary, idempotency, knowledge, presence, public_docs, tool_contracts  # noqa: E402


def _with_features(**flags):
    """Context manager simple para alterar flags en la config temporal."""
    class _Ctx:
        def __enter__(self):
            cfg = T.get_config()
            self.prev = cfg.get("features")
            cfg["features"] = {**(self.prev or {}), **flags}
            return self

        def __exit__(self, *a):
            cfg = T.get_config()
            if self.prev is None:
                cfg.pop("features", None)
            else:
                cfg["features"] = self.prev
    return _Ctx()


def case_knowledge_faq_with_source():
    out = _run(engine.handle_message("kb-1", "¿Qué documentos necesito para enviar?"))
    assert out["usage"] is None and out["handoff"] is False, out
    assert "DNI" in out["response"] and "Fuente" in out["response"] and "rev. 2026" in out["response"], out["response"]
    assert out["flow"] == "info", out
    # Portugues: variante del mismo grupo en el idioma del usuario.
    out_pt = _run(engine.handle_message("kb-2", "quais documentos preciso para me cadastrar?"))
    assert "CPF" in out_pt["response"] and "Fonte" in out_pt["response"], out_pt["response"]
    # Pregunta frecuente SIN respuesta aprobada (borrador): incertidumbre explicita, sin inventar ni derivar.
    out_miss = _run(engine.handle_message("kb-3", "¿cuánto demora en llegar el dinero a Brasil?"))
    assert out_miss["usage"] is None and out_miss["handoff"] is False, out_miss
    assert "no tengo esa información" in out_miss["response"].lower() and "asesor" in out_miss["response"].lower()
    assert not any(ch.isdigit() for ch in out_miss["response"].split("Cotizar")[0]), "no inventa tiempos"
    # Cotizar sigue teniendo prioridad sobre la FAQ ("cómo cotizo 500 soles a reales" trae monto+monedas).
    out_q = _run(engine.handle_message("kb-4", "Cotizar 500 PEN a BRL"))
    assert out_q["flow"] == "quote" and out_q["usage"] is None, out_q
    # Flag apagada -> la pregunta va al LLM (stub).
    with _with_features(knowledge=False):
        out_off = _run(engine.handle_message("kb-5", "¿Qué documentos aceptan?"))
    assert out_off["response"] == "[respuesta simulada]", out_off
    client = _client()
    r = client.get("/api/knowledge", headers=AGENT)
    assert r.status_code == 200 and r.json()["approved"] >= 10 and r.json()["draft"] >= 1, r.text
    assert knowledge.search("horario de atencion", "es") is None, "los borradores no se sirven"


def case_status_intent_handoff_with_summary():
    auth_mod.ensure_seed()
    out = _run(engine.handle_message("st-1", "hola, ¿ya llegó mi envío de ayer?"))
    assert out["handoff"] is True and out["usage"] is None and out["flow"] == "status", out
    low = out["response"].lower()
    assert "asesor" in low and "acreditado" not in low and "confirmado" not in low, out["response"]
    conv = db.get_conversation(out["conversation_id"])
    assert conv["status"] == "handoff" and conv.get("assigned_to"), conv
    h = conv["lead_data"].get("handoff")
    assert h and h["reason"] == "status_lookup_unavailable" and "Pendiente" in h["text"], h
    # El contrato documenta la ausencia de API de estado.
    tools = {t["name"]: t for t in tool_contracts.describe()}
    assert tools["status.lookup"]["available"] is True  # endpoint exists; rollout flag remains off
    out_pt = _run(engine.handle_message("st-2", "meu envio já chegou?"))
    # Frase corta: la deteccion de idioma puede caer en es; lo relevante es la derivacion honesta.
    assert out_pt["handoff"] is True and ("assessor" in out_pt["response"].lower() or "asesor" in out_pt["response"].lower()), out_pt


def case_anti_loop_limits_repetition():
    auth_mod.ensure_seed()
    old = llm.chat

    async def _same(tenant, messages):
        return {"content": "Claro, cuéntame más sobre tu consulta.", "provider": "stub", "model": "stub-model",
                "tokens_in": 10, "tokens_out": 5, "cost_usd": 0.0}

    llm.chat = _same
    try:
        o1 = _run(engine.handle_message("loop-1", "hola, tengo una duda general"))
        cid = o1["conversation_id"]
        assert o1["response"].startswith("Claro"), o1
        o2 = _run(engine.handle_message("loop-1", "no entiendo", conversation_id=cid))
        assert "repitiendo" in o2["response"].lower() and o2["handoff"] is False, o2
        # El mensaje de "repitiendo" rompe la racha; una tercera repeticion identica vuelve a contar.
        o3 = _run(engine.handle_message("loop-1", "sigo sin entender", conversation_id=cid))
        assert o3["response"].startswith("Claro"), o3  # primera vez tras el aviso
        o4 = _run(engine.handle_message("loop-1", "???", conversation_id=cid))
        assert "repitiendo" in o4["response"].lower(), o4
        o5 = _run(engine.handle_message("loop-1", "otra vez", conversation_id=cid))
        assert o5["response"].startswith("Claro"), o5
        # Con la flag apagada no interviene.
        with _with_features(anti_loop=False):
            o6 = _run(engine.handle_message("loop-2", "tengo una consulta general"))
            o7 = _run(engine.handle_message("loop-2", "sigue siendo general", conversation_id=o6["conversation_id"]))
        assert o7["response"].startswith("Claro"), o7
    finally:
        llm.chat = old


def _wa_payload(msg_id, text, pnid="PNID_BRASPER_123", frm="51911111111", name="Marcia Teste", extra=None):
    contact = {"profile": {"name": name}, "wa_id": frm}
    if extra:
        contact.update(extra)
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": pnid}, "contacts": [contact],
        "messages": [{"from": frm, "id": msg_id, "timestamp": "1", "type": "text", "text": {"body": text}}]}}]}]}


def case_webhook_dedup_identity_coex():
    sent: list = []

    async def _fake_send(to, text, connection=None, **kw):
        sent.append((to, text, (connection or {}).get("id")))
        return {"sent": True}

    old_send = whatsapp.send_text
    whatsapp.send_text = _fake_send
    os.environ["WA_PHONE_NUMBER_ID_BRASPER"] = "PNID_BRASPER_123"
    client = _client()
    try:
        body = _wa_payload("wamid.ONE", "Cotizar 100 PEN a BRL", extra={"user_id": "bsuid-abc"})
        r = client.post("/webhook", json=body)
        assert r.status_code == 200, r.text
        res = r.json()["results"][0]
        assert res["resolved"] and res["sent"] and res.get("flow") == "quote", res
        assert sent and sent[-1][2] == "default", "la respuesta sale por la conexion de origen"
        # Identidad conservada sin asumir semantica de campos extra.
        conv = [c for c in db.list_conversations() if c["user_ref"] == "wa:51911111111"][0]
        lead = db.get_conversation(conv["id"])["lead_data"]  # en la lista viene como JSON string
        assert lead.get("wa_profile_name") == "Marcia Teste" and lead.get("wa_identity") == {"user_id": "bsuid-abc"}, lead
        assert conv.get("connection_id") == "default", conv
        assert conv.get("lead_name") == "Marcia Teste" or lead.get("nombre") is None  # el nombre de perfil no es identidad verificada
        n_before = len(sent)
        # Webhook repetido (mismo id): no responde dos veces.
        r2 = client.post("/webhook", json=body)
        assert r2.json()["results"][0].get("duplicate") is True, r2.text
        assert len(sent) == n_before, "duplicado no debe reenviar"
        # Estados de entrega e historial Coex: nunca disparan respuestas.
        st = {"entry": [{"changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": "PNID_BRASPER_123"},
              "statuses": [{"id": "wamid.ONE", "status": "delivered", "recipient_id": "51911111111"}]}}]}]}
        assert client.post("/webhook", json=st).json()["results"][0]["status"] == "delivered"
        hist = {"entry": [{"changes": [{"field": "history", "value": {"metadata": {"phone_number_id": "PNID_BRASPER_123"}, "history": []}}]}]}
        assert client.post("/webhook", json=hist).json()["results"][0]["ignored"] is True
        assert len(sent) == n_before
        # Eco desde la app del celular: ignorado sin coex; con coex -> actividad humana + takeover.
        echo = {"entry": [{"changes": [{"field": "smb_message_echoes", "value": {"metadata": {"phone_number_id": "PNID_BRASPER_123"},
                "message_echoes": [{"id": "wamid.ECHO1", "to": "51911111111", "type": "text", "text": {"body": "Hola, soy Nadia desde el celular"}}]}}]}]}
        assert client.post("/webhook", json=echo).json()["results"][0].get("ignored") is True
        cfg = T.get_config()
        prev_wa, prev_f = dict(cfg["whatsapp"]), cfg.get("features")
        cfg["whatsapp"] = {**cfg["whatsapp"], "mode": "coex"}
        cfg["features"] = {**(prev_f or {}), "coex": True}
        try:
            echo["entry"][0]["changes"][0]["value"]["message_echoes"][0]["id"] = "wamid.ECHO2"
            res = client.post("/webhook", json=echo).json()["results"][0]
            assert res.get("takeover") is True, res
            conv = db.get_conversation(res["conversation_id"])
            assert conv["status"] == "handoff", conv
            msgs = db.get_messages(res["conversation_id"])
            assert msgs[-1]["sender"] == "agent" and msgs[-1]["agent_email"] == "whatsapp-app", msgs[-1]
            # El bot no responde por encima del humano del celular.
            r3 = client.post("/webhook", json=_wa_payload("wamid.TWO", "gracias!"))
            assert r3.json()["results"][0].get("paused") is True, r3.text
            assert len(sent) == n_before, "bot en pausa: no envia"
        finally:
            cfg["whatsapp"] = prev_wa
            if prev_f is None:
                cfg.pop("features", None)
            else:
                cfg["features"] = prev_f
        # Registro de conexiones sin secretos.
        r = client.get("/api/whatsapp/connections", headers=OWNER)
        assert r.status_code == 200 and r.json()["connections"][0]["id"] == "default", r.text
        assert "token" not in r.json()["connections"][0]
    finally:
        whatsapp.send_text = old_send
        os.environ.pop("WA_PHONE_NUMBER_ID_BRASPER", None)


def case_presence_and_atomic_claim():
    auth_mod.ensure_seed()
    client = _client()
    assert client.post("/api/presence", json={"status": "available"}).status_code == 401
    assert client.post("/api/presence", headers=AGENT, json={"status": "raro"}).status_code == 422
    r = client.post("/api/presence", headers=AGENT, json={"status": "away"})
    assert r.status_code == 200 and r.json()["status"] == "away", r.text
    adv = client.get("/api/advisors", headers=OWNER).json()
    assert adv["advisors"][0]["presence"]["status"] == "away", adv
    # Con presencia obligatoria y el unico asesor ausente -> cola (sin asignar) y aviso al cliente.
    with _with_features(presence_required=True):
        out = _run(engine.handle_message("pres-1", "quiero un asesor"))
        conv = db.get_conversation(out["conversation_id"])
        assert conv["status"] == "handoff" and not conv.get("assigned_to"), conv
        assert "cola" in out["response"].lower(), out["response"]
        assert conv["lead_data"]["handoff"]["reason"] == "no_advisor_available"
        # Asesor disponible -> se asigna.
        client.post("/api/presence", headers=AGENT, json={"status": "available"})
        out2 = _run(engine.handle_message("pres-2", "quiero un asesor"))
        assert db.get_conversation(out2["conversation_id"])["assigned_to"] == "agent@brasper.com"
    # Claim atomico: la conversacion ya es del agente; el owner no la toma por encima (409).
    cid = out2["conversation_id"]
    assert db.claim_conversation(cid, "agent@brasper.com") is True
    assert db.claim_conversation(cid, "owner@agencia.com") is False
    r = client.post(f"/api/conversations/{cid}/status", headers=OWNER, json={"status": "handoff"})
    assert r.status_code == 409, r.text
    # Libre -> la toma quien llegue primero; el segundo recibe 409.
    free = db.get_or_create_conversation("pres-3", "webchat")
    db.add_message(free, "user", "hola")
    r1 = client.post(f"/api/conversations/{free}/status", headers=AGENT, json={"status": "handoff"})
    r2 = client.post(f"/api/conversations/{free}/status", headers=OWNER, json={"status": "handoff"})
    assert r1.status_code == 200 and r2.status_code == 409, (r1.text, r2.text)
    assert db.get_conversation(free)["lead_data"]["handoff"]["reason"] == "manual"


def case_tags_filter():
    client = _client()
    cid = db.get_or_create_conversation("tag-1", "webchat")
    db.add_message(cid, "user", "hola")
    assert client.post(f"/api/conversations/{cid}/tags", headers=OWNER, json={"tag": "  "}).status_code == 422
    r = client.post(f"/api/conversations/{cid}/tags", headers=OWNER, json={"tag": " Monto Alto "})
    assert r.status_code == 200 and r.json()["tags"] == ["monto alto"], r.text
    client.post(f"/api/conversations/{cid}/tags", headers=OWNER, json={"tag": "reclamo"})
    r = client.get("/api/conversations", params={"tag": "reclamo"}, headers=OWNER)
    ids = {c["id"] for c in r.json()["conversations"]}
    assert ids == {cid}, ids
    assert r.json()["conversations"][0]["tags"] == ["monto alto", "reclamo"]
    r = client.delete(f"/api/conversations/{cid}/tags/reclamo", headers=OWNER)
    assert r.json()["tags"] == ["monto alto"]
    assert any(t["tag"] == "monto alto" for t in client.get("/api/tags", headers=AGENT).json()["tags"])
    assert client.get(f"/api/conversations/{cid}", headers=OWNER).json()["tags"] == ["monto alto"]


def case_audio_review_and_flow():
    auth_mod.ensure_seed()
    r = audio_review.review_transcript("quiero enviar 500 o 600 soles a Brasil")
    assert r["ambiguous"] and r["reason"] == "multiple_amounts" and r["amounts"] == [500.0, 600.0], r
    assert audio_review.review_transcript("Cotizar 500 PEN a BRL")["ambiguous"] is False
    assert audio_review.review_transcript("quiero mandar 500")["reason"] == "amount_without_currency"
    assert audio_review.review_transcript("son 300 mil reales")["reason"] == "thousands_word"
    assert audio_review.review_transcript("hola [inaudible] gracias")["reason"] == "unreadable_parts"
    sent: list = []

    async def _send(text):
        sent.append(text)
        return {"ok": True}

    media = {"provider": "telegram", "kind": "voice", "ref": "VOICE-AMB", "mime": "audio/ogg"}
    out = _run(audio_flow.process_transcript(channel="telegram", user_ref="tg:9001", text="quiero enviar 500 o 600 soles",
                                             media=media, send=_send))
    assert out.get("ambiguous") is True and sent and "Escuché" in sent[-1] and "500" in sent[-1], (out, sent)
    cid = out["conversation_id"]
    msgs = db.get_messages(cid)
    assert msgs[-2]["role"] == "user" and msgs[-2]["media"]["ref"] == "VOICE-AMB", msgs[-2]
    assert db.get_lead_data(cid).get("audio_pending_confirmation") == "multiple_amounts"
    assert db.conversation_status(cid) != "handoff", "un audio ambiguo NO deriva: pide confirmacion"
    # Audio legible -> sigue con la IA (cotizador) y limpia la confirmacion pendiente.
    out2 = _run(audio_flow.process_transcript(channel="telegram", user_ref="tg:9001", text="Cotizar 500 PEN a BRL",
                                              media=media, send=_send, conversation_id=cid))
    assert out2.get("flow") == "quote" and "710" in sent[-1].replace(",", ""), (out2, sent[-1])
    assert not db.get_lead_data(cid).get("audio_pending_confirmation")
    # Audio imposible de transcribir: evidencia + asesor (no se pierde).
    out3 = _run(audio_flow.unreadable(channel="telegram", user_ref="tg:9002", media=media, send=_send, error="whisper caido"))
    c3 = db.get_conversation(out3["conversation_id"])
    assert c3["status"] == "handoff" and c3["lead_data"]["handoff"]["reason"] == "audio_unreadable", c3
    assert db.get_messages(c3["id"])[0]["media"]["ref"] == "VOICE-AMB"
    # Comprobante recibido != pago confirmado (texto del ack del webhook WhatsApp).
    from api import routes as _routes
    assert "verificado" in _routes._PROOF_ACK and "confirma" in _routes._PROOF_ACK


def case_public_documents_and_deletion():
    client = _client()
    assert client.get("/api/public/documents/privacidad").status_code == 404, "sin publicar -> 404"
    assert client.get("/api/public/documents/otro").status_code == 404
    assert client.put("/api/admin/documents/privacidad", headers=AGENT,
                      json={"lang": "es", "title": "x", "body_md": "y"}).status_code == 403
    r = client.put("/api/admin/documents/privacidad", headers=OWNER,
                   json={"lang": "es", "title": "Política de privacidad", "body_md": "# Hola\n<script>alert(1)</script>Texto **ok**"})
    assert r.status_code == 200 and r.json()["document"]["status"] == "draft", r.text
    v = r.json()["document"]["version"]
    assert "<script>" not in r.json()["document"]["body_md"], "sin HTML ejecutable"
    assert client.get("/api/public/documents/privacidad").status_code == 404, "el borrador NO es publico"
    r = client.post("/api/admin/documents/privacidad/publish", headers=OWNER, json={"lang": "es", "version": v})
    assert r.status_code == 200 and r.json()["document"]["status"] == "published", r.text
    pub = client.get("/api/public/documents/privacidad").json()
    assert pub["version"] == v and "Texto **ok**" in pub["body_md"] and "body_md" in pub
    assert client.get("/api/public/documents/privacidad?lang=pt").status_code == 404
    ov = client.get("/api/admin/documents", headers=OWNER).json()["documents"]
    row = [d for d in ov if d["slug"] == "privacidad" and d["lang"] == "es"][0]
    assert row["published_version"] == v and row["draft_version"] is None, row
    hist = client.get("/api/admin/documents/privacidad?lang=es", headers=OWNER).json()["history"]
    assert hist and hist[0]["status"] == "published"
    # Solicitud publica de eliminacion: se registra, no borra nada.
    n_conv = len(db.list_conversations())
    r = client.post("/api/public/data-deletion-request", json={"contact": "+51 999 888 777", "channel": "whatsapp", "detail": "borren mis datos"})
    assert r.status_code == 200 and r.json()["status"] == "received", r.text
    assert len(db.list_conversations()) == n_conv
    assert client.post("/api/public/data-deletion-request", json={"contact": "x"}).status_code == 422
    reqs = client.get("/api/admin/deletion-requests", headers=OWNER).json()["requests"]
    assert reqs and reqs[0]["contact"] == "+51 999 888 777"
    assert client.get("/api/admin/deletion-requests", headers=AGENT).status_code == 403
    r = client.post(f"/api/admin/deletion-requests/{reqs[0]['id']}/status", headers=OWNER,
                    json={"status": "verifying", "note": "pedir documento"})
    assert r.status_code == 200 and r.json()["request"]["status"] == "verifying"


def case_tool_contracts_idempotency():
    import time as _t
    assert tool_contracts.validate("quote.compute", {"origin": "PEN", "destination": "BRL", "amount_send": 500}) is None
    assert "faltan" in tool_contracts.validate("quote.compute", {"origin": "PEN"})
    assert "no permitidas" in tool_contracts.validate("quote.compute", {"origin": "PEN", "destination": "BRL", "x": 1})
    assert "tipo" in tool_contracts.validate("quote.compute", {"origin": "PEN", "destination": "BRL", "amount_send": True}) or "debe ser" in tool_contracts.validate("quote.compute", {"origin": "PEN", "destination": "BRL", "amount_send": True})
    assert tool_contracts.run("status.lookup", {}, lambda: 1)["error_code"] == "validation"
    assert tool_contracts.run("quote.compute", {"origin": "PEN"}, lambda **k: 1)["error_code"] == "validation"
    slow = tool_contracts.run("knowledge.search", {"query": "x"}, lambda query, lang="es": _t.sleep(2.6) or None)
    assert slow["error_code"] == "timeout", slow
    boom = tool_contracts.run("knowledge.search", {"query": "x"}, lambda query, lang="es": 1 / 0)
    assert boom["error_code"] == "internal", boom
    calls = []

    def _upsert(lead):
        calls.append(lead)
        return {"ok": True, "data": {"id": 77, "created": True}}

    key = idempotency.make_key("client.upsert", "+51", "999000111", "dni", "12345678")
    r1 = tool_contracts.run("client.upsert", {"lead": {"telefono": "999000111"}}, _upsert, idempotency_key=key)
    r2 = tool_contracts.run("client.upsert", {"lead": {"telefono": "999000111"}}, _upsert, idempotency_key=key)
    assert r1["ok"] and r2["ok"] and r2.get("replayed") is True and len(calls) == 1, (r1, r2, calls)
    bad = tool_contracts.run("client.upsert", {"lead": {}}, lambda lead: {"ok": False, "error": "falta telefono"},
                             idempotency_key=idempotency.make_key("client.upsert", "nada"))
    assert bad["error_code"] == "upstream" and idempotency.recall(idempotency.make_key("client.upsert", "nada")) is None
    assert idempotency.seen_event("test", "e1") is False and idempotency.seen_event("test", "e1") is True
    assert idempotency.seen_event("test", None) is False
    client = _client()
    r = client.get("/api/tools", headers=OWNER)
    assert r.status_code == 200 and any(t["name"] == "client.upsert" and t["write"] for t in r.json()["tools"]), r.text
    assert r.json()["features"]["knowledge"] is True


def case_flow_metrics_and_summary():
    _run(engine.handle_message("flow-1", "Cotizar 200 PEN a BRL"))
    snap = _client().get("/api/ops/metrics", headers=OWNER).json()
    assert snap["flows"].get("quote", {}).get("count", 0) >= 1, snap["flows"]
    assert snap["flows"]["quote"]["p95_ms"] is not None
    # Resumen de derivacion completo para el asesor.
    out = _run(engine.handle_message("flow-2", "quiero hablar con un asesor"))
    h = db.get_lead_data(out["conversation_id"])["handoff"]
    assert h["reason_label"] and "Motivo" in h["text"] and "Últimos mensajes" in h["text"], h
    assert handoff_summary.REASON_LABELS["media"]


def case_agent_profiles():
    from core import agent_profiles, agent_graph
    client = _client()
    body = {"profile": {"name": "Luna", "tone": "warm", "emoji": "none", "channels": ["telegram"]}, "expected_version": 0}
    path = "/api/admin/agent-profiles/luna"
    assert client.put(path, json=body, headers=AGENT).status_code == 403
    assert client.put(path, json=body, headers=OWNER).status_code == 200
    assert client.put(path, json=body, headers=OWNER).status_code == 409
    invalid = {**body, "profile": {**body["profile"], "discount": 25}}
    assert client.put(path, json=invalid, headers=OWNER).status_code == 422
    cid = db.get_or_create_conversation("profile-telegram", "telegram")
    state = {"cid": cid, "channel": "telegram", "analysis": {"language": "pt"}}
    assert "Luna" not in agent_graph.build_messages(state)["system_prompt"]  # draft cannot leak
    assert client.post(path + "/publish", json={"version": 1}, headers=OWNER).status_code == 200
    prompt = agent_graph.build_messages(state)["system_prompt"]
    assert "Luna" in prompt and "No uses emojis" in prompt and "portugues" in prompt
    other = db.get_or_create_conversation("profile-whatsapp", "whatsapp")
    assert agent_profiles.resolve(other, "whatsapp") is None
    changed = {"profile": {**body["profile"], "name": "Sol"}, "expected_version": 1}
    assert client.put(path, json=changed, headers=OWNER).status_code == 200
    assert client.post(path + "/publish", json={"version": 2}, headers=OWNER).status_code == 200
    assert "Luna" in agent_graph.build_messages(state)["system_prompt"]  # ongoing conversation remains coherent
    new = db.get_or_create_conversation("profile-new", "telegram")
    assert agent_profiles.resolve(new, "telegram")["profile"]["name"] == "Sol"
    assert client.post(path + "/disable", headers=OWNER).status_code == 200
    assert agent_profiles.resolve(db.get_or_create_conversation("profile-disabled", "telegram"), "telegram") is None
    assert len(client.get(path + "/history", headers=OWNER).json()["versions"]) == 2
    restricted = {"profile": {"name": "Soporte", "capabilities": ["info"], "channels": ["webchat"],
                               "knowledge_ids": ["documentos"], "priority": 100}, "expected_version": 0}
    restricted_path = "/api/admin/agent-profiles/support"
    assert client.put(restricted_path, json=restricted, headers=OWNER).status_code == 200
    assert client.post(restricted_path + "/publish", json={"version": 1}, headers=OWNER).status_code == 200
    out = _run(engine.handle_message("restricted-profile", "Cotizar 500 PEN a BRL"))
    assert out["handoff"] is True and not db.get_lead_data(out["conversation_id"]).get("monto_recibir"), out
    from core import knowledge
    assert knowledge.search("documentos necesarios", "es", allowed_ids=["missing"]) is None
    hit = knowledge.search("documentos necesarios", "pt", allowed_ids=["documentos"])
    assert hit and hit["entry"]["id"] == "documentos"  # translation must not escape the allowed set
    client.post(restricted_path + "/disable", headers=OWNER)


def case_handoff_interrupts_onboarding():
    cid = db.get_or_create_conversation("onboarding-human", "webchat")
    db.merge_lead_data(cid, {"commercial_stage": "collecting_identity", "onboarding_field": "document_number"})
    out = _run(engine.handle_message("onboarding-human", "quiero hablar con un asesor", conversation_id=cid))
    assert out["handoff"] and db.conversation_status(cid) == "handoff", out
    assert not db.get_lead_data(cid).get("numero_documento")


def case_real_timeout_and_concurrent_write():
    import threading
    import time
    from dataclasses import replace
    from core import tool_contracts, idempotency
    original = tool_contracts.REGISTRY["client.upsert"]
    tool_contracts.REGISTRY["client.upsert"] = replace(original, timeout=0.08)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    key = idempotency.make_key("concurrent-write", "verified-client")

    def slow(lead):
        calls.append(lead)
        entered.set()
        release.wait(2)
        finished.set()
        return {"ok": True, "data": {"id": "same-client"}}

    try:
        start = time.monotonic()
        result = tool_contracts.run("client.upsert", {"lead": {}}, slow, idempotency_key=key)
        assert entered.is_set() and result["error_code"] == "timeout", result
        assert time.monotonic() - start < 0.6  # must return before the worker is released
        retry = tool_contracts.run("client.upsert", {"lead": {}}, slow, idempotency_key=key)
        assert retry["error_code"] == "in_progress" and len(calls) == 1, retry
        release.set()
        assert finished.wait(1)
        deadline = time.monotonic() + 1
        while idempotency.recall(key) is None and time.monotonic() < deadline:
            time.sleep(0.01)
        replay = tool_contracts.run("client.upsert", {"lead": {}}, slow, idempotency_key=key)
        assert replay["ok"] and replay["replayed"] and len(calls) == 1, replay
        # A second simultaneous caller sees the atomic reservation before the first returns.
        key2 = idempotency.make_key("parallel-write", "verified-client")
        results = []
        gate = threading.Barrier(3)
        def caller():
            gate.wait()
            results.append(tool_contracts.run("client.upsert", {"lead": {}},
                           lambda lead: time.sleep(0.02) or {"ok": True}, idempotency_key=key2))
        threads = [threading.Thread(target=caller) for _ in range(2)]
        for thread in threads:
            thread.start()
        gate.wait()
        for thread in threads:
            thread.join(2)
        assert len(results) == 2 and any(r.get("ok") for r in results), results
        assert any(r.get("replayed") or r.get("error_code") == "in_progress" for r in results), results
    finally:
        release.set()
        tool_contracts.REGISTRY["client.upsert"] = original


def case_coupon_limits_and_selection():
    import copy
    coupon = {"code": "VALID", "discount_percentage": 25, "is_active": True,
              "lifecycle_status": "ACTIVE", "max_uses": 10, "used_count": 1,
              "origin_currency": "PEN", "destination_currency": "BRL"}
    original = brasper_api._fetch
    rows = [coupon]
    urls = []
    brasper_api._fetch = lambda url: urls.append(url) or rows
    try:
        assert brasper_api.best_coupon({}, "PEN", "BRL")["code"] == "VALID"
        assert urls[-1].endswith("/transactions/coupons/automatic")
        invalids = [
            {"lifecycle_status": "DRAFT"}, {"used_count": 10}, {"is_active": False},
            {"per_user_limit": 1}, {"discount_percentage": -1}, {"discount_percentage": 101},
            {"discount_percentage": float("nan")}, {"discount_percentage": float("inf")},
            {"start_date": "invalid"}, {"start_date": "2030-01-01T00:00:00+00:00"},
            {"end_date": "2020-01-01T00:00:00+00:00"}, {"start_date": "2020-01-01"},
            {"exchange_rate_scopes": ["BRL_USD"]}, {"exchange_rate_scopes": [{}]},
        ]
        for changes in invalids:
            rows = [{**copy.deepcopy(coupon), **changes}]
            assert brasper_api.best_coupon({}, "PEN", "BRL") is None, changes
        rows = [{**coupon, "exchange_rate_scopes": ["ALL"]}]
        assert brasper_api.best_coupon({}, "BRL", "USD")["code"] == "VALID"
        ranges = [{"min": 0, "max": 10000, "rate": 0.03}]
        for percentage, savings in [(0, 0), (25, 3.75), (100, 15)]:
            c = {**coupon, "discount_percentage": percentage}
            q = quotes._quote_from_gross_send(500, 1.5, ranges, c)
            assert q["coupon_savings_amount"] == savings and q["commission"] == 15 - savings, q
            assert q["amount_receive"] == round((500 - 15 + savings) * 1.5, 2), q
            inverse = quotes._quote_inverse(q["amount_receive"], 1.5, ranges, c)
            assert abs(inverse["amount_send"] - 500) <= 0.01, inverse
        for percentage in [-1, 101, float("nan"), float("inf")]:
            q = quotes._quote_from_gross_send(500, 1.5, ranges, {**coupon, "discount_percentage": percentage})
            assert q["coupon_code"] is None and q["coupon_savings_amount"] == 0, q
    finally:
        brasper_api._fetch = original


def case_expired_financial_cache_not_reused():
    import time
    import httpx
    from unittest.mock import patch
    url = "https://unit-test.invalid/coin/tax-rate"
    brasper_api._cache[url] = (time.time() - brasper_api._TTL - 1, [{"tax": 100}])
    try:
        with patch.object(httpx.Client, "get", side_effect=httpx.ConnectError("test offline")):
            assert brasper_api._fetch(url) is None, "No reutilizar una tasa/cupon vencido si falla la API"
    finally:
        brasper_api._cache.pop(url, None)


def case_client_identity_and_history():
    from uuid import uuid4
    for ref in ["wa:bsuid-51999111222", "wa:opaque51999111222", "wa:999111222", "wa:551", "wa:521999111222"]:
        assert lead_onboarding.phone_from_channel("whatsapp", ref) is None, ref
    assert lead_onboarding.phone_from_channel("telegram", "wa:51999111222") is None
    assert lead_onboarding.phone_from_channel("whatsapp", "wa:51999111222") == ("+51", "999111222")
    assert lead_onboarding._parse_phone("+55 1") is None
    recorded, _ = lead_onboarding._consume("document_number", "12345678")
    assert recorded["document_recorded"] is True and recorded["document_verified"] is False
    saved_find, saved_history = brasper_api.find_client, brasper_api.client_history
    history_calls = []
    client_id = str(uuid4())
    try:
        brasper_api.find_client = lambda *a, **kw: {"ok": True, "data": {
            "id": client_id, "names": "Otra", "code_phone": "+51", "phone": "999000000"}}
        assert not lead_onboarding.recognize_by_phone("whatsapp", "wa:51999111222")["found"]
        # Same-name match must never be requested to bind a web/Telegram identity.
        def forbidden_lookup(*a, **kw):
            assert not kw.get("full_name"), "no vincular identidad por nombre"
            return {"ok": True, "data": None}
        brasper_api.find_client = forbidden_lookup
        cid = db.get_or_create_conversation("identity-name-only", "webchat")
        db.merge_lead_data(cid, {"onboarding_field": "full_name", "commercial_stage": "awaiting_name"})
        answer = lead_onboarding.process(cid, "Ana Perez", "webchat", "identity-name-only", new_lead=False)
        assert not answer.get("banner") and not db.get_lead_data(cid).get("brasper_user_id")
        wa_cid = db.get_or_create_conversation("wa:51999111888", "whatsapp")
        db.merge_lead_data(wa_cid, {"brasper_user_id": client_id, "identity_source": "channel_phone_match",
                                  "codigo_telefono": "+51", "telefono": "999111888"})
        payload = {"completed_transfers": 0, "pending_transfers": 1, "first_transfer_eligible": False}
        brasper_api.client_history = lambda *a, **kw: history_calls.append(kw) or {"ok": True, "data": payload}
        result = lead_onboarding.refresh_history(wa_cid, "whatsapp", "wa:51999111888")
        assert result["history_status"] == "verified" and result["first_transfer_eligible"] is False
        payload = {"completed_transfers": 0, "pending_transfers": 0, "first_transfer_eligible": True}
        assert lead_onboarding.refresh_history(wa_cid, "whatsapp", "wa:51999111888")["first_transfer_eligible"] is True
        payload = {"completed_transfers": 0, "pending_transfers": 3, "first_transfer_eligible": True}
        assert lead_onboarding.refresh_history(wa_cid, "whatsapp", "wa:51999111888") is None
        assert db.get_lead_data(wa_cid)["first_transfer_eligible"] is None, "no conservar elegibilidad antigua"
        before = len(history_calls)
        assert lead_onboarding.refresh_history(wa_cid, "telegram", "tg:111") is None
        assert len(history_calls) == before, "telefono auto declarado no permite consultar historial"
    finally:
        brasper_api.find_client, brasper_api.client_history = saved_find, saved_history


def case_approved_media_library():
    import io, json
    from PIL import Image
    from core import media_library
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    content = image.getvalue()
    client = _client()
    metadata = {"name": "Primer envio ES", "purpose": "promotion", "language": "es"}
    path = "/api/admin/media-library/first-send-es"
    assert client.put(path, headers=AGENT, data={"metadata": json.dumps(metadata)}, files={"file": ("test.png", content, "image/png")}).status_code == 403
    saved = client.put(path, headers=OWNER, data={"metadata": json.dumps(metadata)}, files={"file": ("test.png", content, "image/png")})
    assert saved.status_code == 200 and saved.json()["version"] == 1, saved.text
    assert media_library.approved("first-send-es", "es") is None
    assert client.get(path + "/1/preview", headers=OWNER).content == content
    assert client.get(path + "/1/preview").status_code == 401
    assert client.post(path + "/publish", headers=OWNER, json={"version": 1}).status_code == 200
    assert media_library.approved("first-send-es", "es") is not None
    assert media_library.approved("first-send-es", "pt") is None
    assert media_library.approved("first-send-es", "es", "official_accounts") is None
    invalid = client.put(path, headers=OWNER, data={"metadata": json.dumps(metadata), "expected_version": 1}, files={"file": ("script.svg", b"<svg><script>alert(1)</script></svg>", "image/png")})
    assert invalid.status_code == 422
    stale = client.put(path, headers=OWNER, data={"metadata": json.dumps(metadata)}, files={"file": ("test.png", content, "image/png")})
    assert stale.status_code == 409
    quote = {"coupon_id": "campaign-test", "campaign_version": 1, "campaign_rules": {"messages": {
        "es": {"text": "25% sobre comision", "media_id": "first-send-es"}}}}
    lead = {"brasper_user_id": "same-client"}
    banner = media_library.campaign_banner(quote, lead, "es")
    cid = db.get_or_create_conversation("wa:51999000001", "whatsapp")
    saved_sender = whatsapp.send_image_upload
    calls = []
    async def send(*args, **kwargs):
        calls.append(kwargs)
        return {"sent": True}
    whatsapp.send_image_upload = send
    try:
        _run(media_library.deliver(cid, "whatsapp", "51999000001", banner, connection={"id": "second-number"}))
        _run(media_library.deliver(cid, "whatsapp", "51999000001", banner, connection={"id": "second-number"}))
        assert len(calls) == 1 and calls[0]["connection"]["id"] == "second-number"
        assert media_library.campaign_banner(quote, lead, "es") is None
        quote["campaign_version"] = 2
        banner2 = media_library.campaign_banner(quote, lead, "es")
        async def fail(*args, **kwargs):
            raise TimeoutError("simulated")
        whatsapp.send_image_upload = fail
        _run(media_library.deliver(cid, "whatsapp", "51999000001", banner2))
        assert banner2["text"] == "25% sobre comision", "el texto sigue disponible aunque falle imagen"
        assert media_library.campaign_banner(quote, lead, "es") is None, "no reenviar automaticamente tras timeout incierto"
    finally:
        whatsapp.send_image_upload = saved_sender
    assert client.post(path + "/disable", headers=OWNER).status_code == 200
    assert media_library.approved("first-send-es", "es") is None


def case_campaign_quote_and_admin_permissions():
    from uuid import uuid4
    saved = brasper_api.enabled, brasper_api.personalized_quote, brasper_api._integration_request
    brasper_api.enabled = lambda tenant: True
    q = quotes._quote_from_gross_send(500, 1.5, [{"min": 0, "max": 1000, "rate": 0.03}], {"code": "FIRST25", "discount_percentage": 25})
    q.update({"origin_currency": "PEN", "destination_currency": "BRL", "reserved": False})
    brasper_api.personalized_quote = lambda *args, **kwargs: {"ok": True, "data": q}
    try:
        identity = {"brasper_user_id": str(uuid4()), "codigo_telefono": "+51", "telefono": "999111222"}
        assert quotes.compute("PEN", "BRL", 500, identity=identity)["coupon_savings_amount"] == 3.75
        q["amount_receive"] += 100
        assert quotes.compute("PEN", "BRL", 500, identity=identity).get("error"), "no aceptar cifras incoherentes"
        brasper_api.personalized_quote = lambda *args, **kwargs: {"ok": False}
        assert quotes.compute("PEN", "BRL", 500, identity=identity).get("error"), "sin fallback a promo local"
        calls = []
        def upstream(*args, **kwargs):
            calls.append((args, kwargs))
            return {"ok": True, "data": {"id": str(uuid4()), "version": 1}}
        brasper_api._integration_request = upstream
        response = _client().post("/api/admin/campaigns", headers=AGENT, json={"draft": {}})
        assert response.status_code == 403 and not calls
        response = _client().post("/api/admin/campaigns", headers=OWNER, json={"draft": {}})
        assert response.status_code == 200 and calls[0][1]["admin"] is True
        assert calls[0][1]["json"]["actor"] == "owner@agencia.com"
    finally:
        brasper_api.enabled, brasper_api.personalized_quote, brasper_api._integration_request = saved


def case_bilingual_onboarding_and_private_status():
    from unittest.mock import patch
    from uuid import uuid4
    from core import policies, operation_status
    assert policies.detect_language("12345678", fallback="pt") == "pt"
    assert policies.detect_language("Ana Silva", fallback="pt") == "pt"
    assert policies.detect_language("responde en español", fallback="pt") == "es"
    passport, error = lead_onboarding._consume("document_number", "AB123456", "pt", "passport")
    assert not error and passport["numero_documento"] == "AB123456"
    assert lead_onboarding._consume("document_number", "abc123456", "pt", "dni")[1]
    with patch.object(brasper_api, "find_client", return_value={"ok": True, "data": None}), \
         patch.object(brasper_api, "upsert_client", return_value={"ok": True, "data": {"id": str(uuid4()), "created": True}}), \
         patch.object(brasper_api, "deposit_accounts", return_value={"ok": True, "data": [{"bank": "Banco", "company": "Brasper", "account": "test-only"}]}):
        ref = "wa:5511998877665"
        out = _run(engine.handle_message(ref, "Olá", channel="whatsapp"))
        cid = out["conversation_id"]
        assert "nome completo" in out["response"], out
        for message in ["Ana Silva", "quero enviar 500 PEN para BRL", "continuar", "passaporte", "AB123456"]:
            out = _run(engine.handle_message(ref, message, channel="whatsapp", conversation_id=cid))
        assert "contas oficiais" in out["response"] and "verificará o pagamento" in out["response"], out
        assert db.get_lead_data(cid)["idioma"] == "pt"
        # Typed identity must not allow private reads on another channel.
        with patch.object(operation_status.features, "enabled", return_value=True), \
             patch.object(brasper_api, "operation_status", return_value={"ok": True, "data": {"data": [{"code": "PxB-123", "status": "verification"}]}}) as remote:
            assert operation_status.lookup(cid, "telegram", ref, "estado", "pt") is None
            remote.assert_not_called()
            reply = operation_status.lookup(cid, "whatsapp", ref, "estado PxB-123", "pt")
            assert "em verificação" in reply and "concluída" not in reply
            remote.return_value = {"ok": True, "data": {"data": [{"code": "PxB-123", "status": "invented"}]}}
            assert operation_status.lookup(cid, "whatsapp", ref, "estado", "es") is None
            remote.return_value = {"ok": False}
            assert operation_status.lookup(cid, "whatsapp", ref, "estado", "es") is None


def case_human_revision_and_document_conflicts():
    from unittest.mock import patch
    from concurrent.futures import ThreadPoolExecutor
    from core import public_docs
    cid = db.get_or_create_conversation("human-race-test", "webchat")
    revision = db.get_conversation(cid)["human_revision"]
    old = {"conversation_id": cid, "human_revision": revision}
    assert engine.delivery_allowed(old)
    db.invalidate_ai(cid)
    db.set_conversation_status(cid, "active")
    assert not engine.delivery_allowed(old), "resuming cannot revive a stale response"
    async def interrupted(tenant, messages):
        db.invalidate_ai(cid)
        return {"content": "This response must not be sent", "provider": "stub", "model": "stub", "tokens_in": 1, "tokens_out": 1, "cost_usd": 0}
    with patch.object(llm, "chat", side_effect=interrupted):
        out = _run(engine.handle_message("human-race-test", "necesito orientación general", conversation_id=cid))
    assert out["paused"] and not out["response"] and not engine.delivery_allowed(out)
    latest = public_docs.get_latest("terminos", "pt")
    version = latest["version"] if latest else 0
    def save(n):
        try:
            return public_docs.save_draft("terminos", "pt", f"Test {n}", "Only synthetic content", "test", version)
        except public_docs.Conflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [1, 2]))
    assert sum(r is not None for r in results) == 1
    assert public_docs.get_latest("terminos", "pt")["version"] == version + 1


def main() -> int:
    from engagement_checks import run as engagement_checks
    from channel_checks import run as channel_checks
    from media_checks import run as media_checks
    from identity_checks import identity_checks
    from contact_checks import contact_checks
    from outbound_checks import outbound_checks
    from access_checks import access_checks
    from service_auth_checks import service_auth_checks
    from lock_checks import lock_checks
    check("1. config single-tenant Brasper (secretos por env, prompt con reglas)", case_config_single_tenant)
    check("2. persistencia + orden cronologico", case_persistence_order)
    check("3. conversacion se reutiliza por usuario/canal; closed abre nueva", case_conversation_reuse)
    check("4. medicion de consumo (summary/daily/events)", case_usage_measurement)
    check("5. resolve_by_phone_number_id", case_resolve_pnid)
    check("6. whatsapp.parse_incoming", case_parse_incoming)
    check("7. API protegida con RBAC (owner/agent/billing)", case_api_auth_rbac)
    check("8. webhook WhatsApp valida firma", case_webhook_signature)
    check("9. webhook Telegram exige secret en produccion", case_telegram_secret_in_production)
    check("10. Admin API single-tenant: patch, pausa, secretos por env", case_admin_tenant_api)
    check("11. LangGraph ruta LLM con stub", case_langgraph_llm_path)
    check("12. Fallo del LLM -> respuesta cortes + handoff", case_llm_failure_degrades_to_handoff)
    check("13. Redis runtime sin REDIS_URL", case_redis_runtime_without_redis)
    check("14. ToolRouter ejecuta conector y el LLM redacta", case_tool_router_path)
    check("15. CalendarAdapter puro; Brasper no agenda citas", case_calendar_adapter)
    check("16. Observabilidad, metricas protegidas y /health", case_observability_metrics)
    check("17. Backup SQLite local", case_sqlite_backup_create)
    check("18. Jobs retry/dead-letter sin Redis", case_jobs_retry_without_redis)
    check("19. Export de conversaciones + retencion", case_export_and_retention)
    check("20. Produccion exige Postgres + Redis (fail-fast)", case_production_requires_postgres_redis)
    check("21. Cotizador: matematica directa/inversa + texto", case_quote_math)
    check("22. Cotizador: extraccion (monedas, paises, recibir, seguimiento)", case_quote_request_extraction)
    check("23. Cotizador en el grafo (sin LLM) + aclaraciones deterministas", case_quote_graph_path)
    check("24. Handoff por keyword + asignacion al asesor con menos carga", case_handoff_and_advisor_assignment)
    check("25. Takeover humano: bot en pausa, asesor responde, devolver al bot", case_human_takeover)
    check("26. Asesor: ve lo suyo + libres, guard anti-colision, imagenes", case_agent_scoping_and_images)
    check("27. Subida de archivo por el asesor (multipart + guards)", case_upload_file)
    check("28. Media entrante: se guarda, deriva y da acuse", case_incoming_media)
    check("29. Telegram solo responde en privado (allow_groups opcional)", case_telegram_private_only)
    check("30. Jobs degradan si Redis esta inalcanzable (no 500)", case_jobs_degrade_when_redis_unreachable)
    check("31. Guard: el bot nunca deriva a WhatsApp/redes", case_no_external_channel_guard)
    check("32. Telegram: voz entrante se transcribe y el bot responde", case_telegram_audio_transcription)
    check("33. audio_adapter: seleccion de backend", case_audio_adapter_provider_selection)
    check("34. API Brasper exclusiva: TC real sin fallback local", case_brasper_api_live_quote)
    check("35. Contacto nuevo: nombre no acredita identidad ni primer envio", case_new_lead_and_banner)
    check("36. Cotizacion persiste lead estructurado + fila quotes (fee real)", case_lead_data_and_quote_persisted)
    check("37. Reglas: vigencia TC 20min + monto alto deriva a asesor", case_quote_business_rules)
    check("38. Checkout: cuentas oficiales sin crear transaccion", case_checkout_deposit_accounts)
    check("39. Onboarding progresivo: cotiza primero, documento al continuar", case_client_onboarding_without_transaction)
    check("40. Cliente recurrente: reconocimiento por telefono", case_returning_client_by_phone)
    check("41. Cuentas no disponibles: handoff real sin error tecnico", case_deposit_failure_creates_handoff)
    check("42. Integracion Brasper: solo endpoints IA privados + borrado guardado", case_private_brasper_ai_contracts)
    check("43. Borrado de conversacion con guard de identidad", case_conversation_delete_guard)
    check("44. E2E HTTP: prompt configurado desde Admin API llega al LLM", case_bot_config_e2e)
    check("45. Webchat compat (/consulta-webchat) publico y con seguimiento", case_webchat_compat_endpoint)
    check("46. Panel v2: filtros/since/after, sender, notas, quick replies, cache media, vitals", case_panel_inbox_v2)
    check("47. Conocimiento: FAQ aprobada con fuente; sin respuesta -> incertidumbre explicita", case_knowledge_faq_with_source)
    check("48. Estado de envio sin API -> asesor con resumen (nunca inventa)", case_status_intent_handoff_with_summary)
    check("49. Anti-bucle: limite de repeticiones del bot", case_anti_loop_limits_repetition)
    check("50. Webhook WA: dedup, identidad, estados/historial, ecos Coex, conexion de origen", case_webhook_dedup_identity_coex)
    check("51. Presencia con heartbeat + cola + claim atomico (409)", case_presence_and_atomic_claim)
    check("52. Etiquetas: alta/baja/filtro", case_tags_filter)
    check("53. Audios: cifras ambiguas piden confirmacion; evidencia; no transcribible -> asesor", case_audio_review_and_flow)
    check("54. Documentos publicos: borrador privado, publicacion versionada, solicitud de borrado", case_public_documents_and_deletion)
    check("55. Contratos de herramientas: validacion, timeout, no disponible, idempotencia", case_tool_contracts_idempotency)
    check("56. Metricas por flujo + resumen de derivacion", case_flow_metrics_and_summary)
    check("57. Perfiles IA: permisos, borradores, versionado, canales y continuidad", case_agent_profiles)
    check("58. Solicitar asesor interrumpe la recopilacion de identidad", case_handoff_interrupts_onboarding)
    check("59. Timeout real, escritura concurrente unica y resultado tardio recuperable", case_real_timeout_and_concurrent_write)
    check("60. Cupones: 0-100 sobre comision, vigencia, limites y par oficial", case_coupon_limits_and_selection)
    check("61. API caida: cache financiera vencida no se reutiliza", case_expired_financial_cache_not_reused)
    check("62. Identidad: sin vinculacion por nombre/BSUID; historial oficial y reserva pendiente", case_client_identity_and_history)
    check("63. Biblioteca aprobada: versiones, idioma, RBAC, envio unico y fallo de imagen", case_approved_media_library)
    check("64. Campanas: cotizacion oficial sin fallback y administracion separada", case_campaign_quote_and_admin_permissions)
    check("65. Onboarding PT persistente, documentos y estado privado por identidad", case_bilingual_onboarding_and_private_status)
    check("66. Intervencion humana invalida respuestas; conflictos de documentos", case_human_revision_and_document_conflicts)

    print("=" * 60)
    print("GATE PRODUCCION — verificacion (sin pytest, sin LLM real)")
    print("=" * 60)
    check("67. Seguimiento: consentimiento, horario, takeover, encuesta y ventana", lambda: engagement_checks(_client(), OWNER, AGENT))
    check("68. Canales: conexiones aisladas, BSUID, eco propio y humano durante upload", lambda: channel_checks(_client(), _wa_payload))
    check("69. Medios privados: streaming limitado, tipo de audio y host autorizado", media_checks)
    check("70. Vinculacion Telegram/webchat: token de un uso, grant cifrado, dueño y timeout", identity_checks)
    check("71. Contactos/alias por conexion, BSUID sin telefono, conflictos, creacion concurrente y Redis caido", contact_checks)
    check("72. Salidas enviado/cancelado/incierto/fallido, estados fuera de orden, ecos diferidos y replay Coex", outbound_checks)
    check("73. Alcance por canal/numero/sector, comprobantes privados y asignacion con permisos", lambda: access_checks(_client(), OWNER))
    check("74. Cuenta de servicio: JWT + secreto, re-login unico ante 401 del middleware, sin confundir 401 de ruta", service_auth_checks)
    check("75. Lock comun en base: sin base no se procesa, Redis mixto excluye y lease vencido no entrega", lock_checks)
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
