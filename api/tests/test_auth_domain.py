from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from core.security.sessions import (
    SESSION_TTL_SECONDS,
    create_session,
    destroy_session,
    read_session,
    touch_session,
)
from modules.auth.repository import (
    AuthEventRepo,
    EmailVerificationRepo,
    PasswordResetRepo,
    UserRepository,
)
from modules.auth.service import check_pwned, hash_password, hash_token, make_token, verify_password


class AcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return AcquireContext(self.conn)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.expirations = {}

    async def setex(self, key, ttl, value):
        self.values[key] = value
        self.expirations[key] = ttl

    async def get(self, key):
        return self.values.get(key)

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def expire(self, key, ttl):
        self.expirations[key] = ttl

    async def delete(self, key):
        self.values.pop(key, None)

    async def srem(self, key, value):
        self.sets.setdefault(key, set()).discard(value)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class RaisingResponse:
    def raise_for_status(self):
        raise httpx.HTTPStatusError("bad", request=MagicMock(), response=MagicMock())


def user_row(user_id=None):
    now = datetime.now(timezone.utc)
    return {
        "id": user_id or uuid4(),
        "email": "user@example.com",
        "password_hash": "hash",
        "name": "User",
        "email_verified_at": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def test_hash_password_roundtrip_and_mismatch():
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong", password_hash)
    assert not verify_password("secret", "not-an-argon-hash")


def test_make_token_returns_raw_and_sha256_hash():
    raw, token_hash = make_token()

    assert raw
    assert token_hash == hash_token(raw)


@pytest.mark.asyncio
async def test_check_pwned_detects_matching_suffix():
    digest = "A" * 40

    async def fake_get(_url):
        return FakeResponse(f"{digest[5:]}:12\nBBBB:1")

    with patch("modules.auth.service.hashlib.sha1") as sha1:
        sha1.return_value.hexdigest.return_value = digest
        with patch("modules.auth.service.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.get = fake_get
            assert await check_pwned("password")


@pytest.mark.asyncio
async def test_check_pwned_returns_false_for_no_match_and_http_error():
    async def no_match(_url):
        return FakeResponse("BBBB:1")

    async def raises_status(_url):
        return RaisingResponse()

    with patch("modules.auth.service.httpx.AsyncClient") as client:
        client.return_value.__aenter__.return_value.get = no_match
        assert not await check_pwned("password")

        client.return_value.__aenter__.return_value.get = raises_status
        assert not await check_pwned("password")


@pytest.mark.asyncio
async def test_user_repository_crud_methods():
    conn = AsyncMock()
    conn.fetchrow.side_effect = [user_row(), user_row(), None]
    pool = FakePool(conn)
    repo = UserRepository(pool)
    user_id = uuid4()

    inserted = await repo.insert(email="user@example.com", password_hash="hash", name="User")
    found = await repo.get_by_email("user@example.com")
    missing = await repo.get_by_id(user_id)
    await repo.mark_verified(user_id, datetime.now(timezone.utc))
    await repo.update_password(user_id, "new-hash")

    assert inserted.email == "user@example.com"
    assert found is not None
    assert missing is None
    assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_token_repositories_and_auth_events():
    conn = AsyncMock()
    valid_row = {"token_hash": b"h", "user_id": uuid4(), "expires_at": datetime.now(timezone.utc)}
    conn.fetchrow.return_value = valid_row
    pool = FakePool(conn)
    email_repo = EmailVerificationRepo(pool)
    reset_repo = PasswordResetRepo(pool)
    events = AuthEventRepo(pool)
    user_id = uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    await email_repo.insert(token_hash=b"h", user_id=user_id, expires_at=expires_at)
    assert await email_repo.get_valid(b"h") == valid_row
    await email_repo.mark_used(b"h")
    await reset_repo.insert(token_hash=b"r", user_id=user_id, expires_at=expires_at)
    await events.record(event="login_ok", user_id=user_id, ip="127.0.0.1", user_agent="test")

    assert conn.execute.await_count == 4


@pytest.mark.asyncio
async def test_session_lifecycle():
    redis = FakeRedis()
    user_id = uuid4()

    session_id = await create_session(redis, user_id, "127.0.0.1", "ua")
    data = await read_session(redis, session_id)
    touched = await touch_session(redis, session_id)
    await destroy_session(redis, session_id)

    assert data is not None
    assert data.user_id == user_id
    assert data.csrf_token
    assert touched is not None
    assert redis.expirations[f"sess:{session_id}"] == SESSION_TTL_SECONDS
    assert await read_session(redis, session_id) is None


@pytest.mark.asyncio
async def test_touch_and_destroy_missing_session():
    redis = FakeRedis()

    assert await touch_session(redis, "missing") is None
    await destroy_session(redis, "missing")

    assert redis.values == {}
