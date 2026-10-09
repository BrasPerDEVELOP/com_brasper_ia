"""Real local PostgreSQL/Redis checks; refuses non-test database targets.

Run through docker-compose.validation.yml. Never imports production dotenv files.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1", "dotenv must be disabled"
url = urlparse(os.environ.get("DATABASE_URL", ""))
assert url.hostname in {"postgres", "127.0.0.1", "localhost"}
assert url.path.startswith("/brasper_test_"), "requires a dedicated synthetic database"
redis_url = urlparse(os.environ.get("REDIS_URL", ""))
assert redis_url.hostname in {"redis", "127.0.0.1", "localhost"} and redis_url.path == "/15"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from alembic.config import Config
from sqlite_migration_checks import run as sqlite_checks
sqlite_checks()
command.upgrade(Config("alembic.ini"), "head")

from core import auth, db, engagement, public_docs, redis_runtime, idempotency
assert db.is_postgres() and db.ping()
db.init_db()
auth.ensure_seed()
assert redis_runtime.ping()
name = redis_runtime.key("validation", "exclusive")
token = redis_runtime.acquire_lock(name, ttl_seconds=5, wait_seconds=0)
assert token and token != "local-no-redis"
assert redis_runtime.acquire_lock(name, wait_seconds=0) is None
redis_runtime.release_lock(name, "wrong-owner")
assert redis_runtime.acquire_lock(name, wait_seconds=0) is None
redis_runtime.release_lock(name, token)
replacement = redis_runtime.acquire_lock(name, wait_seconds=0)
assert replacement
redis_runtime.release_lock(name, replacement)

key = idempotency.make_key("infra", os.urandom(16).hex())
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(lambda _: idempotency.claim_write(key, "synthetic"), range(4)))
assert results.count(True) == 1

latest = public_docs.get_latest("privacidad", "es")
version = latest["version"] if latest else 0
def save(n):
    try:
        return public_docs.save_draft("privacidad", "es", "Synthetic test", f"Synthetic {n}", "test", version)
    except public_docs.Conflict:
        return None
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(save, range(2)))
assert sum(value is not None for value in results) == 1

from fastapi.testclient import TestClient
from main import app
from engagement_checks import run
run(TestClient(app), {"X-Auth-Token": "demo-owner"}, {"X-Auth-Token": "demo-agent-brasper"})
command.upgrade(Config("alembic.ini"), "head")
print("PASS: migrations, real Redis lock ownership, PostgreSQL concurrent claims/documents and engagement")
