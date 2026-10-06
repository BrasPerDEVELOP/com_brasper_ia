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
    out = _run(engine.handle_message("user-langgraph", "hola, que documentos necesito?"))
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
    token = redis_runtime.acquire_lock("test:lock")
    assert token == "local-no-redis", token
    redis_runtime.release_lock("test:lock", token)
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

    # Senal debil sin datos ("envio" como sustantivo) NO cae al cotizador.
    out5 = _run(engine.handle_message("user-quote-doc", "que documentos necesito para el envio?"))
    assert out5["response"] == "[respuesta simulada]", out5["response"]


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

    async def _fake_image(to, link, caption=""):
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
# Caso 35: lead nuevo — deteccion + banner de primer envio tras verificar cliente
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
        assert out2.get("banner") and "primer envío" in (out2["banner"]["text"] or "").lower(), out2
        # El webchat antepone el banner a la respuesta (contrato del panel/web).
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


def main() -> int:
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
    check("35. Lead nuevo: deteccion + banner de primer envio", case_new_lead_and_banner)
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
