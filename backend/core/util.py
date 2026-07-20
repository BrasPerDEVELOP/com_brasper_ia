"""Utilidades puras compartidas (sin dependencias de otros módulos core).

Centraliza helpers que estaban duplicados entre módulos: timestamp UTC, flag de
producción, parseo de booleanos (desde env o desde config) y normalización de
email y de texto. Mantener este módulo SIN imports de otros `core.*` para evitar
ciclos: solo stdlib.
"""
from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone

_TRUE = {"1", "true", "yes", "on"}


def now_iso() -> str:
    """Timestamp UTC ISO-8601 con precisión de segundos."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_production() -> bool:
    """Producción explícita vía APP_ENV (gobierna seed demo y bypass local de login)."""
    return (os.getenv("APP_ENV") or "").strip().lower() in {"production", "prod", "prd"}


def env_bool(name: str) -> bool:
    """Lee una variable de entorno como booleano ('1','true','yes','on')."""
    return (os.getenv(name) or "").strip().lower() in _TRUE


def as_bool(value) -> bool:
    """Interpreta un valor arbitrario (bool/int/str) como booleano."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    return bool(value)


def normalize_email(email: str | None) -> str:
    """Email canónico: sin espacios y en minúsculas."""
    return (email or "").strip().lower()


def normalize_text(value: str | None, split_underscores: bool = False) -> str:
    """Minúsculas, sin acentos (NFKD) y espacios colapsados.

    split_underscores=True trata '_' como separador de palabras.
    """
    nfkd = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    if split_underscores:
        text = text.replace("_", " ")
    return " ".join(text.split())
