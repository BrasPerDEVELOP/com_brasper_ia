"""Cuenta de servicio hacia la API con AUTH_REQUIRED=true (JWT + secreto), sin red."""
import os
from unittest.mock import patch

import httpx

from core import brasper_api, tenants


def service_auth_checks():
    calls = []
    state = {"valid": {"jwt-1"}, "issued": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.url.path == "/auth/login":
            body = request.read().decode()
            if '"password": "synthetic-pass"' not in body.replace('":"', '": "'):
                return httpx.Response(401, json={"detail": "bad"})
            state["issued"] += 1
            token = f"jwt-{state['issued']}"
            state["valid"].add(token)
            return httpx.Response(200, json={"access_token": token})
        auth = (request.headers.get("authorization") or "").removeprefix("Bearer ")
        if auth not in state["valid"]:
            return httpx.Response(401, json={"detail": "Invalid or expired token"}, headers={"WWW-Authenticate": "Bearer"})
        if request.headers.get("x-brasper-ia-secret") != "synthetic-secret":
            return httpx.Response(401, json={"detail": "secreto"})
        if request.url.path.endswith("/redeem"):
            return httpx.Response(401, json={"detail": "Vínculo inválido"})  # 401 de la ruta: sin WWW-Authenticate
        return httpx.Response(200, json={"found": False})

    real_client = httpx.Client

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    tenant = tenants.get_config()
    env = {"BRASPER_IA_SERVICE_USERNAME": "svc-ia@test", "BRASPER_IA_SERVICE_PASSWORD": "synthetic-pass",
           "BRASPER_IA_SHARED_SECRET": "synthetic-secret"}
    brasper_api._service.update(token=None, expires=0.0, retry_after=0.0)
    with patch.dict(os.environ, env), patch.object(brasper_api.httpx, "Client", side_effect=client):
        # 1) Login una vez, Bearer + secreto en cada llamada, token reutilizado.
        assert brasper_api.find_client(tenant, phone="987654321", code_phone="+51")["ok"]
        assert brasper_api.find_client(tenant, phone="987654322", code_phone="+51")["ok"]
        assert [c[1] for c in calls].count("/auth/login") == 1
        assert all(c[2] == "Bearer jwt-1" for c in calls if c[1] != "/auth/login")

        # 2) Token revocado en la API: 401 del middleware -> un único re-login y reintento.
        state["valid"].discard("jwt-1")
        calls.clear()
        assert brasper_api.find_client(tenant, phone="987654323", code_phone="+51")["ok"]
        assert [c[1] for c in calls] == ["/brasper/ai/clients/lookup", "/auth/login", "/brasper/ai/clients/lookup"]

        # 3) Un 401 de la propia ruta (código inválido) no provoca re-login ni segundo canje.
        calls.clear()
        res = brasper_api.redeem_identity_link(tenant, channel="telegram", subject="tg:1", link_token="a" * 43)
        assert res["status"] == 401 and [c[1] for c in calls] == ["/brasper/ai/identity-links/redeem"]

        # 4) Sesión de servicio rechazada: no se confunde con «código inválido» (status None, sin revocar grants).
        state["valid"].clear()
        with patch.dict(os.environ, {"BRASPER_IA_SERVICE_PASSWORD": "wrong"}):
            brasper_api._service.update(token=None, expires=0.0, retry_after=0.0)
            res = brasper_api.redeem_identity_link(tenant, channel="telegram", subject="tg:1", link_token="a" * 43)
            assert res["ok"] is False and res.get("status") is None, res
            res = brasper_api.linked_operations(tenant, "00000000-0000-4000-8000-000000000001", "g", "telegram", "tg:1")
            assert res.get("status") != 401, "el bot no debe borrar el grant por un fallo de su propia sesión"
            logins = [c[1] for c in calls].count("/auth/login")
            brasper_api.find_client(tenant, phone="987654325", code_phone="+51")
            assert [c[1] for c in calls].count("/auth/login") == logins, "backoff: sin re-login inmediato"

    # 5) Sin credenciales de servicio (desarrollo / AUTH_REQUIRED=false): no se envía Authorization.
    calls.clear()
    brasper_api._service.update(token=None, expires=0.0, retry_after=0.0)
    with patch.dict(os.environ, {"BRASPER_IA_SHARED_SECRET": "synthetic-secret", "BRASPER_IA_SERVICE_USERNAME": "",
                                 "BRASPER_IA_SERVICE_PASSWORD": ""}), \
         patch.object(brasper_api.httpx, "Client", side_effect=client):
        brasper_api.find_client(tenant, phone="987654324", code_phone="+51")
    assert calls and all(c[2] is None for c in calls) and "/auth/login" not in [c[1] for c in calls]
