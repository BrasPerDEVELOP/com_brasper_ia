"""Vinculación verificable de canales sin teléfono (Telegram / webchat) con la cuenta Brasper.

Flujo: el cliente inicia sesión en el portal Brasper, que emite un token de un uso
(5 min) atado a este chat. El cliente lo trae al chat (deep-link `/start <token>` en
Telegram o pegándolo en webchat). El bot lo canjea en la API por un grant de 30 min y
lo guarda cifrado en `identity_grants`; nunca en mensajes, lead_data ni el LLM.

Nombre, documento, número escrito o conocer la referencia de una operación NO vinculan.
Sin grant válido la consulta privada se deriva a un asesor.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

from . import brasper_api, db, features, observability, tenants, tool_contracts, util

GRANT_KEY_ENV = "BRASPER_IA_GRANT_KEY"
REDACTED = "[código de vinculación]"
_TOKEN = r"[A-Za-z0-9_-]{43}"
# Deep-link de Telegram (/start <token>), comando explícito o el token solo en la línea.
_TOKEN_RE = re.compile(
    rf"(?:^|(?<=\s))(?:/start\s+|/vincular\s+|vincular\s+(?:chat\s+)?|vincular:\s*)?({_TOKEN})(?=\s|$)",
    re.IGNORECASE | re.MULTILINE)
# Redacción más amplia que el canje: cualquier secuencia aislada con forma de código
# (p. ej. "código:XXXX." o entre comillas) se oculta aunque no se canjee.
_REDACT_RE = re.compile(rf"(?<![A-Za-z0-9_-]){_TOKEN}(?![A-Za-z0-9_-])")
_TELEGRAM_SUBJECT = re.compile(r"tg:[1-9][0-9]{0,19}")
_WEBCHAT_SUBJECT = re.compile(r"[A-Za-z0-9:+._-]{16,160}")
_GENERIC_WEBCHAT = {"webchat-visitor", "webchat:webchat", "webchat"}


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS identity_grants (conversation_id TEXT PRIMARY KEY, "
                    "channel TEXT NOT NULL, subject_hash TEXT NOT NULL, brasper_user_id TEXT NOT NULL, "
                    "grant_ciphertext TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)")


AMBIGUOUS = "__several_link_codes__"


def extract_token(text: str) -> tuple[str, str | None]:
    """Devuelve (texto con TODOS los códigos redactados, token). Con varios códigos distintos
    no se canjea ninguno (`AMBIGUOUS`): el cliente debe enviar solo el suyo."""
    found = {m.group(1) for m in _TOKEN_RE.finditer(text or "")}
    redacted = _REDACT_RE.sub(REDACTED, _TOKEN_RE.sub(REDACTED, text or "")).strip()
    if not found:
        return (redacted if redacted != (text or "").strip() else text), None
    return redacted, found.pop() if len(found) == 1 else AMBIGUOUS


def subject_for(channel: str, user_ref: str) -> str | None:
    """Referencia de canal que la API acepta; None si el canal no admite vinculación."""
    ref = (user_ref or "").strip()
    if channel == "telegram" and _TELEGRAM_SUBJECT.fullmatch(ref):
        return ref
    # Webchat: solo sesiones con identificador propio (nunca el visitante genérico compartido).
    if channel == "webchat" and ref not in _GENERIC_WEBCHAT and _WEBCHAT_SUBJECT.fullmatch(ref):
        return ref
    return None


def _available() -> bool:
    return features.enabled("identity_link") and bool(os.getenv(GRANT_KEY_ENV))


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(os.environ[GRANT_KEY_ENV].encode())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _parse(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _store(cid: str, channel: str, subject: str, user_id: str, grant: str, expires_at: str) -> None:
    cipher = _fernet().encrypt(grant.encode()).decode()
    with db.connect() as con:
        con.execute("INSERT INTO identity_grants VALUES (?,?,?,?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET "
                    "channel=excluded.channel, subject_hash=excluded.subject_hash, "
                    "brasper_user_id=excluded.brasper_user_id, grant_ciphertext=excluded.grant_ciphertext, "
                    "expires_at=excluded.expires_at, created_at=excluded.created_at",
                    (cid, channel, _digest(subject), user_id, cipher, expires_at, util.now_iso()))


def revoke(cid: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM identity_grants WHERE conversation_id=?", (cid,))


def grant_for(cid: str, channel: str, user_ref: str) -> dict | None:
    """Grant vigente de ESTA conversación y ESTE canal; vencido o ajeno -> None (y se borra)."""
    subject = subject_for(channel, user_ref)
    if not subject or not _available():
        return None
    with db.connect() as con:
        row = con.execute("SELECT channel, subject_hash, brasper_user_id, grant_ciphertext, expires_at "
                          "FROM identity_grants WHERE conversation_id=?", (cid,)).fetchone()
    if not row:
        return None
    row = dict(row)
    expiry = _parse(row["expires_at"])
    if (row["channel"] != channel or row["subject_hash"] != _digest(subject)
            or expiry is None or expiry <= datetime.now(timezone.utc)):
        revoke(cid)
        return None
    try:
        grant = _fernet().decrypt(row["grant_ciphertext"].encode()).decode()
    except Exception:  # clave rotada o dato alterado: el grant deja de servir
        revoke(cid)
        return None
    return {"user_id": row["brasper_user_id"], "grant": grant, "channel": channel, "subject": subject}


_REPLIES = {
    "linked": ("Listo ✅ Este chat quedó vinculado a tu cuenta Brasper durante 30 minutos. "
               "Ya puedes preguntarme por el estado de tus envíos.",
               "Pronto ✅ Este chat ficou vinculado à sua conta Brasper por 30 minutos. "
               "Já pode me perguntar sobre o status dos seus envios."),
    "invalid": ("Ese código de vinculación no es válido, ya se usó o venció. Genera uno nuevo desde tu cuenta "
                "Brasper (Vincular chat) o, si prefieres, te ayuda un asesor aquí mismo.",
                "Esse código de vinculação não é válido, já foi usado ou venceu. Gere um novo na sua conta "
                "Brasper (Vincular chat) ou, se preferir, um atendente te ajuda aqui mesmo."),
    "unavailable": ("No pude verificar el código en este momento. Inténtalo de nuevo en unos minutos con un "
                    "código nuevo; mientras tanto un asesor puede ayudarte aquí mismo.",
                    "Não consegui verificar o código agora. Tente de novo em alguns minutos com um código novo; "
                    "enquanto isso um atendente pode te ajudar aqui mesmo."),
    "ambiguous": ("Recibí más de un código de vinculación. Por seguridad no usé ninguno: envía solo el código "
                  "que generaste en tu cuenta Brasper.",
                  "Recebi mais de um código de vinculação. Por segurança não usei nenhum: envie só o código "
                  "que você gerou na sua conta Brasper."),
    "unsupported": ("Este chat no admite vinculación de cuenta. Un asesor puede ayudarte aquí mismo.",
                    "Este chat não permite vincular a conta. Um atendente pode te ajudar aqui mesmo."),
}


def _reply(key: str, language: str) -> str:
    return _REPLIES[key][int(language == "pt")]


def _redeem_and_store(cid: str, channel: str, subject: str, link_token: str) -> dict:
    """Canje + guardado cifrado en el mismo paso: si la API responde tarde (después del
    timeout del contrato) el grant igual queda guardado y el resultado registrado en
    idempotencia no contiene secretos."""
    result = brasper_api.redeem_identity_link(tenants.get_config(), channel=channel,
                                              subject=subject, link_token=link_token)
    body = result.get("data") if result.get("ok") else None
    if (not isinstance(body, dict) or not isinstance(body.get("grant"), str)
            or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(body.get("user_id") or ""))
            or _parse(body.get("expires_at")) is None):
        return {"linked": False, "rejected": result.get("status") in {401, 422}}
    _store(cid, channel, subject, body["user_id"], body["grant"], str(body["expires_at"]))
    return {"linked": True}


def redeem(cid: str, channel: str, user_ref: str, token: str, language: str) -> str:
    """Canjea el token una sola vez. Un timeout no se reintenta con la API: el mismo token
    devuelve el resultado registrado o «pendiente de verificar», nunca un segundo canje."""
    if token == AMBIGUOUS:
        observability.event("identity_link.ambiguous", conversation_id=cid)
        return _reply("ambiguous", language)
    subject = subject_for(channel, user_ref)
    if not subject or not _available():
        observability.event("identity_link.unsupported", conversation_id=cid, channel=channel)
        return _reply("unsupported", language)
    run = tool_contracts.run(
        "identity.redeem", {"channel": channel, "subject": subject, "link_token": token},
        lambda **kw: _redeem_and_store(cid, **kw),
        idempotency_key="identity.redeem:" + _digest(token))
    outcome = run.get("data") if run.get("ok") else None
    if isinstance(outcome, dict) and outcome.get("linked") and grant_for(cid, channel, user_ref):
        observability.event("identity_link.linked", conversation_id=cid, channel=channel)
        return _reply("linked", language)
    rejected = isinstance(outcome, dict) and outcome.get("rejected")
    observability.event("identity_link.rejected" if rejected else "identity_link.error",
                        conversation_id=cid, error_code=run.get("error_code"))
    return _reply("invalid" if rejected or (isinstance(outcome, dict) and outcome.get("linked"))
                  else "unavailable", language)


def portal_hint(channel: str, user_ref: str, language: str) -> str | None:
    """Indicación para vincular desde el portal; None si el canal no lo admite o falta config."""
    subject = subject_for(channel, user_ref)
    base = brasper_api._api_cfg(tenants.get_config() or {}).get("identity_link_url") or ""
    if not subject or not _available() or not base.startswith("https://"):
        return None
    # Fragmento (#): el navegador no lo envía al servidor ni queda en logs de acceso.
    url = f"{base}#canal={channel}&ref={quote(subject, safe='')}"
    if language == "pt":
        return ("Se quiser consultar por aqui, entre na sua conta Brasper por este link e toque em "
                f"«Vincular este chat»: {url}")
    return f"Si quieres consultarlo por aquí, entra a tu cuenta Brasper desde este enlace y toca «Vincular este chat»: {url}"
