"""Autenticación simple por token + RBAC para el panel interno (modelo agencia).

Modelo actual: sin passwords. El login es por email (usuarios gestionados por el
equipo, no auto-registro). Cada usuario tiene un token opaco que el frontend guarda en
localStorage y envía en el header 'X-Auth-Token'.

Esquema propio (gestionado aquí, no en core/db.py):
  panel_users(id, email UNIQUE, name, role, tenant_scope, token)
    - tenant_scope NULL  -> usuario de agencia: ve TODOS los tenants.
    - tenant_scope='brasper' -> scoped a ese cliente.

RBAC: matriz {rol: [permisos]}. Un permiso es una cadena 'recurso:accion'
(o 'recurso:*' para comodín sobre el recurso). El comodín global '*' da todo.

Gating opt-in: los endpoints existentes NO cambian. Para proteger uno nuevo:
    from core import auth
    @router.get("/api/algo", dependencies=[Depends(auth.require("usage:read"))])
o para leer el usuario dentro del handler:
    def handler(user: dict = Depends(auth.require("usage:read"))): ...
"""
import os
import secrets

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
        "conversations:read", "conversations:write",
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
        "conversations:read", "conversations:write",
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
"""


def ensure_schema() -> None:
    with db.connect() as con:
        con.executescript(_POSTGRES_SCHEMA if db.is_postgres() else _SQLITE_SCHEMA)


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


def _seed_prod_admin(con) -> None:
    """Crea/actualiza el owner de producción desde variables de entorno.

    Requiere PANEL_ADMIN_EMAIL y PANEL_ADMIN_TOKEN. El token NO se genera aquí:
    evitamos imprimir secretos en el log del servidor. Para generar uno usa
    `python manage.py create-admin` (lo muestra una vez en tu terminal).
    Idempotente y tolerante a arranques concurrentes (INSERT OR IGNORE + UPDATE);
    rotar = cambiar PANEL_ADMIN_TOKEN y reiniciar.
    """
    email = normalize_email(os.getenv("PANEL_ADMIN_EMAIL"))
    if not email:
        return
    token = (os.getenv("PANEL_ADMIN_TOKEN") or "").strip()
    if not token:
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
      NO siembra usuarios demo y PURGA cualquier token demo heredado (p.ej. si se
      reutiliza una DB de desarrollo). Fuerza demo solo con SEED_DEMO_USERS=true.
    - Desarrollo (default): siembra los usuarios demo (tokens legibles) para local.
    """
    ensure_schema()
    prod = _is_production()
    seed_demo = _env_true("SEED_DEMO_USERS") or not prod
    with db.connect() as con:
        _seed_prod_admin(con)
        if prod and not seed_demo:
            # Elimina tokens demo predecibles que pudieran venir de una DB de dev.
            placeholders = ",".join("?" * len(_DEMO_TOKENS))
            con.execute(f"DELETE FROM panel_users WHERE token IN ({placeholders})", _DEMO_TOKENS)
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
# Consultas / autenticación
# ---------------------------------------------------------------------------
def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "token": row["token"],
    }


def list_advisors() -> list[dict]:
    """Asesores (rol 'agent') que pueden atender."""
    try:
        with db.connect() as con:
            rows = con.execute(
                "SELECT * FROM panel_users WHERE role='agent' ORDER BY id"
            ).fetchall()
    except Exception:  # noqa: BLE001 - tabla aún no creada: sin asesores, no rompe el handoff
        return []
    return [_row_to_user(r) for r in rows]


def pick_advisor() -> dict | None:
    """Derivación: elige el asesor con menos conversaciones en handoff activas."""
    advisors = list_advisors()
    if not advisors:
        return None
    load = db.handoff_load_by_agent()
    return min(advisors, key=lambda u: (load.get(u["email"], 0), u["id"]))


def derive_to_advisor(conversation_id: str) -> str | None:
    """Asigna la conversación al asesor con menos carga y devuelve su email (o None).

    Usado por el handoff del grafo y por la recepción de comprobantes (Telegram/
    WhatsApp): un solo punto de derivación para todo el sistema (DRY)."""
    advisor = pick_advisor()
    if advisor:
        try:
            db.assign_conversation(conversation_id, advisor["email"])
        except Exception:  # noqa: BLE001 - asignación best-effort, no rompe el flujo
            return None
        return advisor["email"]
    return None


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM panel_users WHERE token=?", (token,)).fetchone()
    return _row_to_user(row) if row else None


def user_from_email(email: str | None) -> dict | None:
    if not email:
        return None
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM panel_users WHERE email=?", (normalize_email(email),)).fetchone()
    return _row_to_user(row) if row else None


def login(email: str, code: str | None = None, local_request: bool = False) -> dict | None:
    """Login del panel controlado por código.

    - PANEL_LOGIN_CODE definido: `code` debe coincidir (comparación constante).
    - Sin PANEL_LOGIN_CODE: solo se permite en DESARROLLO desde localhost. En
      producción (APP_ENV=production) el login SIEMPRE exige el código, sin atajo
      por IP — así un reverse proxy que haga parecer local la conexión no bypasea.
    """
    required_code = (os.getenv("PANEL_LOGIN_CODE") or "").strip() or None
    if required_code:
        code = (code or "").strip()
        if not code or not secrets.compare_digest(code, required_code):
            return None
    elif not (local_request and not _is_production()):
        return None

    user = user_from_email(email)
    if not user:
        return None
    return {"token": user["token"], "user": _public_user(user)}


def _public_user(user: dict) -> dict:
    """Vista del usuario sin el token, con permisos efectivos (para /api/me y login)."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "permissions": permissions_for(user),
    }


def create_user(email: str, name: str, role: str,
                token: str | None = None) -> dict:
    """Alta de usuario (gestión interna). Genera token opaco si no se pasa uno."""
    if role not in ROLE_PERMS:
        raise ValueError(f"Rol desconocido: {role!r}")
    token = token or secrets.token_urlsafe(24)
    with db.connect() as con:
        con.execute(
            "INSERT INTO panel_users (email, name, role, token) "
            "VALUES (?,?,?,?)",
            (normalize_email(email), name, role, token))
        row = con.execute("SELECT * FROM panel_users WHERE email=?", (normalize_email(email),)).fetchone()
    return _row_to_user(row)


# ---------------------------------------------------------------------------
# Dependencia FastAPI (gating opt-in)
# ---------------------------------------------------------------------------
def require(perm: str):
    """Dependencia que exige un permiso.

    401 si falta/invalida el token; 403 si el token es válido pero sin permiso.
    Devuelve el dict del usuario autenticado al handler.
    """
    def _dep(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
        user = user_from_token(x_auth_token)
        if not user:
            raise HTTPException(status_code=401, detail="Token ausente o inválido")
        if not has_perm(user, perm):
            raise HTTPException(
                status_code=403,
                detail=f"Rol '{user['role']}' no tiene el permiso '{perm}'")
        return user
    return _dep


def current_user(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    """Dependencia que solo exige un token válido (sin chequear permiso concreto)."""
    user = user_from_token(x_auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Token ausente o inválido")
    return user
