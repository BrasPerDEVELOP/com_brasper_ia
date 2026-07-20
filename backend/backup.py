"""Backups y restore para la plataforma.

Postgres: usa pg_dump/pg_restore via DATABASE_URL.
SQLite local/tests: copia el archivo backend/data/plataforma.db.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from core import db

BACKUP_DIR = Path(__file__).resolve().parent / "backups"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _database_url() -> str | None:
    return db.database_url()


def _is_postgres(url: str | None) -> bool:
    return bool(url and not url.startswith("sqlite:"))


def _ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise RuntimeError(f"Falta '{name}'. En Docker se instala con postgresql-client.")


def create_backup(out_dir: str | Path | None = None) -> Path:
    out = Path(out_dir) if out_dir else BACKUP_DIR
    out.mkdir(parents=True, exist_ok=True)
    url = _database_url()
    if _is_postgres(url):
        _ensure_tool("pg_dump")
        path = out / f"cauce-postgres-{_stamp()}.dump"
        subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(path), url], check=True)
        return path

    source = db.DB_PATH
    if not source.exists():
        raise RuntimeError(f"No existe DB SQLite local: {source}")
    path = out / f"cauce-sqlite-{_stamp()}.db"
    shutil.copy2(source, path)
    return path


def restore_backup(path: str | Path, yes: bool = False) -> None:
    backup = Path(path)
    if not backup.exists():
        raise RuntimeError(f"No existe backup: {backup}")
    if not yes:
        raise RuntimeError("Restore requiere --yes para evitar ejecuciones accidentales")
    url = _database_url()
    if _is_postgres(url):
        _ensure_tool("pg_restore")
        subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", url, str(backup)], check=True)
        return
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, db.DB_PATH)


def list_backups(out_dir: str | Path | None = None) -> list[Path]:
    out = Path(out_dir) if out_dir else BACKUP_DIR
    if not out.exists():
        return []
    return sorted([p for p in out.iterdir() if p.is_file()], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backups/restore Cauce")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="crear backup")
    create.add_argument("--out-dir", default=None)

    restore = sub.add_parser("restore", help="restaurar backup")
    restore.add_argument("path")
    restore.add_argument("--yes", action="store_true")

    listed = sub.add_parser("list", help="listar backups")
    listed.add_argument("--out-dir", default=None)

    args = parser.parse_args()
    try:
        if args.cmd == "create":
            path = create_backup(args.out_dir)
            print(path)
        elif args.cmd == "restore":
            restore_backup(args.path, yes=args.yes)
            print("[restore] aplicado")
        elif args.cmd == "list":
            for path in list_backups(args.out_dir):
                print(path)
    except Exception as e:  # noqa: BLE001 - CLI debe mostrar mensaje claro
        print(f"[backup] error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
