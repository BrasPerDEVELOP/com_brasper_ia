"""CLI de administracion y bootstrap de produccion.

Ejecutar desde backend/ con el venv del repo:

    ../.venv/bin/python manage.py init
        Crea el esquema (tablas) y ejecuta el seed respetando las variables de
        entorno (PANEL_ADMIN_EMAIL, SEED_DEMO_USERS...). Idempotente.

    ../.venv/bin/python manage.py migrate
        Ejecuta Alembic hasta head usando DATABASE_URL.

    ../.venv/bin/python manage.py create-admin --email a@b.com --name "Nombre" [--token XXX]
        Crea un owner con token seguro (o rota el token si el email ya existe).
        Imprime el token una vez. Sin --token, se genera uno.

    ../.venv/bin/python manage.py set-password --email a@b.com [--password-stdin] [--temporary]
        Fija la contraseña individual de un usuario (se pide oculta; nunca por argumento).
        Revoca sus sesiones e invalida su token estático. Con --temporary obliga a cambiarla.

    ../.venv/bin/python manage.py list-users        # usuarios del panel (estado, sin secretos)
    ../.venv/bin/python manage.py list-tenants       # clientes desde DB o config/tenants.json

En producción, el arranque de la app (main.py) ya llama a init automáticamente;
este CLI sirve para bootstrap manual, crear/rotar admins y diagnosticar.
"""
import argparse
import getpass
import secrets
import sys
from pathlib import Path

from core import auth, db
from core import tenants as T
from core.util import normalize_email

BACKEND_DIR = Path(__file__).resolve().parent


def _mask(token: str) -> str:
    return token[:4] + "…" + token[-4:] if len(token) > 10 else "••••"


def cmd_init(_args) -> None:
    db.init_db()
    auth.ensure_schema()
    auth.ensure_seed()
    print("[init] esquema creado y seed aplicado.")
    cmd_list_users(_args)


def cmd_migrate(_args) -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as e:
        raise SystemExit("Alembic no esta instalado. Ejecuta: pip install -r ../requirements.txt") from e
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    print("[migrate] Alembic upgrade head aplicado.")


def cmd_create_admin(args) -> None:
    email = normalize_email(args.email)
    name = args.name or "Administrador"
    token = args.token or secrets.token_urlsafe(32)
    auth.ensure_schema()
    existing = auth.user_from_email(email)
    if existing:
        # Recuperación de acceso: también reactiva la cuenta si estaba desactivada.
        with db.connect() as con:
            con.execute("UPDATE panel_users SET token=?, role='owner', name=?, active=1, deactivated_at=NULL "
                        "WHERE email=?", (token, name, email))
        db.add_audit_event("manage.py", "user.admin_recovered", f"user:{email}", {"role": "owner"})
        print(f"[create-admin] admin '{email}' actualizado (rol=owner, activo, token rotado).")
    else:
        auth.create_user(email, name, "owner", token=token)
        print(f"[create-admin] admin '{email}' creado (rol=owner).")
    print(f"[create-admin] TOKEN (guárdalo, se muestra ahora): {token}")
    print("  Úsalo en el header 'X-Auth-Token'. Para el panel fija una contraseña con:")
    print(f"  python manage.py set-password --email {email}")


def cmd_list_users(_args) -> None:
    db.init_db()
    with db.connect() as con:
        rows = con.execute(
            "SELECT email, role, active, password_hash FROM panel_users ORDER BY id").fetchall()
    if not rows:
        print("  (sin usuarios)")
        return
    print(f"  {'email':32} {'rol':8} {'estado':10} credencial")
    for r in rows:
        state = "activo" if int(r["active"]) else "inactivo"
        cred = "contraseña" if r["password_hash"] else "sin contraseña (compatibilidad)"
        print(f"  {r['email']:32} {r['role']:8} {state:10} {cred}")


def cmd_set_password(args) -> None:
    """Contraseña individual (transición desde PANEL_LOGIN_CODE). Nunca se imprime."""
    db.init_db()
    email = normalize_email(args.email)
    user = auth.user_from_email(email)
    if not user:
        raise SystemExit(f"[set-password] no existe el usuario '{email}'")
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Nueva contraseña: ")
        if getpass.getpass("Repite la contraseña: ") != password:
            raise SystemExit("[set-password] las contraseñas no coinciden")
    try:
        auth.validate_new_password(password, email)
    except ValueError as exc:
        raise SystemExit(f"[set-password] {exc}") from exc
    auth.set_password(user["id"], password, must_change=args.temporary)
    db.add_audit_event("manage.py", "user.password_set", f"user:{email}",
                       {"temporary": bool(args.temporary), "sessions_revoked": True})
    print(f"[set-password] contraseña fijada para '{email}'. Sesiones previas revocadas.")
    if not user["active"]:
        print("  AVISO: la cuenta está desactivada; reactívala desde el panel o con create-admin.")


def cmd_list_tenants(_args) -> None:
    cfg = T.get_config()
    tenants = {"brasper": cfg}
    if not tenants:
        print("  (sin tenants)")
        return
    source = "database" if T.database_tenants_enabled() else "config/tenants.json"
    print(f"  fuente: {source}")
    for tid in tenants:
        t = T.get_config() if tid == "brasper" else None
        if not t:
            print(f"  {tid:16} (inactivo)")
            continue
        chans = []
        if T.whatsapp_token(t) and T.whatsapp_phone_number_id(t):
            chans.append("whatsapp")
        if T.telegram_token(t):
            chans.append("telegram")
        llm_ok = "llm✓" if T.llm_api_key(t) else "llm✗"
        print(f"  {tid:16} {t.get('vertical',''):24} {llm_ok}  canales: {', '.join(chans) or 'webchat'}")


def cmd_import_campaigns(args) -> None:
    """Importación EXPLÍCITA y de solo lectura de campañas del diseño anterior (API financiera).
    Quedan como borrador en IA; no se publica ni se escribe nada en Brasper."""
    import json
    from core import brasper_api, campaigns
    db.init_db()
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            data = json.load(fh)
        rows = data.get("campaigns", data) if isinstance(data, dict) else data
    else:
        result = brasper_api._integration_request(T.get_config(), "GET", "/brasper/ai/admin/campaigns", admin=True)
        if not result.get("ok"):
            print(f"[import-campaigns] no se pudo leer la API ({result.get('error')}); usa --file con una exportación")
            return
        rows = (result.get("data") or {}).get("campaigns", [])
    report = campaigns.import_legacy(rows, args.actor)
    print(f"[import-campaigns] leídas: {len(rows)} · importadas como borrador: {len(report['imported'])}")
    for code in report["imported"]:
        print(f"  + {code}")
    for item in report["skipped"]:
        print(f"  - {item.get('code')}: {item.get('error')}")


def cmd_set_scope(args) -> None:
    """Alcance por canal/número/sector (listas separadas por coma; vacío = sin restricción)."""
    from core import access
    db.init_db()
    split = lambda raw: [v.strip() for v in (raw or "").split(",") if v.strip()]  # noqa: E731
    scope = access.set_scope(args.email, {"channels": split(args.channels),
                                          "connections": split(args.connections), "sectors": split(args.sectors)})
    print(f"[set-scope] {args.email.strip().lower()}: {scope}")


def main() -> int:
    p = argparse.ArgumentParser(description="Bootstrap/administracion del panel")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="crear esquema + seed (respeta env)")
    sub.add_parser("migrate", help="ejecutar Alembic upgrade head")

    ca = sub.add_parser("create-admin", help="crear/rotar un admin owner con token seguro")
    ca.add_argument("--email", required=True)
    ca.add_argument("--name", default=None)
    ca.add_argument("--token", default=None, help="opcional; si falta se genera")

    sc = sub.add_parser("set-scope", help="limitar un usuario a canales/números/sectores")
    sc.add_argument("--email", required=True)
    sc.add_argument("--channels", default="")
    sc.add_argument("--connections", default="")
    sc.add_argument("--sectors", default="")

    sp = sub.add_parser("set-password", help="fijar la contraseña individual de un usuario")
    sp.add_argument("--email", required=True)
    sp.add_argument("--password-stdin", action="store_true", help="leer la contraseña de stdin (sin eco)")
    sp.add_argument("--temporary", action="store_true", help="obligar a cambiarla en el próximo login")

    ic = sub.add_parser("import-campaigns", help="importar campañas del diseño anterior como borradores IA")
    ic.add_argument("--file", default=None, help="JSON exportado ({campaigns:[{draft:{...}}]}); sin él lee la API")
    ic.add_argument("--actor", default="import@manage")

    sub.add_parser("list-users", help="listar usuarios del panel")
    sub.add_parser("list-tenants", help="listar clientes de config/tenants.json")

    args = p.parse_args()
    {
        "init": cmd_init,
        "migrate": cmd_migrate,
        "create-admin": cmd_create_admin,
        "set-scope": cmd_set_scope,
        "set-password": cmd_set_password,
        "import-campaigns": cmd_import_campaigns,
        "list-users": cmd_list_users,
        "list-tenants": cmd_list_tenants,
    }[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
