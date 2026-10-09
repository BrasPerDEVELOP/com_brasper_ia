"""Documentos públicos (privacidad, términos, eliminación de datos) con borrador /
publicación versionada y auditoría, más solicitudes de eliminación de datos.

Las páginas públicas del panel leen SOLO versiones publicadas. El contenido es
Markdown en texto plano; el frontend lo renderiza sin HTML ejecutable.
"""
from __future__ import annotations

import re

from . import db
from .util import now_iso

SLUGS = ("privacidad", "terminos", "eliminacion-de-datos")
LANGS = ("es", "pt")
MAX_BODY = 60_000
_TAG_RE = re.compile(r"<[^>]*>")


class Conflict(ValueError):
    pass


def ensure_schema() -> None:
    pk = "id SERIAL PRIMARY KEY" if db.is_postgres() else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    with db.connect() as con:
        con.execute(
            f"CREATE TABLE IF NOT EXISTS public_documents ({pk}, slug TEXT NOT NULL, lang TEXT NOT NULL, "
            "version INTEGER NOT NULL, title TEXT NOT NULL, body_md TEXT NOT NULL, status TEXT NOT NULL, "
            "author TEXT, created_at TEXT NOT NULL, published_at TEXT, published_by TEXT)"
        )
        con.execute(
            f"CREATE TABLE IF NOT EXISTS deletion_requests ({pk}, contact TEXT NOT NULL, channel TEXT, "
            "detail TEXT, status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, handled_by TEXT, note TEXT)"
        )
        _renumber_duplicate_versions(con.execute)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS public_documents_version ON public_documents(slug,lang,version)")
        con.execute("CREATE TABLE IF NOT EXISTS public_document_heads (slug TEXT NOT NULL, lang TEXT NOT NULL, "
                    "version INTEGER NOT NULL, PRIMARY KEY(slug,lang))")
        con.execute("INSERT INTO public_document_heads(slug,lang,version) "
                    "SELECT slug,lang,MAX(version) FROM public_documents GROUP BY slug,lang "
                    "ON CONFLICT(slug,lang) DO NOTHING")


def _renumber_duplicate_versions(execute) -> int:
    """Versiones repetidas (slug, lang, version) creadas sin lock antes del índice único:
    la fila más antigua conserva su número y las demás pasan al final, sin borrar nada."""
    dups = execute("SELECT slug, lang, version FROM public_documents GROUP BY slug, lang, version "
                   "HAVING COUNT(*) > 1").fetchall()
    moved = 0
    for slug, lang, version in [tuple(r) if not isinstance(r, dict) else (r["slug"], r["lang"], r["version"]) for r in dups]:
        ids = [r[0] if not isinstance(r, dict) else r["id"] for r in execute(
            "SELECT id FROM public_documents WHERE slug=? AND lang=? AND version=? ORDER BY id", (slug, lang, version)).fetchall()]
        for doc_id in ids[1:]:
            top = execute("SELECT MAX(version) FROM public_documents WHERE slug=? AND lang=?", (slug, lang)).fetchone()
            nxt = (top[0] if not isinstance(top, dict) else list(top.values())[0]) + 1
            execute("UPDATE public_documents SET version=? WHERE id=?", (nxt, doc_id))
            moved += 1
    return moved


def _check(slug: str, lang: str) -> None:
    if slug not in SLUGS:
        raise ValueError("slug inválido")
    if lang not in LANGS:
        raise ValueError("lang inválido")


def sanitize(body: str) -> str:
    """Texto/Markdown sin etiquetas HTML (no se acepta HTML ejecutable)."""
    body = (body or "").replace("\r\n", "\n")
    body = _TAG_RE.sub("", body)
    return body[:MAX_BODY]


def _row(r) -> dict:
    d = dict(r)
    for k in ("created_at", "published_at"):
        if d.get(k) is not None and not isinstance(d[k], str):
            d[k] = d[k].isoformat()
    return d


def get_published(slug: str, lang: str) -> dict | None:
    _check(slug, lang)
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM public_documents WHERE slug=? AND lang=? AND status='published' "
            "ORDER BY version DESC LIMIT 1", (slug, lang)).fetchone()
    return _row(row) if row else None


def get_latest(slug: str, lang: str) -> dict | None:
    """Última versión (borrador o publicada) para el editor."""
    _check(slug, lang)
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM public_documents WHERE slug=? AND lang=? ORDER BY version DESC LIMIT 1",
            (slug, lang)).fetchone()
    return _row(row) if row else None


def history(slug: str, lang: str, limit: int = 20) -> list[dict]:
    _check(slug, lang)
    with db.connect() as con:
        rows = con.execute(
            "SELECT id, slug, lang, version, title, status, author, created_at, published_at, published_by "
            "FROM public_documents WHERE slug=? AND lang=? ORDER BY version DESC LIMIT ?",
            (slug, lang, limit)).fetchall()
    return [_row(r) for r in rows]


def save_draft(slug: str, lang: str, title: str, body_md: str, author: str | None,
               expected_version: int | None = None) -> dict:
    _check(slug, lang)
    title = (title or "").strip()[:200]
    body = sanitize(body_md)
    if not title or not body.strip():
        raise ValueError("título y contenido son obligatorios")
    with db.connect() as con:
        con.execute("INSERT INTO public_document_heads(slug,lang,version) VALUES (?,?,0) "
                    "ON CONFLICT(slug,lang) DO NOTHING", (slug, lang))
        query = "UPDATE public_document_heads SET version=version+1 WHERE slug=? AND lang=?"
        params = (slug, lang)
        if expected_version is not None:
            query += " AND version=?"
            params += (expected_version,)
        row = con.execute(query + " RETURNING version", params).fetchone()
        if not row:
            raise Conflict("El documento cambió; recarga antes de guardar")
        version = int(row["version"])
        # Un solo borrador vigente: los anteriores quedan 'superseded'.
        con.execute("UPDATE public_documents SET status='superseded' WHERE slug=? AND lang=? AND status='draft'",
                    (slug, lang))
        con.execute(
            "INSERT INTO public_documents (slug, lang, version, title, body_md, status, author, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (slug, lang, version, title, body, "draft", author, now_iso()))
        result = con.execute("SELECT * FROM public_documents WHERE slug=? AND lang=? AND version=?", (slug, lang, version)).fetchone()
        return _row(result)


def publish(slug: str, lang: str, version: int, actor: str | None) -> dict:
    _check(slug, lang)
    with db.connect() as con:
        # Serialize publication with drafts and other publications on both DBs.
        con.execute("UPDATE public_document_heads SET version=version WHERE slug=? AND lang=?", (slug, lang))
        row = con.execute("SELECT * FROM public_documents WHERE slug=? AND lang=? AND version=?",
                          (slug, lang, int(version))).fetchone()
        if not row:
            raise KeyError("versión no encontrada")
        if row["status"] not in ("draft", "published", "archived"):
            raise ValueError("solo se publica un borrador vigente")
        con.execute("UPDATE public_documents SET status='archived' WHERE slug=? AND lang=? AND status='published'",
                    (slug, lang))
        con.execute("UPDATE public_documents SET status='published', published_at=?, published_by=? "
                    "WHERE slug=? AND lang=? AND version=?", (now_iso(), actor, slug, lang, int(version)))
        result = con.execute("SELECT * FROM public_documents WHERE slug=? AND lang=? AND version=?", (slug, lang, int(version))).fetchone()
        return _row(result)


def overview() -> list[dict]:
    """Estado por documento/idioma para la vista de administración."""
    out = []
    for slug in SLUGS:
        for lang in LANGS:
            pub = get_published(slug, lang)
            latest = get_latest(slug, lang)
            out.append({"slug": slug, "lang": lang,
                        "published_version": pub["version"] if pub else None,
                        "published_at": pub.get("published_at") if pub else None,
                        "draft_version": latest["version"] if latest and latest["status"] == "draft" else None,
                        "title": (latest or pub or {}).get("title"),
                        "public_path": f"/{slug}" + ("" if lang == "es" else f"?lang={lang}")})
    return out


# ---------- solicitudes de eliminación de datos ----------
DELETION_STATUSES = ("received", "verifying", "completed", "rejected")


def create_deletion_request(contact: str, channel: str | None, detail: str | None) -> dict:
    contact = (contact or "").strip()[:200]
    if len(contact) < 5:
        raise ValueError("indica un contacto válido (teléfono o correo)")
    now = now_iso()
    with db.connect() as con:
        row = con.execute(
            "INSERT INTO deletion_requests (contact, channel, detail, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?) RETURNING *", (contact, (channel or "")[:40], sanitize(detail or "")[:2000], "received", now, now)).fetchone()
    return _row(row)


def list_deletion_requests(limit: int = 200) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM deletion_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def set_deletion_status(req_id: int, status: str, actor: str | None, note: str | None = None) -> dict:
    if status not in DELETION_STATUSES:
        raise ValueError("estado inválido")
    with db.connect() as con:
        con.execute("UPDATE deletion_requests SET status=?, handled_by=?, note=?, updated_at=? WHERE id=?",
                    (status, actor, (note or "")[:1000], now_iso(), int(req_id)))
        row = con.execute("SELECT * FROM deletion_requests WHERE id=?", (int(req_id),)).fetchone()
    if not row:
        raise KeyError("solicitud no encontrada")
    return _row(row)
