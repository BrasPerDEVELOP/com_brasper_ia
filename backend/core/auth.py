"""Autenticación del panel interno + RBAC.

Credenciales individuales (plan de campañas y usuarios, sección 5):
  - Cada usuario tiene contraseña propia guardada con scrypt (stdlib, sal aleatoria,
    parámetros dentro del propio hash). La contraseña nunca se guarda ni se registra.
  - El login emite un token de SESIÓN opaco (`s.<aleatorio>`): en la base solo se guarda
    su SHA-256 (`panel_sessions.token_hash`), con vencimiento (PANEL_SESSION_HOURS,
    12 h por defecto) y revocación (logout, "cerrar sesiones", desactivación, reset).
  - `panel_users.active=0` bloquea el login y TODAS sus sesiones/tokens al instante:
    se verifica en cada request (`user_from_token`).
  - Compatibilidad: `panel_users.token` sigue siendo un token de API estático (lo usan
    `PANEL_ADMIN_TOKEN`, `manage.py create-admin` y los usuarios demo de desarrollo).
    Se reemplaza por un valor inutilizable ('!' + aleatorio, rechazado siempre) al fijar
    contraseña, resetear, cerrar sesiones o desactivar. Un usuario SIN contraseña puede
    seguir entrando con email + PANEL_LOGIN_CODE mientras ese código exista (transición,
    ver RUNBOOK §1.5). En desarrollo, sin código, el login por email desde localhost sigue.

El token viaja en el header 'X-Auth-Token'.

RBAC: matriz {rol: [permisos]}. Un permiso es una cadena 'recurso:accion'
(o 'recurso:*' para comodín sobre el recurso). El comodín global '*' da todo.
Solo `owner` gestiona usuarios y roles (`require_owner`, ver core/users.py).

Gating opt-in:
    from core import auth
    @router.get("/api/algo", dependencies=[Depends(auth.require("usage:read"))])
o para leer el usuario dentro del handler:
    def handler(user: dict = Depends(auth.require("usage:read"))): ...
"""
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from . import db


# ---------------------------------------------------------------------------
# RBAC — matriz de permisos por rol (modelo agencia)
# ---------------------------------------------------------------------------
# Permisos como 'recurso:accion'. '*' = todo. 'recurso:*' = todo sobre recurso.
ROLE_PERMS: dict[str, list[str]] = {
    # Dueño de la agencia: acceso total.
    "owner": ["*"],
    # Admin de agencia: opera todo salvo gestión de usuarios/facturación sensible.
    "admin": [
        "tenants:read", "tenants:write",
        "conversations:read", "conversations:write", "media:private",
        "usage:read",
        "chat:test",
        "config:read", "config:write",
        "users:read",
    ],
    # Builder: configura tenants y prompts, prueba el chat; no ve facturación ni usuarios.
    "builder": [
        "tenants:read", "tenants:write",
        "conversations:read",
        "chat:test",
        "config:read", "config:write",
    ],
    # Analyst: solo lectura de datos y consumo (para reportes/economía unitaria).
    "analyst": [
        "tenants:read",
        "conversations:read",
        "usage:read",
    ],
    # Agent: atención al cliente — lee/escribe conversaciones (handoff), sin config ni billing.
    "agent": [
        "tenants:read",
        "conversations:read", "conversations:write", "media:private",
        "chat:test",
    ],
    # Billing: facturación y consumo; nada de operación ni configuración.
    "billing": [
        "tenants:read",
        "usage:read",
        "billing:read", "billing:write",
    ],
    # Viewer: solo lectura mínima.
    "viewer": [
        "tenants:read",
        "conversations:read",
        "usage:read",
    ],
}


def has_perm(user: dict | None, perm: str) -> bool:
    """True si el usuario tiene el permiso. Soporta comodines '*' y 'recurso:*'."""
    if not user:
        return False
    perms = ROLE_PERMS.get(user.get("role", ""), [])
    if "*" in perms or perm in perms:
        return True
    resource = perm.split(":", 1)[0]
    return f"{resource}:*" in perms


def permissions_for(user: dict | None) -> list[str]:
    """Lista de permisos efectivos del usuario (para exponer al frontend)."""
    if not user:
        return []
    return list(ROLE_PERMS.get(user.get("role", ""), []))


# ---------------------------------------------------------------------------
# Esquema y seed
# ---------------------------------------------------------------------------
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS panel_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_panel_users_token ON panel_users(token);
CREATE TABLE IF NOT EXISTS panel_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  method TEXT
);
CREATE INDEX IF NOT EXISTS idx_panel_sessions_user ON panel_sessions(user_id);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS panel_users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_panel_users_token ON panel_users(token);
CREATE TABLE IF NOT EXISTS panel_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  method TEXT
);
CREATE INDEX IF NOT EXISTS idx_panel_sessions_user ON panel_sessions(user_id);
"""

# Columnas de credenciales (migración 0012). Aditivas: los usuarios existentes quedan
# activos y sin contraseña (entran por la vía de compatibilidad hasta fijar una).
USER_CREDENTIAL_COLUMNS: dict[str, str] = {
    "password_hash": "TEXT",
    "active": "INTEGER NOT NULL DEFAULT 1",
    "must_change_password": "INTEGER NOT NULL DEFAULT 0",
    "password_changed_at": "TEXT",
    "deactivated_at": "TEXT",
}


def ensure_schema() -> None:
    with db.connect() as con:
        con.executescript(_POSTGRES_SCHEMA if db.is_postgres() else _SQLITE_SCHEMA)
    db.has_column.cache_clear()
    for column, ddl in USER_CREDENTIAL_COLUMNS.items():
        if db.has_column("panel_users", column):
            continue
        try:
            with db.connect() as con:
                if db.is_postgres():
                    con.execute(f"ALTER TABLE panel_users ADD COLUMN IF NOT EXISTS {column} {ddl}")
                else:
                    con.execute(f"ALTER TABLE panel_users ADD COLUMN {column} {ddl}")
        except Exception as exc:  # noqa: BLE001 - arranques concurrentes: otro worker la creó
            if "duplicate column" not in str(exc).lower():
                raise
        db.has_column.cache_clear()


from .util import env_bool as _env_true  # noqa: E402  (helpers únicos, ver core/util.py)
from .util import is_production as _is_production  # noqa: E402
from .util import normalize_email  # noqa: E402


def _clean_name(name: str) -> str:
    """Nombre visible seguro: sin caracteres de control, acotado a 80 chars."""
    name = "".join(ch for ch in (name or "") if ch.isprintable()).strip()
    return name[:80] or "Administrador"


# Usuarios demo (SOLO desarrollo): tokens fijos y legibles. Nunca en producción
# salvo que se fuerce con SEED_DEMO_USERS=true.
_DEMO_TOKENS = ("demo-owner", "demo-agent-brasper", "demo-billing")
_SEED_USERS = [
    {"email": "owner@agencia.com", "name": "Dueño Agencia",
     "role": "owner", "token": "demo-owner"},
    {"email": "agent@brasper.com", "name": "Agente Brasper",
     "role": "agent", "token": "demo-agent-brasper"},
    {"email": "billing@agencia.com", "name": "Facturación Agencia",
     "role": "billing", "token": "demo-billing"},
]
_DEMO_EMAILS = tuple(u["email"] for u in _SEED_USERS)


def _seed_prod_admin(con) -> None:
    """Crea/actualiza el owner de producción desde variables de entorno.

    Requiere PANEL_ADMIN_EMAIL y PANEL_ADMIN_TOKEN. El token NO se genera aquí:
    evitamos imprimir secretos en el log del servidor. Para generar uno usa
    `python manage.py create-admin` (lo muestra una vez en tu terminal).
    Idempotente y tolerante a arranques concurrentes (INSERT OR IGNORE + UPDATE);
    rotar = cambiar PANEL_ADMIN_TOKEN y reiniciar. No reactiva una cuenta desactivada
    ni toca su contraseña: con credenciales individuales, PANEL_ADMIN_TOKEN es solo el
    token de API de operación y puede retirarse del entorno (ver RUNBOOK §1.5).
    """
    email = normalize_email(os.getenv("PANEL_ADMIN_EMAIL"))
    if not email:
        return
    token = (os.getenv("PANEL_ADMIN_TOKEN") or "").strip()
    if not token:
        exists = con.execute("SELECT 1 FROM panel_users WHERE email=?", (email,)).fetchone()
        if not exists:
            print(f"[auth] AVISO: PANEL_ADMIN_EMAIL={email} pero falta PANEL_ADMIN_TOKEN; "
                  f"no se creó admin. Genera uno con: python manage.py create-admin --email {email}")
        return
    name = _clean_name(os.getenv("PANEL_ADMIN_NAME") or "Administrador")
    if db.is_postgres():
        con.execute(
            "INSERT INTO panel_users (email, name, role, token) "
            "VALUES (?,?,?,?) ON CONFLICT (email) DO NOTHING",
            (email, name, "owner", token))
    else:
        con.execute(
            "INSERT OR IGNORE INTO panel_users (email, name, role, token) "
            "VALUES (?,?,?,?)", (email, name, "owner", token))
    con.execute("UPDATE panel_users SET token=?, role='owner', name=? WHERE email=?",
                (token, name, email))


def ensure_seed() -> None:
    """Prepara los usuarios del panel según el entorno (APP_ENV).

    - APP_ENV=production: crea el owner desde PANEL_ADMIN_EMAIL/PANEL_ADMIN_TOKEN,
      NO siembra usuarios demo y PURGA cualquier usuario demo heredado (p.ej. si se
      reutiliza una DB de desarrollo). Fuerza demo solo con SEED_DEMO_USERS=true.
    - Desarrollo (default): siembra los usuarios demo (tokens legibles) para local.
    """
    ensure_schema()
    prod = _is_production()
    seed_demo = _env_true("SEED_DEMO_USERS") or not prod
    with db.connect() as con:
        _seed_prod_admin(con)
        if prod and not seed_demo:
            # Elimina usuarios demo predecibles que pudieran venir de una DB de dev
            # (por token o por email: un token demo rotado no debe dejar la cuenta viva).
            tph = ",".join("?" * len(_DEMO_TOKENS))
            eph = ",".join("?" * len(_DEMO_EMAILS))
            con.execute(f"DELETE FROM panel_users WHERE token IN ({tph}) OR email IN ({eph})",
                        (*_DEMO_TOKENS, *_DEMO_EMAILS))
        if seed_demo:
            if db.is_postgres():
                con.executemany(
                    "INSERT INTO panel_users (email, name, role, token) "
                    "VALUES (%(email)s, %(name)s, %(role)s, %(token)s) "
                    "ON CONFLICT (email) DO NOTHING",
                    _SEED_USERS)
            else:
                con.executemany(
                    "INSERT OR IGNORE INTO panel_users (email, name, role, token) "
                    "VALUES (:email, :name, :role, :token)",
                    _SEED_USERS)


# ---------------------------------------------------------------------------
# Contraseñas (scrypt, solo stdlib)
# ---------------------------------------------------------------------------
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 3
_SCRYPT_MAXMEM = 128 * 1024 * 1024
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """Hash scrypt con sal aleatoria: 'scrypt$N$r$p$sal$hash' (parámetros versionados)."""
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                        p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str | None, stored: str | None) -> bool:
    """Comparación en tiempo constante. Hash ausente/corrupto = False (nunca abre)."""
    if not password or not stored:
        return False
    try:
        algo, n, r, p, salt, expected = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        if algo != "scrypt" or n > 2 ** 20 or r > 32 or p > 16:
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=n, r=r, p=p,
                            maxmem=_SCRYPT_MAXMEM, dklen=len(_unb64(expected)))
        return hmac.compare_digest(dk, _unb64(expected))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH: str | None = None


def _dummy_verify(password: str | None) -> None:
    """Mismo costo que una verificación real: no revela si el email existe."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password or "x", _DUMMY_HASH)


def validate_new_password(password: str | None, email: str | None = None) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña admite como máximo {MAX_PASSWORD_LENGTH} caracteres")
    if not password.strip() or len(set(password)) < 4:
        raise ValueError("La contraseña es demasiado simple")
    if email and password.strip().lower() == normalize_email(email):
        raise ValueError("La contraseña no puede ser tu correo")
    return password


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)


def _disabled_token() -> str:
    """Valor para `panel_users.token` que ningún request puede usar ('!' se rechaza)."""
    return "!" + secrets.token_urlsafe(24)


def _login_code() -> str | None:
    return (os.getenv("PANEL_LOGIN_CODE") or "").strip() or None


# ---------------------------------------------------------------------------
# Sesiones (token opaco; en la base solo su SHA-256)
# ---------------------------------------------------------------------------
SESSION_PREFIX = "s."


def session_hours() -> float:
    try:
        return min(720.0, max(0.05, float(os.getenv("PANEL_SESSION_HOURS") or 12)))
    except ValueError:
        return 12.0


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


def create_session(user_id: int, method: str) -> str:
    token = SESSION_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with db.connect() as con:
        con.execute(
            "INSERT INTO panel_sessions (token_hash, user_id, created_at, expires_at, method) "
            "VALUES (?,?,?,?,?)",
            (_hash_token(token), user_id, _iso(now), _iso(now + timedelta(hours=session_hours())), method))
    return token


def revoke_session(token: str | None) -> bool:
    if not token or not token.startswith(SESSION_PREFIX):
        return False
    with db.connect() as con:
        return con.execute("UPDATE panel_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                           (_now(), _hash_token(token))).rowcount == 1


def revoke_user_sessions(con, user_id: int, except_hash: str | None = None) -> int:
    """Revoca las sesiones vigentes del usuario (dentro de la transacción `con`)."""
    sql = "UPDATE panel_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL"
    args: list = [_now(), user_id]
    if except_hash:
        sql += " AND token_hash<>?"
        args.append(except_hash)
    return con.execute(sql, args).rowcount or 0


def active_session_counts() -> dict[int, int]:
    with db.connect() as con:
        rows = con.execute(
            "SELECT user_id, COUNT(*) AS n FROM panel_sessions WHERE revoked_at IS NULL AND expires_at>? "
            "GROUP BY user_id", (_now(),)).fetchall()
    return {int(r["user_id"]): int(r["n"]) for r in rows}


def set_password(user_id: int, password: str, must_change: bool,
                 keep_session_hash: str | None = None) -> None:
    """Guarda el hash, invalida el token estático y revoca las sesiones (salvo la actual)."""
    hashed = hash_password(password)
    with db.connect() as con:
        con.execute(
            "UPDATE panel_users SET password_hash=?, must_change_password=?, password_changed_at=?, token=? "
            "WHERE id=?", (hashed, 1 if must_change else 0, _now(), _disabled_token(), user_id))
        revoke_user_sessions(con, user_id, except_hash=keep_session_hash)


# ---------------------------------------------------------------------------
# Consultas / autenticación
# ---------------------------------------------------------------------------
def _col(row, key: str, default=None):
    return row[key] if key in row.keys() else default


def _row_to_user(row) -> dict:
    """Usuario interno. Nunca incluye el hash de contraseña."""
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "token": row["token"],
        "access_scope": _col(row, "access_scope"),
        "active": _col(row, "active", 1) is None or bool(int(_col(row, "active", 1))),
        "has_password": bool(_col(row, "password_hash")),
        "must_change_password": bool(int(_col(row, "must_change_password", 0) or 0)),
    }


def list_advisors() -> list[dict]:
    """Asesores (rol 'agent') ACTIVOS que pueden atender."""
    try:
        with db.connect() as con:
            rows = con.execute(
                "SELECT * FROM panel_users WHERE role='agent' AND active=1 ORDER BY id"
            ).fetchall()
    except Exception:  # noqa: BLE001 - tabla aún no creada: sin asesores, no rompe el handoff
        return []
    return [_row_to_user(r) for r in rows]


def pick_advisor(conversation_id: str | None = None) -> dict | None:
    """Derivación: elige el asesor con menos conversaciones en handoff activas.

    Con la flag `presence_required` solo cuenta a los asesores con presencia
    `available` y heartbeat vigente (nunca a uno ausente). Si no hay ninguno, la
    conversación queda en cola (sin asignar) y el panel la muestra en "Libres"."""
    from . import features, presence  # noqa: PLC0415 - evita import circular
    advisors = list_advisors()
    if not advisors:
        return None
    if features.enabled("presence_required"):
        snap = presence.snapshot()
        advisors = [u for u in advisors if snap.get(u["email"], {}).get("status") == "available"]
        if not advisors:
            return None
    if conversation_id:
        # Solo asesores con alcance sobre la conversación (canal, número, sector).
        from . import access  # noqa: PLC0415
        conv = db.get_conversation(conversation_id)
        advisors = [u for u in advisors if conv and access.conversation_allowed(u, conv)]
        if not advisors:
            return None
    load = db.handoff_load_by_agent()
    return min(advisors, key=lambda u: (load.get(u["email"], 0), u["id"]))


def derive_to_advisor(conversation_id: str) -> str | None:
    """Asigna la conversación al asesor con menos carga y devuelve su email (o None).

    Usado por el handoff del grafo y por la recepción de comprobantes (Telegram/
    WhatsApp): un solo punto de derivación para todo el sistema (DRY). La asignación
    es un claim atómico: si otro proceso la asignó un instante antes, se respeta."""
    advisor = pick_advisor(conversation_id)
    if advisor:
        try:
            if not db.claim_conversation(conversation_id, advisor["email"]):
                current = (db.get_conversation(conversation_id) or {}).get("assigned_to")
                return current
        except Exception:  # noqa: BLE001 - asignación best-effort, no rompe el flujo
            return None
        return advisor["email"]
    try:
        from . import observability  # noqa: PLC0415
        observability.event("handoff.queued", conversation_id=conversation_id, reason="no_advisor_available")
    except Exception:  # noqa: BLE001
        pass
    return None


def user_from_token(token: str | None) -> dict | None:
    """Usuario ACTIVO dueño del token: sesión vigente (hash) o token estático heredado."""
    if not token or len(token) > 512:
        return None
    if token.startswith(SESSION_PREFIX):
        with db.connect() as con:
            row = con.execute(
                "SELECT u.*, s.token_hash AS session_hash FROM panel_sessions s "
                "JOIN panel_users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.active=1",
                (_hash_token(token), _now())).fetchone()
        if not row:
            return None
        user = _row_to_user(row)
        user["session_hash"] = row["session_hash"]
        return user
    if token.startswith("!"):
        return None
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM panel_users WHERE token=? AND active=1", (token,)).fetchone()
    return _row_to_user(row) if row else None


def user_from_email(email: str | None) -> dict | None:
    """Usuario por email (incluye desactivados: lo usa la gestión de usuarios)."""
    if not email:
        return None
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM panel_users WHERE email=?", (normalize_email(email),)).fetchone()
    return _row_to_user(row) if row else None


def login_options() -> dict:
    """Qué muestra el formulario de login (sin revelar secretos)."""
    legacy = bool(_login_code())
    return {"password": True, "legacy_code": legacy,
            "dev_local": not legacy and not _is_production()}


def _audit_login(email: str, ok: bool, detail: str, ip: str | None) -> None:
    try:
        if ok:
            db.add_audit_event(email, "auth.login", f"user:{email}", {"method": detail})
        else:
            db.add_audit_event(None, "auth.login_failed", f"user:{email[:120]}",
                               {"reason": detail, "ip": (ip or "")[:64]})
        from . import observability  # noqa: PLC0415
        observability.event("auth.login" if ok else "auth.login_failed", reason=detail)
    except Exception:  # noqa: BLE001 - la auditoría no debe tumbar el login
        pass


def login(email: str, code: str | None = None, local_request: bool = False,
          password: str | None = None, ip: str | None = None) -> dict | None:
    """Login del panel. Devuelve {"token", "user"} con un token de sesión nuevo, o None.

    - Usuario con contraseña: exige `password` (scrypt). El código compartido no sirve.
    - Usuario SIN contraseña (transición): con PANEL_LOGIN_CODE definido, exige ese código
      (comparación constante). Sin código, solo en DESARROLLO desde localhost. En
      producción nunca hay atajo por IP.
    - Cuenta desactivada: siempre None. Los fallos se auditan sin la contraseña.
    """
    email = normalize_email(email)[:254]
    with db.connect() as con:
        row = con.execute("SELECT * FROM panel_users WHERE email=?", (email,)).fetchone()
    if not row:
        _dummy_verify(password)
        _audit_login(email, False, "unknown_user", ip)
        return None
    stored = _col(row, "password_hash")
    if stored:
        if not verify_password(password, stored):
            _audit_login(email, False, "bad_password", ip)
            return None
        method = "password"
    else:
        required = _login_code()
        if required:
            supplied = (code or password or "").strip()
            if not supplied or not secrets.compare_digest(supplied, required):
                _audit_login(email, False, "bad_code", ip)
                return None
            method = "legacy_code"
        elif local_request and not _is_production():
            method = "dev_local"
        else:
            _audit_login(email, False, "no_password", ip)
            return None
    user = _row_to_user(row)
    if not user["active"]:
        _audit_login(email, False, "inactive", ip)
        return None
    token = create_session(user["id"], method)
    _audit_login(email, True, method, ip)
    return {"token": token, "user": _public_user(user)}


def change_own_password(user: dict, current: str | None, new: str) -> None:
    """Cambio de contraseña por el propio usuario (exige la actual).

    Sin contraseña previa (transición) la "actual" es el PANEL_LOGIN_CODE vigente; en
    desarrollo sin código no se exige. Revoca las demás sesiones y conserva la actual."""
    with db.connect() as con:
        row = con.execute("SELECT * FROM panel_users WHERE id=? AND active=1", (user["id"],)).fetchone()
    if not row:
        raise PermissionError("Cuenta no disponible")
    stored = _col(row, "password_hash")
    if stored:
        if not verify_password(current, stored):
            raise PermissionError("La contraseña actual no es correcta")
    else:
        required = _login_code()
        if required:
            if not current or not secrets.compare_digest(current.strip(), required):
                raise PermissionError("Para fijar tu primera contraseña escribe el código de acceso vigente")
        elif _is_production():
            raise PermissionError("Fija la primera contraseña con: python manage.py set-password --email <correo>")
    validate_new_password(new, row["email"])
    if stored and verify_password(new, stored):
        raise ValueError("La nueva contraseña debe ser distinta de la actual")
    set_password(row["id"], new, must_change=False, keep_session_hash=user.get("session_hash"))
    db.add_audit_event(row["email"], "user.password_changed", f"user:{row['email']}",
                       {"other_sessions_revoked": True})


def _public_user(user: dict) -> dict:
    """Vista del usuario sin token ni hash, con permisos efectivos (para /api/me y login)."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "permissions": permissions_for(user),
        "access_scope": user.get("access_scope"),
        "active": user.get("active", True),
        "has_password": user.get("has_password", False),
        "must_change_password": user.get("must_change_password", False),
    }


def create_user(email: str, name: str, role: str,
                token: str | None = None, password: str | None = None,
                must_change_password: bool = False) -> dict:
    """Alta de usuario (gestión interna). Sin `token` el token estático queda inutilizable
    cuando hay contraseña, o aleatorio (no mostrado) si no la hay."""
    if role not in ROLE_PERMS:
        raise ValueError(f"Rol desconocido: {role!r}")
    if not token:
        token = _disabled_token() if password else secrets.token_urlsafe(24)
    hashed = hash_password(password) if password else None
    email = normalize_email(email)
    with db.connect() as con:
        con.execute(
            "INSERT INTO panel_users (email, name, role, token, password_hash, must_change_password, "
            "password_changed_at, active) VALUES (?,?,?,?,?,?,?,1)",
            (email, name, role, token, hashed, 1 if must_change_password else 0,
             _now() if hashed else None))
        row = con.execute("SELECT * FROM panel_users WHERE email=?", (email,)).fetchone()
    return _row_to_user(row)


# ---------------------------------------------------------------------------
# Dependencia FastAPI (gating opt-in)
# ---------------------------------------------------------------------------
def _authenticated(token: str | None) -> dict:
    user = user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token ausente o inválido")
    return user


def _assert_password_ok(user: dict) -> None:
    if user.get("must_change_password"):
        raise HTTPException(status_code=403, detail="Debes cambiar tu contraseña temporal antes de continuar")


def require(perm: str):
    """Dependencia que exige un permiso.

    401 si falta/invalida el token (o la cuenta está desactivada); 403 si el token es
    válido pero sin permiso, o si la contraseña temporal aún no se cambió.
    Devuelve el dict del usuario autenticado al handler.
    """
    def _dep(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
        user = _authenticated(x_auth_token)
        _assert_password_ok(user)
        if not has_perm(user, perm):
            raise HTTPException(
                status_code=403,
                detail=f"Rol '{user['role']}' no tiene el permiso '{perm}'")
        return user
    return _dep


def require_owner(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    """Solo `owner` administra usuarios, roles, contraseñas y sesiones ajenas."""
    user = _authenticated(x_auth_token)
    _assert_password_ok(user)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Solo el owner puede gestionar usuarios y roles")
    return user


def current_user(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    """Dependencia que solo exige un token válido (sin chequear permiso concreto).
    Con contraseña temporal pendiente de cambio responde 403."""
    user = _authenticated(x_auth_token)
    _assert_password_ok(user)
    return user


def current_user_pending_ok(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    """Única excepción a la contraseña temporal: /api/me, /api/me/password y /api/logout."""
    return _authenticated(x_auth_token)
