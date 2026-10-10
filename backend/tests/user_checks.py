"""Gestión de usuarios y credenciales individuales del panel (plan campañas y usuarios §5)."""
import argparse
import hashlib
import io
import os
import threading
from unittest.mock import patch

from core import auth, db, rate_limit, users


def user_checks(client, owner_headers):
    secrets_seen: list[str] = []

    def login(email, password=None, code=None):
        rate_limit._BUCKETS.clear()
        return client.post("/api/login", json={"email": email, "password": password, "code": code})

    def hdr(token):
        return {"X-Auth-Token": token}

    def static_user(email, role):
        if not auth.user_from_email(email):
            auth.create_user(email, email.split("@")[0], role, token=f"tok-{email}")
        return hdr(f"tok-{email}")

    # 1) Hash de contraseña: scrypt con sal, verificación constante, corrupto nunca abre.
    h1, h2 = auth.hash_password("Clave-larga-123"), auth.hash_password("Clave-larga-123")
    assert h1.startswith("scrypt$") and h1 != h2 and "Clave" not in h1
    assert auth.verify_password("Clave-larga-123", h1) and not auth.verify_password("Clave-larga-124", h1)
    assert not auth.verify_password("x", "garbage") and not auth.verify_password("", h1)

    # 2) Solo owner gestiona usuarios (backend): admin lee pero no crea; agent ni lee.
    admin_h = static_user("admin-u@test", "admin")
    agent_h = static_user("agent-u@test", "agent")
    new_user = {"email": "Nueva@Test.com", "name": "Nueva Persona", "role": "agent",
                "access_scope": {"channels": ["telegram"]}}
    assert client.get("/api/admin/users", headers=admin_h).status_code == 200
    assert client.post("/api/admin/users", json=new_user, headers=admin_h).status_code == 403
    assert client.post("/api/admin/users", json=new_user, headers=agent_h).status_code == 403
    assert client.get("/api/admin/users", headers=agent_h).status_code == 403
    assert client.post("/api/admin/users/agent-u@test/deactivate", headers=admin_h).status_code == 403
    assert client.put("/api/admin/users/agent-u@test/scope", json={"channels": []}, headers=admin_h).status_code == 403
    assert client.patch("/api/admin/users/admin-u@test", json={"role": "owner"}, headers=admin_h).status_code == 403

    r = client.post("/api/admin/users", json=new_user, headers=owner_headers)
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]
    secrets_seen.append(temp)
    created = r.json()["user"]
    assert created["email"] == "nueva@test.com" and created["must_change_password"] and created["has_password"]
    assert created["access_scope"]["channels"] == ["telegram"] and "token" not in created
    assert client.post("/api/admin/users", json=new_user, headers=owner_headers).status_code == 409
    for bad in ({**new_user, "email": "otra@test", "role": "superuser"}, {**new_user, "email": "sin-arroba"},
                {**new_user, "email": "otra@test", "password": "corta"},
                {**new_user, "email": "otra@test", "access_scope": {"channels": ["fax"]}}):
        assert client.post("/api/admin/users", json=bad, headers=owner_headers).status_code == 422, bad
    assert not auth.user_from_email("otra@test"), "una validación fallida no deja el usuario creado"

    # 3) Login con la temporal: sesión opaca guardada solo como hash; obliga a cambiarla.
    assert login("nueva@test.com", "contraseña-incorrecta").status_code == 401
    r = login("NUEVA@test.com", temp)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    secrets_seen.append(tok)
    assert tok.startswith("s.") and r.json()["user"]["must_change_password"]
    with db.connect() as con:
        hashes = [row["token_hash"] for row in con.execute("SELECT token_hash FROM panel_sessions").fetchall()]
        stored_hash = con.execute("SELECT password_hash FROM panel_users WHERE email='nueva@test.com'").fetchone()[0]
    assert tok not in hashes and hashlib.sha256(tok.encode()).hexdigest() in hashes
    assert temp not in stored_hash and stored_hash.startswith("scrypt$")
    assert client.get("/api/me", headers=hdr(tok)).status_code == 200
    r = client.get("/api/conversations", headers=hdr(tok))
    assert r.status_code == 403 and "contraseña" in r.json()["detail"]
    # Hasta cambiarla solo funcionan /api/me, /api/me/password y /api/logout (servidor).
    assert client.post("/api/presence", json={"status": "available"}, headers=hdr(tok)).status_code == 403
    assert client.get("/api/admin/users", headers=hdr(tok)).status_code == 403

    # 4) Cambio de contraseña: exige la actual; revoca las otras sesiones y conserva la actual.
    other = login("nueva@test.com", temp).json()["token"]
    new_pw = "Nueva-clave-segura-1"
    secrets_seen.append(new_pw)
    bad = client.post("/api/me/password", json={"current_password": "no-es", "new_password": new_pw}, headers=hdr(tok))
    assert bad.status_code == 403, bad.text
    weak = client.post("/api/me/password", json={"current_password": temp, "new_password": "aaaaaaaaaaaa"}, headers=hdr(tok))
    assert weak.status_code == 422, weak.text
    r = client.post("/api/me/password", json={"current_password": temp, "new_password": new_pw}, headers=hdr(tok))
    assert r.status_code == 200 and not r.json()["user"]["must_change_password"], r.text
    assert client.get("/api/conversations", headers=hdr(tok)).status_code == 200
    assert client.get("/api/me", headers=hdr(other)).status_code == 401, "las otras sesiones se revocan"
    assert login("nueva@test.com", temp).status_code == 401
    assert login("nueva@test.com", new_pw).status_code == 200

    # 5) El alcance sigue aplicando con sesiones nuevas (canal telegram solamente).
    wa = db.get_or_create_conversation("wa:51977700001", "whatsapp", connection_id="conn-u")
    assert client.get(f"/api/conversations/{wa}", headers=hdr(tok)).status_code == 403
    r = client.patch("/api/admin/users/nueva@test.com", headers=owner_headers,
                     json={"name": "Nueva Editada", "access_scope": {"channels": ["whatsapp"]}})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Nueva Editada", r.text
    assert client.get(f"/api/conversations/{wa}", headers=hdr(tok)).status_code == 200

    # 6) Logout revoca solo esa sesión; "cerrar sesiones" del owner revoca todas.
    s2 = login("nueva@test.com", new_pw).json()["token"]
    assert client.post("/api/logout", headers=hdr(s2)).json()["revoked"] is True
    assert client.get("/api/me", headers=hdr(s2)).status_code == 401
    assert client.get("/api/me", headers=hdr(tok)).status_code == 200
    s3 = login("nueva@test.com", new_pw).json()["token"]
    r = client.post("/api/admin/users/nueva@test.com/revoke-sessions", headers=owner_headers)
    assert r.status_code == 200 and r.json()["revoked"] >= 2, r.text
    assert all(client.get("/api/me", headers=hdr(t)).status_code == 401 for t in (tok, s3))

    # 7) Desactivar bloquea login, sesiones y token estático al instante; reactivar devuelve el acceso.
    tok = login("nueva@test.com", new_pw).json()["token"]
    static_h = static_user("estatico@test", "agent")
    assert client.get("/api/me", headers=static_h).status_code == 200
    for email in ("nueva@test.com", "estatico@test"):
        r = client.post(f"/api/admin/users/{email}/deactivate", headers=owner_headers)
        assert r.status_code == 200 and r.json()["user"]["active"] is False, r.text
    assert client.get("/api/me", headers=hdr(tok)).status_code == 401
    assert client.get("/api/me", headers=static_h).status_code == 401
    assert login("nueva@test.com", new_pw).status_code == 401
    assert "estatico@test" not in {u["email"] for u in auth.list_advisors()}
    assert client.post(f"/api/conversations/{wa}/assign", json={"email": "estatico@test"},
                       headers=owner_headers).status_code == 422
    assert client.post("/api/admin/users/nueva@test.com/reactivate", headers=owner_headers).status_code == 200
    assert client.get("/api/me", headers=hdr(tok)).status_code == 401, "reactivar no revive sesiones revocadas"
    assert login("nueva@test.com", new_pw).status_code == 200

    # 8) Reset por el owner: temporal nueva, cierra sesiones, obliga a cambiarla.
    tok = login("nueva@test.com", new_pw).json()["token"]
    r = client.post("/api/admin/users/nueva@test.com/password-reset", json={}, headers=owner_headers)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"], r.text
    temp2 = r.json()["temporary_password"]
    secrets_seen.append(temp2)
    assert client.get("/api/me", headers=hdr(tok)).status_code == 401
    assert login("nueva@test.com", new_pw).status_code == 401
    r = login("nueva@test.com", temp2)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"], r.text
    assert client.get("/api/conversations", headers=hdr(r.json()["token"])).status_code == 403
    # Contraseña fijada por el owner: también temporal (el owner la conoce).
    owner_pw = "Fijada-por-owner-9"
    secrets_seen.append(owner_pw)
    r = client.post("/api/admin/users/nueva@test.com/password-reset", json={"password": owner_pw}, headers=owner_headers)
    assert r.status_code == 200 and r.json()["temporary_password"] is None and r.json()["user"]["must_change_password"]
    assert "password_hash" not in r.text and "scrypt$" not in r.text and "token" not in r.json()["user"]
    t4 = login("nueva@test.com", owner_pw).json()["token"]
    assert client.get("/api/conversations", headers=hdr(t4)).status_code == 403
    assert client.post("/api/me/password", headers=hdr(t4),
                       json={"current_password": owner_pw, "new_password": new_pw}).status_code == 200
    assert client.get("/api/conversations", headers=hdr(t4)).status_code == 200
    listing = client.get("/api/admin/users", headers=owner_headers).text
    assert "password_hash" not in listing and "scrypt$" not in listing and "tok-" not in listing

    # 9) Último owner activo: no se degrada ni se desactiva, tampoco con peticiones concurrentes.
    owner_email = client.get("/api/me", headers=owner_headers).json()["email"]
    with db.connect() as con:
        others = [row["id"] for row in con.execute(
            "SELECT id FROM panel_users WHERE role='owner' AND active=1 AND email<>?", (owner_email,)).fetchall()]
        owner_static = con.execute("SELECT token FROM panel_users WHERE email=?", (owner_email,)).fetchone()[0]
    try:
        with db.connect() as con:
            for uid in others:
                con.execute("UPDATE panel_users SET active=0 WHERE id=?", (uid,))
        r = client.post("/api/admin/users", headers=owner_headers, json={
            "email": "jefa@test", "name": "Jefa", "role": "owner", "password": "Jefa-clave-segura-1"})
        assert r.status_code == 200, r.text
        assert client.patch("/api/admin/users/jefa@test", json={"role": "admin"},
                            headers=owner_headers).status_code == 200
        r = client.patch(f"/api/admin/users/{owner_email}", json={"role": "admin"}, headers=owner_headers)
        assert r.status_code == 409, r.text
        assert client.post(f"/api/admin/users/{owner_email}/deactivate", headers=owner_headers).status_code == 422
        try:
            users.set_active({"email": "otro@test"}, owner_email, False)
            raise AssertionError("se desactivó al último owner")
        except users.LastOwnerError:
            pass
        assert client.patch("/api/admin/users/jefa@test", json={"role": "owner"},
                            headers=owner_headers).status_code == 200

        for attempt in ("deactivate", "demote"):
            barrier, results = threading.Barrier(2), {}

            def run(actor, target, attempt=attempt, barrier=barrier, results=results):
                barrier.wait()
                try:
                    if attempt == "deactivate":
                        users.set_active({"email": actor}, target, False)
                    else:
                        users.update({"email": actor}, target, role="admin")
                    results[target] = "ok"
                except users.LastOwnerError:
                    results[target] = "last_owner"

            threads = [threading.Thread(target=run, args=("jefa@test", owner_email)),
                       threading.Thread(target=run, args=(owner_email, "jefa@test"))]
            [t.start() for t in threads]
            [t.join(30) for t in threads]
            assert sorted(results.values()) == ["last_owner", "ok"], (attempt, results)
            with db.connect() as con:
                n = con.execute("SELECT COUNT(*) FROM panel_users WHERE role='owner' AND active=1").fetchone()[0]
            assert n == 1, (attempt, n)
            # Restaurar ambos owners activos para el siguiente intento.
            with db.connect() as con:
                con.execute("UPDATE panel_users SET role='owner', active=1, deactivated_at=NULL "
                            "WHERE email IN (?,?)", (owner_email, "jefa@test"))
        users.set_active({"email": owner_email}, "jefa@test", False)
    finally:
        with db.connect() as con:
            con.execute("UPDATE panel_users SET role='owner', active=1, deactivated_at=NULL, token=? WHERE email=?",
                        (owner_static, owner_email))
            for uid in others:
                con.execute("UPDATE panel_users SET active=1 WHERE id=?", (uid,))
    assert client.get("/api/me", headers=owner_headers).status_code == 200

    # 10) Owner heredado sin contraseña: entra con PANEL_LOGIN_CODE hasta fijar una (manage.py).
    env_keys = ("PANEL_LOGIN_CODE", "APP_ENV", "PANEL_ADMIN_EMAIL", "PANEL_ADMIN_TOKEN")
    saved = {k: os.environ.get(k) for k in env_keys}
    try:
        os.environ.update({"PANEL_ADMIN_EMAIL": "legado@test", "PANEL_ADMIN_TOKEN": "tok-legado-env",
                           "PANEL_LOGIN_CODE": "codigo-compartido-1"})
        auth.ensure_seed()
        legacy = auth.user_from_email("legado@test")
        assert legacy and legacy["role"] == "owner" and not legacy["has_password"]
        assert client.get("/api/me", headers=hdr("tok-legado-env")).status_code == 200
        assert client.get("/api/login/options").json()["legacy_code"] is True
        assert login("legado@test").status_code == 401
        assert login("legado@test", code="otro-codigo").status_code == 401
        r = login("legado@test", code="codigo-compartido-1")
        assert r.status_code == 200 and r.json()["token"].startswith("s."), r.text
        legacy_session = r.json()["token"]
        # El código no sirve para usuarios que ya tienen contraseña.
        assert login("nueva@test.com", code="codigo-compartido-1").status_code == 401

        import manage  # noqa: PLC0415
        legacy_pw = "Legado-clave-segura-1"
        secrets_seen.append(legacy_pw)
        with patch("sys.stdin", io.StringIO(legacy_pw + "\n")):
            manage.cmd_set_password(argparse.Namespace(email="legado@test", password_stdin=True, temporary=False))
        assert login("legado@test", code="codigo-compartido-1").status_code == 401
        assert login("legado@test", legacy_pw).status_code == 200
        assert client.get("/api/me", headers=hdr(legacy_session)).status_code == 401
        assert client.get("/api/me", headers=hdr("tok-legado-env")).status_code == 401, "token estático invalidado"

        # Producción sin código: un usuario sin contraseña no entra ni desde localhost.
        os.environ["PANEL_LOGIN_CODE"] = ""
        os.environ["APP_ENV"] = "production"
        assert client.get("/api/login/options").json() == {"password": True, "legacy_code": False, "dev_local": False}
        assert login("agent-u@test").status_code == 401
        os.environ["APP_ENV"] = "development"
        assert login("agent-u@test").status_code == 200, "desarrollo local sigue igual"
    finally:
        for k, v in saved.items():
            os.environ[k] = v if v is not None else ""
        with db.connect() as con:
            con.execute("UPDATE panel_users SET active=0, token=? WHERE email='legado@test'", (auth._disabled_token(),))

    # 11) Intentos fallidos: auditados sin secretos y limitados por IP.
    rate_limit._BUCKETS.clear()
    codes = [client.post("/api/login", json={"email": "nadie@test", "password": "x" * 12}).status_code
             for _ in range(12)]
    assert codes[0] == 401 and codes[-1] == 429, codes
    rate_limit._BUCKETS.clear()

    with db.connect() as con:
        events = [dict(row) for row in con.execute(
            "SELECT actor, action, resource, metadata FROM audit_events "
            "WHERE action LIKE 'user.%' OR action LIKE 'auth.%'").fetchall()]
    actions = {e["action"] for e in events}
    assert {"user.create", "user.update", "user.deactivate", "user.reactivate", "user.password_reset",
            "user.sessions_revoked", "user.password_changed", "user.password_set", "auth.login",
            "auth.login_failed"} <= actions, actions
    dump = repr(events)
    assert all(s not in dump for s in secrets_seen) and "scrypt$" not in dump, "auditoría con secretos"
    assert any(e["action"] == "user.update" and "Nueva Editada" in (e["metadata"] or "") for e in events)
    owner_actor = client.get("/api/me", headers=owner_headers).json()["email"]
    assert all(e["actor"] == owner_actor for e in events
               if e["action"] in {"user.create", "user.deactivate", "user.password_reset"} and e["resource"] == "user:nueva@test.com")
