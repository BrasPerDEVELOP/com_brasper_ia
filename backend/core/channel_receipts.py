"""Provider message IDs distinguish our own echoes from human app activity."""
from . import db, util


def ensure_schema():
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS channel_receipts (connection_id TEXT NOT NULL, "
                    "message_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(connection_id,message_id))")


def remember(connection_id, message_id):
    if not connection_id or not message_id:
        return
    with db.connect() as con:
        con.execute("INSERT INTO channel_receipts VALUES (?,?,?) ON CONFLICT(connection_id,message_id) DO NOTHING",
                    (connection_id, message_id, util.now_iso()))


def is_own(connection_id, message_id):
    if not connection_id or not message_id:
        return False
    with db.connect() as con:
        return bool(con.execute("SELECT 1 FROM channel_receipts WHERE connection_id=? AND message_id=?",
                                (connection_id, message_id)).fetchone())
