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

    ../.venv/bin/python manage.py list-users        # usuarios del panel (token enmascarado)
    ../.venv/bin/python manage.py list-tenants       # clientes desde DB o config/tenants.json

En producción, el arranque de la app (main.py) ya llama a init automáticamente;
este CLI sirve para bootstrap manual, crear/rotar admins y diagnosticar.
"""
import argparse
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
    T.ensure_store()
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
        with db.connect() as con:
            con.execute("UPDATE panel_users SET token=?, role='owner', name=? WHERE email=?",
                        (token, name, email))
        print(f"[create-admin] admin '{email}' actualizado (rol=owner, token rotado).")
    else:
        auth.create_user(email, name, "owner", tenant_scope=None, token=token)
        print(f"[create-admin] admin '{email}' creado (rol=owner).")
    print(f"[create-admin] TOKEN (guárdalo, se muestra ahora): {token}")
    print("  Úsalo en el header 'X-Auth-Token', o loguéate con este email + PANEL_LOGIN_CODE.")


def cmd_list_users(_args) -> None:
    auth.ensure_schema()
    with db.connect() as con:
        rows = con.execute(
            "SELECT email, name, role, tenant_scope, token FROM panel_users ORDER BY id").fetchall()
    if not rows:
        print("  (sin usuarios)")
        return
    print(f"  {'email':28} {'rol':8} {'scope':10} token")
    for r in rows:
        scope = r["tenant_scope"] or "(agencia)"
        print(f"  {r['email']:28} {r['role']:8} {scope:10} {_mask(r['token'])}")


def cmd_list_tenants(_args) -> None:
    T.ensure_store()
    tenants = T.all_tenants(include_inactive=True)
    if not tenants:
        print("  (sin tenants)")
        return
    source = "database" if T.database_tenants_enabled() else "config/tenants.json"
    print(f"  fuente: {source}")
    for tid in tenants:
        t = T.get_tenant(tid, include_inactive=True)
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


def main() -> int:
    p = argparse.ArgumentParser(description="Bootstrap/administracion del panel")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="crear esquema + seed (respeta env)")
    sub.add_parser("migrate", help="ejecutar Alembic upgrade head")

    ca = sub.add_parser("create-admin", help="crear/rotar un admin owner con token seguro")
    ca.add_argument("--email", required=True)
    ca.add_argument("--name", default=None)
    ca.add_argument("--token", default=None, help="opcional; si falta se genera")

    sub.add_parser("list-users", help="listar usuarios del panel")
    sub.add_parser("list-tenants", help="listar clientes de config/tenants.json")

    args = p.parse_args()
    {
        "init": cmd_init,
        "migrate": cmd_migrate,
        "create-admin": cmd_create_admin,
        "list-users": cmd_list_users,
        "list-tenants": cmd_list_tenants,
    }[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
