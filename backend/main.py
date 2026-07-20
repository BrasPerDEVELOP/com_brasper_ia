"""Plataforma IA multi-tenant — backend.

Ejecutar desde backend/:  ../.venv/bin/python -m uvicorn main:app --port 8002
"""
import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from core import db, auth, tenants, util

app = FastAPI(title="Cauce · Plataforma IA multi-tenant", version="0.2.0")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

_origins = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:8080,http://127.0.0.1:8080",
)
allow_origins = [o.strip() for o in _origins.split(",") if o.strip()]
allow_origin_regex: str | None = None

# En producción solo se permiten dominios reales (criterio §10 del plan): se
# descartan orígenes locales para que un CORS mal configurado no abra el panel.
if util.is_production():
    _local = [o for o in allow_origins if "localhost" in o or "127.0.0.1" in o]
    if _local:
        logging.warning("[cors] ignorando orígenes locales en producción: %s", ", ".join(_local))
        allow_origins = [o for o in allow_origins if o not in _local]
    if not allow_origins:
        logging.warning("[cors] CORS_ALLOW_ORIGINS no tiene dominios reales; configúralo en .env")
else:
    # Desarrollo: permite panel en localhost, 127.0.0.1 o IP de red (ej. 192.168.x.x:3001).
    allow_origin_regex = (
        r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?"
    )

_cors_kwargs: dict = {
    "allow_origins": allow_origins,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if allow_origin_regex:
    _cors_kwargs["allow_origin_regex"] = allow_origin_regex

app.add_middleware(CORSMiddleware, **_cors_kwargs)

db.assert_production_infra()   # fail-fast: en produccion exige Postgres + Redis
db.init_db()
tenants.ensure_store()
auth.ensure_schema()
auth.ensure_seed()
app.include_router(router)
