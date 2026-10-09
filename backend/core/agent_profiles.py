"""Versioned assistant profiles. Style never changes financial calculations."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import db
from .util import now_iso


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60, pattern=r"^[\w .áéíóúÁÉÍÓÚñÑ-]+$")
    tone: Literal["professional", "warm", "concise"] = "professional"
    length: Literal["short", "balanced", "detailed"] = "balanced"
    emoji: Literal["none", "discreet", "natural"] = "discreet"
    languages: list[Literal["es", "pt", "en"]] = Field(default_factory=lambda: ["es", "pt"], min_length=1)
    channels: list[Literal["whatsapp", "telegram", "webchat"]] = Field(
        default_factory=lambda: ["whatsapp", "telegram", "webchat"], min_length=1)
    connection_ids: list[str] = Field(default_factory=list, max_length=30)
    priority: int = Field(default=0, ge=0, le=100)
    capabilities: list[Literal["quote", "onboarding", "deposit", "info", "status", "tool", "calendar", "llm"]] = Field(
        default_factory=lambda: ["quote", "onboarding", "deposit", "info", "status", "tool", "calendar", "llm"])
    knowledge_ids: list[str] = Field(default_factory=list, max_length=200)


class Conflict(ValueError):
    pass


def ensure_schema():
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS agent_profiles (id TEXT PRIMARY KEY, "
                    "latest_version INTEGER NOT NULL, published_version INTEGER, enabled INTEGER NOT NULL DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS agent_profile_versions (profile_id TEXT NOT NULL, "
                    "version INTEGER NOT NULL, payload TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "PRIMARY KEY(profile_id, version))")


def save(profile_id: str, profile: Profile, expected_version: int, actor: str) -> dict:
    if not profile_id or len(profile_id) > 60 or not profile_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Identificador inválido")
    version = expected_version + 1
    with db.connect() as con:
        con.execute("INSERT INTO agent_profiles(id, latest_version) VALUES (?,0) ON CONFLICT(id) DO NOTHING",
                    (profile_id,))
        changed = con.execute("UPDATE agent_profiles SET latest_version=? WHERE id=? AND latest_version=?",
                              (version, profile_id, expected_version))
        if changed.rowcount != 1:
            raise Conflict("El perfil cambió. Recarga antes de guardar.")
        con.execute("INSERT INTO agent_profile_versions VALUES (?,?,?,?,?)",
                    (profile_id, version, profile.model_dump_json(), actor, now_iso()))
    return get(profile_id, version)


def get(profile_id: str, version: int) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT * FROM agent_profile_versions WHERE profile_id=? AND version=?",
                          (profile_id, version)).fetchone()
    if not row:
        raise KeyError("Versión no encontrada")
    return {"id": profile_id, "version": version, "profile": json.loads(row["payload"]),
            "author": row["author"], "created_at": row["created_at"]}


def inventory() -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM agent_profiles ORDER BY id").fetchall()
    return [{**dict(r), "latest": get(r["id"], r["latest_version"])} for r in rows]


def history(profile_id: str) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT version FROM agent_profile_versions WHERE profile_id=? ORDER BY version DESC",
                           (profile_id,)).fetchall()
    return [get(profile_id, r["version"]) for r in rows]


def publish(profile_id: str, version: int):
    get(profile_id, version)
    with db.connect() as con:
        con.execute("UPDATE agent_profiles SET published_version=?, enabled=1 WHERE id=?", (version, profile_id))


def disable(profile_id: str):
    with db.connect() as con:
        if con.execute("UPDATE agent_profiles SET enabled=0 WHERE id=?", (profile_id,)).rowcount != 1:
            raise KeyError("Perfil no encontrado")


def resolve(cid: str, channel: str) -> dict | None:
    """Pin an immutable style version; future edits only affect new selections."""
    lead = db.get_lead_data(cid)
    pinned = lead.get("agent_profile")
    if pinned:
        return get(pinned["id"], pinned["version"])
    connection_id = (db.get_conversation(cid) or {}).get("connection_id")
    candidates = []
    for item in inventory():
        if not item["enabled"] or item["published_version"] is None:
            continue
        version = get(item["id"], item["published_version"])
        p = version["profile"]
        if channel not in p["channels"]:
            continue
        if p["connection_ids"] and connection_id not in p["connection_ids"]:
            continue
        candidates.append(version)
    if not candidates:
        return None
    selected = sorted(candidates, key=lambda p: (-p["profile"]["priority"], p["id"]))[0]
    db.merge_lead_data(cid, {"agent_profile": {"id": selected["id"], "version": selected["version"]}})
    return selected


def prompt(profile: dict, language: str) -> str:
    p = Profile.model_validate(profile)
    tone = {"professional": "profesional, cordial y claro", "warm": "cercano, paciente y empático",
            "concise": "directo, amable y preciso"}[p.tone]
    length = {"short": "breves", "balanced": "con el detalle necesario", "detailed": "detalladas cuando se solicite"}[p.length]
    emojis = {"none": "No uses emojis.", "discreet": "Usa emojis ocasionalmente, como máximo uno por mensaje.",
              "natural": "Usa emojis con moderación y nunca en reclamos delicados."}[p.emoji]
    return (f"Tu nombre de asistente es {p.name}. Identifícate como asistente virtual de Brasper, nunca como humano. "
            f"Mantén un tono {tone} y respuestas {length}. {emojis} "
            "Conversa libremente; pregunta solo datos faltantes, conserva el contexto y permite correcciones. "
            "No vuelvas a presentarte en cada turno. Este estilo no autoriza operaciones ni modifica reglas, "
            "tasas, promociones, cuentas, herramientas o permisos. Usa datos financieros solo de las herramientas. "
            + ("Si el idioma no está cubierto, ofrece continuar en español o portugués sin fingir dominio."
               if language not in p.languages else "Mantén el idioma del cliente."))
