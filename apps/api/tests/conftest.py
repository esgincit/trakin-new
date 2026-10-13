"""Test setup: a fresh local database built from the real migrations + demo seed, and
signed test tokens for each demo user (HS256, like a Supabase project with a JWT secret).

    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/mytrakin_test pytest
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import jwt
import pytest

ROOT = Path(__file__).resolve().parents[3]
DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/mytrakin_test")
SECRET = "test-secret-at-least-32-characters-long!!"

os.environ.update({
    "DATABASE_URL": DB_URL,
    "ENVIRONMENT": "test",
    "SUPABASE_URL": "",
    "SUPABASE_JWT_SECRET": SECRET,
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "RESEND_API_KEY": "",
    "CRON_SECRET": "cron-test-secret",
    "WEB_ORIGIN": "http://localhost:3000",
    "MYTRAKIN_LOCAL_STORAGE": tempfile.mkdtemp(prefix="mytrakin-storage-"),
})

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import dispose_engine, get_engine  # noqa: E402
from app.main import app  # noqa: E402

USERS = {
    "admin": "admin@example.com",
    "finance": "finance@example.com",
    "consultant": "ravi.kumar@example.com",
    "vendor": "s.rao@brightpath.example",
    "platform": "owner@mytrakin.example",
    "outsider": "someone@else.example",
}


@pytest.fixture(scope="session", autouse=True)
def database():
    if os.environ.get("SKIP_DB_RESET") != "1":
        subprocess.run([str(ROOT / "scripts" / "db-local-reset.sh"), DB_URL], check=True, capture_output=True)
    yield


@pytest.fixture(scope="session")
async def user_ids(database) -> dict[str, uuid.UUID]:
    """Create the auth users; the sign-up trigger claims their invitations."""
    ids = {}
    async with get_engine().begin() as conn:
        for key, email in USERS.items():
            ids[key] = (await conn.execute(text("insert into auth.users (email) values (:e) returning id"), {"e": email})).scalar()
        await conn.execute(text("insert into mytrakin.platform_admins (user_id) values (:u)"), {"u": ids["platform"]})
    yield ids
    await dispose_engine()


def token_for(user_id: uuid.UUID, email: str, aal: str = "aal2") -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "email": email, "aud": "authenticated", "role": "authenticated",
                       "aal": aal, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
async def client(user_ids):
    transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test/v1") as c:
        yield c


@pytest.fixture(scope="session")
def auth(user_ids):
    """auth("finance") -> headers for that demo user."""
    def headers(who: str, aal: str = "aal2") -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_ids[who], USERS[who], aal)}"}
    return headers
