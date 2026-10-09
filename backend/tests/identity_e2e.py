"""E2E de la vinculación de identidad del chat (C2) contra la API Brasper REAL en local.

NO forma parte de run_checks (necesita la API levantada). Lo orquesta
``com_brasper_api/scripts/e2e_identity_link_driver.py``: PGlite migrado + arnés
``scripts/e2e_identity_link_pglite.py`` en http://127.0.0.1:8010.

Recorre el camino real del bot: ``engine.handle_message("tg:<id>", ..., channel="telegram")``
→ LangGraph → ``identity_link`` / ``operation_status`` → ``brasper_api`` (httpx) → API.
El portal se simula con la sesión sintética del arnés (``Bearer e2e-portal.<uuid>``).

Aislamiento (igual que run_checks): SQLite y tenants.json temporales, Redis apagado,
variables del .env local neutralizadas ANTES de importar ``core``; el LLM se sustituye
por un stub que falla (ningún paso debe gastarlo) y un guardia de sockets rechaza
cualquier conexión que no sea a loopback (nunca apibras.finzeler.com ni otro host).

Variables: E2E_SHARED_SECRET (sintético, el mismo del arnés), E2E_API_BASE
(por defecto http://127.0.0.1:8010), E2E_SERVICE_USERNAME / E2E_SERVICE_PASSWORD
(cuenta de servicio sintética sembrada por el arnés; el bot entra por el
``POST /auth/login`` real) y E2E_AUTH_REQUIRED (``1`` si la API exige Bearer).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8010").rstrip("/")
SECRET = os.environ.get("E2E_SHARED_SECRET", "")
if len(SECRET) < 24:
    print("E2E_SHARED_SECRET sintético es obligatorio", file=sys.stderr)
    sys.exit(2)

# --- Guardia de red: solo loopback ------------------------------------------------
_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect
BLOCKED: list[str] = []


def _is_loopback(host) -> bool:
    host = str(host)
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guard_getaddrinfo(host, *args, **kwargs):
    if host is not None and not _is_loopback(host if not isinstance(host, bytes) else host.decode()):
        BLOCKED.append(str(host))
        raise OSError(f"[e2e] red externa bloqueada: {host}")
    return _orig_getaddrinfo(host, *args, **kwargs)


def _guard_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
        BLOCKED.append(str(address[0]))
        raise OSError(f"[e2e] red externa bloqueada: {address[0]}")
    return _orig_connect(self, address)


socket.getaddrinfo = _guard_getaddrinfo
socket.socket.connect = _guard_connect

# --- Entorno hermético (antes de importar core) -----------------------------------
from cryptography.fernet import Fernet  # noqa: E402

os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["APP_ENV"] = "development"
for _name in ("PANEL_ADMIN_EMAIL", "PANEL_ADMIN_TOKEN", "PANEL_ADMIN_NAME", "PANEL_LOGIN_CODE",
              "SEED_DEMO_USERS", "TENANTS_SOURCE", "TENANTS_BOOTSTRAP_OVERWRITE",
              "CHANNEL_DEBOUNCE_SECONDS", "WHATSAPP_REQUIRE_SIGNATURE", "WHATSAPP_APP_SECRET",
              "META_APP_SECRET", "BRASPER_IA_ADMIN_SECRET"):
    os.environ[_name] = ""
os.environ["BRASPER_IA_SHARED_SECRET"] = SECRET
# Cuenta de servicio: siempre se fija (aunque sea vacía) para que el .env local no la aporte.
os.environ["BRASPER_IA_SERVICE_USERNAME"] = os.environ.get("E2E_SERVICE_USERNAME", "")
os.environ["BRASPER_IA_SERVICE_PASSWORD"] = os.environ.get("E2E_SERVICE_PASSWORD", "")
AUTH_REQUIRED = os.environ.get("E2E_AUTH_REQUIRED", "0") == "1"
GRANT_KEY = Fernet.generate_key().decode()
os.environ["BRASPER_IA_GRANT_KEY"] = GRANT_KEY

_TMP = Path(tempfile.mkdtemp(prefix="identity_e2e_"))
from core import tenants as T  # noqa: E402

_cfg_path = _TMP / "tenants.json"
shutil.copy2(T.CONFIG_PATH, _cfg_path)
_cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
_tenant = _cfg["tenants"]["brasper"]
_api_cfg = _tenant.setdefault("quote", {}).setdefault("api", {})
_api_cfg.update({"enabled": True, "base_url": API, "integration_secret_env": "BRASPER_IA_SHARED_SECRET",
                 "identity_link_url": "https://portal.e2e.invalid/vincular-chat"})
_tenant.setdefault("features", {}).update({"identity_link": True, "operation_status": True})
_cfg_path.write_text(json.dumps(_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
T.CONFIG_PATH = _cfg_path
T.reload_config()

from core import db  # noqa: E402

db.DB_PATH = _TMP / "identity_e2e.db"
db.init_db()

import httpx  # noqa: E402

from core import brasper_api, engine, features, identity_link, llm, operation_status  # noqa: E402


async def _no_llm(*_a, **_k):
    raise AssertionError("ningún paso de la vinculación debe llegar al LLM")


llm.chat = _no_llm

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(cond), "" if cond else detail[:400]))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail[:400]}"), flush=True)
    return bool(cond)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def say(user_ref: str, text: str, cid: str | None = None) -> dict:
    out = run(engine.handle_message(user_ref, text, channel="telegram", conversation_id=cid))
    db.set_conversation_status(out["conversation_id"], "active")  # siguiente turno vuelve al bot
    return out


def control(method: str, path: str, **kw):
    r = httpx.request(method, f"{API}{path}", headers={"X-E2E-Control": SECRET}, timeout=15, **kw)
    r.raise_for_status()
    return r.json()


def portal(method: str, user_id: str, json_body: dict | None = None) -> httpx.Response:
    """Lo que haría el portal con la sesión del cliente (simulada por el arnés)."""
    return httpx.request(method, f"{API}/brasper/identity-links", json=json_body, timeout=15,
                         headers={"Authorization": f"Bearer e2e-portal.{user_id}"})


def issue(user_id: str, subject: str) -> str:
    r = portal("POST", user_id, {"channel": "telegram", "subject": subject})
    if r.status_code != 200:
        raise AssertionError(f"emisión falló {r.status_code}: {r.text[:200]}")
    return r.json()["link_token"]


def grant_row(cid: str) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM identity_grants WHERE conversation_id=?", (cid,)).fetchone()
    return dict(row) if row else None


def ai(method: str, path: str, **kw) -> httpx.Response:
    """Llamada directa a la integración como la haría el bot: secreto + Bearer de servicio."""
    headers = {"X-Brasper-IA-Secret": SECRET}
    bearer = brasper_api._service_token(T.get_config())
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    headers.update(kw.pop("headers", {}))
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=15, **kw)


def route_401(r: httpx.Response) -> bool:
    """401 emitido por la ruta (dato rechazado), no por el middleware (sin WWW-Authenticate)."""
    return r.status_code == 401 and "www-authenticate" not in r.headers


def main() -> int:
    seed = control("GET", "/__e2e/seed")
    owner, other = seed["owner_id"], seed["other_id"]
    own_codes = [c for c, _ in seed["owner_ops"]]
    deleted_code = seed["owner_deleted_op"][0]
    other_codes = [c for c, _ in seed["other_ops"]]
    flags = features.all_flags()
    check("00 flags identity_link + operation_status activas y API local", flags["identity_link"]
          and flags["operation_status"] and brasper_api._base_url(T.get_config()) == API, str(flags))

    owner_ref, intruder_ref, expired_ref, down_ref = "tg:700001", "tg:700002", "tg:700003", "tg:700004"

    # 1) Sin vínculo: el estado deriva a asesor y ofrece el enlace del portal.
    out = say(owner_ref, "¿ya llegó mi envío?")
    cid = out["conversation_id"]
    check("01 sin vínculo -> handoff sin estados privados", out["handoff"]
          and not any(c in out["response"] for c in own_codes + other_codes), out["response"])
    check("01b sin vínculo -> pista del portal con ref en fragmento #",
          "https://portal.e2e.invalid/vincular-chat#canal=telegram&ref=tg%3A700001" in out["response"],
          out["response"])

    # 2) El portal emite un token de un uso para ESTE chat (sesión del dueño).
    token = issue(owner, owner_ref)
    check("02 portal emite token de 43 caracteres", len(token) == 43)
    r = portal("POST", owner, {"channel": "telegram", "subject": "tg:-100"})
    check("02b portal rechaza referencia de grupo de Telegram (422)", r.status_code == 422, r.text)
    r = httpx.post(f"{API}/brasper/identity-links", json={"channel": "telegram", "subject": owner_ref}, timeout=15)
    check("02c sin sesión del portal no se emite token (401)", r.status_code == 401, f"{r.status_code} {r.text}")

    # 3) /start <token> por el camino real del bot.
    out = say(owner_ref, f"/start {token}", cid)
    check("03 /start canjea y responde vinculado", "vinculado" in out["response"]
          and out.get("flow") == "identity_link" and not out["handoff"], json.dumps(out, default=str)[:300])
    stored = " ".join(m["content"] for m in db.get_messages(cid))
    check("03b el token no queda en mensajes (redactado)", token not in stored
          and identity_link.REDACTED in stored, stored[-200:])
    row = grant_row(cid)
    check("03c grant guardado cifrado y atado al dueño", bool(row) and row["brasper_user_id"] == owner
          and row["channel"] == "telegram", str(row and {k: v for k, v in row.items() if k != "grant_ciphertext"}))
    grant = Fernet(GRANT_KEY.encode()).decrypt(row["grant_ciphertext"].encode()).decode() if row else ""
    check("03d grant en claro no aparece en SQLite ni lead_data", bool(grant) and grant not in json.dumps(row)
          and grant not in json.dumps(db.get_lead_data(cid), default=str))
    links = control("GET", "/__e2e/links", params={"user_id": owner})
    check("03e API: vínculo consumido", any(l["consumed"] for l in links), str(links))

    # 4) Estado oficial del dueño (y nada del otro cliente ni lo eliminado).
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    resp = out["response"]
    check("04 estado oficial del dueño sin derivar", not out["handoff"]
          and "E2E-OWN-001: en verificación" in resp and "E2E-OWN-002: completada" in resp, resp)
    check("04b no muestra operaciones del otro cliente ni eliminadas",
          not any(c in resp for c in other_codes + [deleted_code]), resp)
    check("04c flujo determinista (sin LLM)", out.get("usage") is None, str(out.get("usage")))

    # S) Cuenta de servicio del bot (login real /auth/login + JWT real).
    stats = control("GET", "/__e2e/service/stats")
    check("S1 un solo login de servicio hasta aquí (token cacheado)", stats["logins_ok"] == 1
          and stats["sessions_active"] == 1, str(stats))
    revoked = control("POST", "/__e2e/service/revoke-sessions")
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    after = control("GET", "/__e2e/service/stats")
    check("S2 sesión de servicio revocada a mitad de corrida -> la consulta sigue funcionando",
          revoked["revoked"] == 1 and not out["handoff"] and "E2E-OWN-001" in out["response"], out["response"])
    expected_relogins = 1 if AUTH_REQUIRED else 0  # sin AUTH_REQUIRED el middleware ignora el Bearer inválido
    check(f"S3 re-login único tras la revocación ({expected_relogins})",
          after["logins_ok"] - stats["logins_ok"] == expected_relogins
          and after["sessions_active"] == expected_relogins, f"antes={stats} después={after}")
    if AUTH_REQUIRED:
        # Servicio roto (usuario de servicio deshabilitado): ni "código inválido" ni grant olvidado.
        broken_token = issue(owner, "tg:700005")
        control("POST", "/__e2e/service/enable", params={"value": False})
        before = control("GET", "/__e2e/service/stats")
        out = say(owner_ref, "¿ya llegó mi envío?", cid)
        check("S4 servicio rechazado -> handoff sin estados y el grant NO se olvida", out["handoff"]
              and not any(c in out["response"] for c in own_codes) and grant_row(cid) is not None, out["response"])
        out = say("tg:700005", f"/start {broken_token}")
        check("S5 servicio rechazado -> /start responde 'No pude verificar' (no 'no es válido')",
              "No pude verificar" in out["response"], out["response"])
        mid = control("GET", "/__e2e/service/stats")
        links = control("GET", "/__e2e/links", params={"user_id": owner})
        check("S6 el token no se consumió en la API", sum(1 for l in links if l["consumed"]) == 1, str(links))
        from core import brasper_api as _bapi
        check("S6b backoff: con la cuenta rechazada no se reintenta el login en cada llamada",
              _bapi._service["retry_after"] > time.time(), str(_bapi._service["retry_after"]))
        control("POST", "/__e2e/service/enable", params={"value": True})
        _bapi._service["retry_after"] = 0.0  # simula que pasaron los 30 s de backoff
        out = say(owner_ref, "¿ya llegó mi envío?", cid)
        final = control("GET", "/__e2e/service/stats")
        check("S7 servicio rehabilitado -> la consulta vuelve a funcionar", not out["handoff"]
              and "E2E-OWN-001" in out["response"], out["response"])
        print(f"   [info] logins de servicio: antes={before} con-servicio-roto={mid} final={final}", flush=True)

    # 5) Token reutilizado desde otro chat.
    out = say(intruder_ref, f"/start {token}")
    cid_intruder = out["conversation_id"]
    check("05 bot: token reutilizado en otro chat -> no válido, sin grant",
          "no es válido" in out["response"] and grant_row(cid_intruder) is None, out["response"])
    r = ai("POST", "/brasper/ai/identity-links/redeem",
           json={"channel": "telegram", "subject": intruder_ref, "link_token": token})
    check("05b API: mismo token con otro chat -> 401", route_401(r), f"{r.status_code} {r.text}")
    r = ai("POST", "/brasper/ai/identity-links/redeem",
           json={"channel": "telegram", "subject": owner_ref, "link_token": token})
    check("05c API: mismo token en el chat original (segundo canje) -> 401", route_401(r),
          f"{r.status_code} {r.text}")
    r = ai("POST", "/brasper/ai/identity-links/redeem",
           json={"channel": "telegram", "subject": owner_ref, "link_token": token},
           headers={"X-Brasper-IA-Secret": "x" * 32})
    check("05d API: canje sin el secreto de integración -> 401", route_401(r), f"{r.status_code}")

    # 6) Otro chat no puede usar el grant.
    ops_path = f"/brasper/ai/identity-links/{owner}/operations"
    r = ai("GET", ops_path, params={"channel": "telegram", "subject": owner_ref},
           headers={"X-Brasper-Identity-Grant": grant})
    check("06 API: grant con su chat -> 200 con operaciones del dueño", r.status_code == 200
          and sorted(i["code"] for i in r.json()["data"]) == sorted(own_codes), f"{r.status_code} {r.text}")
    r = ai("GET", ops_path, params={"channel": "telegram", "subject": intruder_ref},
           headers={"X-Brasper-Identity-Grant": grant})
    check("06b API: grant usado desde otro chat -> 401", route_401(r), f"{r.status_code} {r.text}")
    r = ai("GET", f"/brasper/ai/identity-links/{other}/operations",
           params={"channel": "telegram", "subject": owner_ref}, headers={"X-Brasper-Identity-Grant": grant})
    check("06c API: grant del dueño contra el otro cliente -> 401", route_401(r), f"{r.status_code}")
    # Fila de grant copiada a la conversación del intruso (p. ej. dato filtrado): el bot la descarta.
    with db.connect() as con:
        con.execute("INSERT INTO identity_grants SELECT ?, channel, subject_hash, brasper_user_id, "
                    "grant_ciphertext, expires_at, created_at FROM identity_grants WHERE conversation_id=?",
                    (cid_intruder, cid))
    out = say(intruder_ref, "¿ya llegó mi envío?", cid_intruder)
    check("06d bot: grant ajeno en otro chat -> handoff y se borra", out["handoff"]
          and grant_row(cid_intruder) is None and not any(c in out["response"] for c in own_codes),
          out["response"])

    # 7) Token vencido (expires_at manipulado en la BD).
    expired_token = issue(owner, expired_ref)
    upd = control("POST", "/__e2e/links/expire-tokens", params={"user_id": owner})
    out = say(expired_ref, f"/start {expired_token}")
    check("07 token vencido -> no válido y sin grant", upd["updated"] >= 1 and "no es válido" in out["response"]
          and grant_row(out["conversation_id"]) is None, f"{upd} {out['response']}")

    # 8) Grant vencido en la API: 401 -> el bot lo olvida y deriva.
    upd = control("POST", "/__e2e/links/expire-grants", params={"user_id": owner})
    check("08 precondición: grant local aún vigente", identity_link.grant_for(cid, "telegram", owner_ref)
          is not None and upd["updated"] >= 1, str(upd))
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    check("08b grant vencido en API -> handoff sin estados", out["handoff"]
          and not any(c in out["response"] for c in own_codes), out["response"])
    check("08c bot olvidó el grant tras el 401", grant_row(cid) is None)

    # 8') Grant vencido localmente (expires_at del bot): se borra sin consultar estados.
    out = say(owner_ref, f"/start {issue(owner, owner_ref)}", cid)
    check("08d re-vinculación con token nuevo", "vinculado" in out["response"], out["response"])
    with db.connect() as con:
        con.execute("UPDATE identity_grants SET expires_at=? WHERE conversation_id=?",
                    ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), cid))
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    check("08e grant vencido local -> handoff y borrado", out["handoff"] and grant_row(cid) is None
          and not any(c in out["response"] for c in own_codes), out["response"])

    # 9) Revocación desde la cuenta (DELETE): la consulta falla y el bot olvida el grant.
    out = say(owner_ref, f"/start {issue(owner, owner_ref)}", cid)
    ok_link = "vinculado" in out["response"]
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    check("09 precondición: vinculado consulta estados", ok_link and "E2E-OWN-001" in out["response"],
          out["response"])
    r = portal("DELETE", owner)
    check("09b portal revoca vínculos (DELETE)", r.status_code == 200 and r.json().get("revoked", 0) >= 1,
          f"{r.status_code} {r.text}")
    out = say(owner_ref, "¿ya llegó mi envío?", cid)
    check("09c tras revocar -> handoff sin estados", out["handoff"]
          and not any(c in out["response"] for c in own_codes), out["response"])
    check("09d bot olvidó el grant revocado", grant_row(cid) is None)
    r = portal("DELETE", other)
    check("09e revocar al otro cliente no afecta (0 vínculos)", r.status_code == 200
          and r.json().get("revoked") == 0, r.text)

    # 10) API caída: sin excepción, derivación; el /start pendiente responde «No pude verificar».
    out = say(owner_ref, f"/start {issue(owner, owner_ref)}", cid)
    check("10 precondición: re-vinculado antes de la caída", "vinculado" in out["response"], out["response"])
    pending_token = issue(owner, down_ref)
    control("POST", "/__e2e/shutdown")
    down = False
    for _ in range(40):
        try:
            httpx.get(f"{API}/health", timeout=0.5)
            time.sleep(0.25)
        except httpx.HTTPError:
            down = True
            break
    check("10b API detenida (puerto cerrado)", down)
    try:
        out = say(owner_ref, "¿ya llegó mi envío?", cid)
        check("10c API caída -> handoff sin crash ni estados", out["handoff"]
              and not any(c in out["response"] for c in own_codes), out["response"])
        check("10d API caída no borra el grant (solo un 401 lo invalida)", grant_row(cid) is not None)
        out = say(down_ref, f"/start {pending_token}")
        check("10e /start con API caída -> 'No pude verificar' sin crash",
              "No pude verificar" in out["response"] and not out["handoff"], out["response"])
    except Exception as exc:  # noqa: BLE001
        check("10c API caída sin excepción", False, f"{type(exc).__name__}: {exc}")

    check("11 guardia de red: ninguna conexión fuera de loopback", not BLOCKED, str(BLOCKED))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        check("ZZ ejecución completa sin excepción", False, f"{type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\nRESULTADO identity_e2e: {passed}/{len(RESULTS)} PASS", flush=True)
    results_path = Path(os.environ.get("E2E_RESULTS") or (_TMP / "results.json"))
    results_path.write_text(json.dumps([{"case": n, "ok": ok, "detail": d} for n, ok, d in RESULTS],
                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"resultados: {results_path}")
    sys.exit(0 if passed == len(RESULTS) else 1)
