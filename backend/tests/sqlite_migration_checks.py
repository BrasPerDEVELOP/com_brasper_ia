"""Historical synthetic data survives migrations and SQLite backup/restore."""
import os
from pathlib import Path
import sqlite3
import tempfile


def run():
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    previous = os.environ.get("DATABASE_URL")
    root = Path(tempfile.mkdtemp(prefix="brasper_migration_check_"))
    path = root / "source.db"
    os.environ["DATABASE_URL"] = "sqlite:///" + path.as_posix()
    from alembic import command
    from alembic.config import Config
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    try:
        command.upgrade(config, "0006_lead_data")
        with sqlite3.connect(path) as con:
            con.execute("INSERT INTO conversations (id,tenant_id,channel,user_ref,status,started_at,updated_at) "
                        "VALUES ('synthetic-history','brasper','webchat','synthetic-user','handoff',?,?)", ("2026-10-01T00:00:00+00:00",) * 2)
            con.execute("INSERT INTO messages (conversation_id,tenant_id,role,content,created_at) "
                        "VALUES ('synthetic-history','brasper','user','Synthetic evidence',?)", ("2026-10-01T00:00:00+00:00",))
            # El runtime desplegado creaba public_documents sin índice único: dos borradores simultáneos
            # podían compartir versión. La migración no debe fallar ni borrar ninguno.
            con.execute("CREATE TABLE IF NOT EXISTS public_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL, "
                        "lang TEXT NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL, body_md TEXT NOT NULL, "
                        "status TEXT NOT NULL, author TEXT, created_at TEXT NOT NULL, published_at TEXT, published_by TEXT)")
            # Tabla de ofertas del diseño anterior (8 columnas) con una oferta ya registrada.
            con.execute("CREATE TABLE campaign_offers (subject TEXT NOT NULL, coupon_id TEXT NOT NULL, version INTEGER NOT NULL, "
                        "conversation_id TEXT NOT NULL, language TEXT NOT NULL, asset_id TEXT, asset_version INTEGER, "
                        "offered_at TEXT NOT NULL, PRIMARY KEY(subject, coupon_id, version))")
            con.execute("INSERT INTO campaign_offers VALUES ('contact-1','camp-1',2,'synthetic-history','pt',NULL,NULL,'2026-10-01')")
            for title in ("Synthetic A", "Synthetic B"):
                con.execute("INSERT INTO public_documents (slug,lang,version,title,body_md,status,created_at) "
                            "VALUES ('terminos','es',1,?,'synthetic','draft','2026-10-01')", (title,))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0014_campaign_offers_columns"
            assert con.execute("SELECT status,human_revision FROM conversations WHERE id='synthetic-history'").fetchone() == ("handoff", 0)
            assert con.execute("SELECT content FROM messages WHERE conversation_id='synthetic-history'").fetchone()[0] == "Synthetic evidence"
            assert "tenant_id" not in {c[1] for c in con.execute("PRAGMA table_info(conversations)")}
            assert "contact_id" in {c[1] for c in con.execute("PRAGMA table_info(conversations)")}
            assert sorted(con.execute("SELECT title, version FROM public_documents ORDER BY id").fetchall()) == [
                ("Synthetic A", 1), ("Synthetic B", 2)], "duplicado renumerado, nada borrado"
            con.execute("INSERT INTO secret_rotations (actor, secret_path, env_name, note, rotated_at) "
                        "VALUES ('test','llm','X_ENV',NULL,'2026-10-01')")
            con.execute("INSERT INTO appointments (conversation_id, user_ref, patient_name, document_id, specialty, "
                        "scheduled_for, status, metadata, created_at, updated_at) "
                        "VALUES (NULL,'u','Synthetic',NULL,'x','2026-10-02','scheduled',NULL,'2026-10-01','2026-10-01')")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"contacts", "contact_aliases", "contact_conflicts", "identity_grants", "conversation_locks",
                    "campaigns", "campaign_versions", "campaign_benefits", "first_transfer_claims", "campaign_offers"} <= tables
            assert "panel_sessions" in tables
            assert {"password_hash", "active", "must_change_password"} <= {c[1] for c in con.execute("PRAGMA table_info(panel_users)")}
            legacy = con.execute("SELECT state, delivery_key, updated_at FROM campaign_offers WHERE subject='contact-1'").fetchone()
            assert legacy[0] == "legacy_unverified" and len(legacy[1]) == 40 and legacy[2] == "2026-10-01", legacy
            # El INSERT del código nuevo funciona sobre la tabla reparada y la oferta antigua bloquea un reenvío.
            con.execute("INSERT INTO campaign_offers (subject, coupon_id, version, conversation_id, language, asset_id, "
                        "asset_version, offered_at, delivery_key, state, updated_at) VALUES ('contact-2','camp-1',2,'c','es',"
                        "NULL,NULL,'2026-10-02','k2','prepared','2026-10-02')")
            assert con.execute("INSERT INTO campaign_offers (subject, coupon_id, version, conversation_id, language, offered_at, "
                               "delivery_key, state) VALUES ('contact-1','camp-1',2,'c','pt','x','k','prepared') "
                               "ON CONFLICT(subject, coupon_id, version) DO NOTHING").rowcount == 0
            con.commit()
            with sqlite3.connect(root / "restored.db") as restored:
                con.backup(restored)
                assert restored.execute("SELECT content FROM messages").fetchall() == con.execute("SELECT content FROM messages").fetchall()
                assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        print("PASS: SQLite 0006 to 0014, historical evidence preserved, repeat migration and backup/restore")
    finally:
        if previous is None: os.environ.pop("DATABASE_URL", None)
        else: os.environ["DATABASE_URL"] = previous


if __name__ == "__main__":
    run()
