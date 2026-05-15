from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import URL

from core.csrf import csrf_dependency, generate_csrf_token, verify_csrf
from core.middleware.auth import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    get_current_user,
    optional_user,
    set_session_cookie,
)
from core.rate_limit import RateLimiter
from core.security.sessions import create_session
from modules.auth.schemas import UserRecord


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counts = {}
        self.expirations = {}
        self.sets = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        self.expirations[key] = ttl

    async def ttl(self, key):
        return self.expirations.get(key, -1)

    async def setex(self, key, ttl, value):
        self.values[key] = value
        self.expirations[key] = ttl

    async def get(self, key):
        return self.values.get(key)

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)


class FakeResponse:
    def __init__(self):
        self.cookies = []
        self.deleted = []

    def set_cookie(self, *args, **kwargs):
        self.cookies.append((args, kwargs))

    def delete_cookie(self, *args, **kwargs):
        self.deleted.append((args, kwargs))


class FakeRequest:
    def __init__(self, *, cookies=None, headers=None, scheme="http"):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = URL(f"{scheme}://test.local")


def user_record(user_id):
    now = datetime.now(timezone.utc)
    return UserRecord(
        id=user_id,
        email="user@example.com",
        password_hash="hash",
        name="User",
        created_at=now,
        updated_at=now,
    )


def test_csrf_helpers_and_dependency():
    token = generate_csrf_token()

    assert token
    assert verify_csrf("same", "same")
    assert not verify_csrf("same", "other")
    assert not verify_csrf(None, "same")
    assert not verify_csrf("same", None)


@pytest.mark.asyncio
async def test_csrf_dependency_accepts_and_rejects():
    await csrf_dependency(FakeRequest(cookies={"cnpj_csrf": "t"}, headers={"x-csrf-token": "t"}))

    with pytest.raises(HTTPException) as exc:
        await csrf_dependency(FakeRequest())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_rate_limiter_allows_without_redis_and_blocks_after_limit():
    assert (await RateLimiter(None, bucket_key="b", window=60, max_count=2).try_acquire()).ok

    redis = FakeRedis()
    limiter = RateLimiter(redis, bucket_key="b", window=60, max_count=2)

    first = await limiter.try_acquire()
    second = await limiter.try_acquire()
    third = await limiter.try_acquire()

    assert first.ok
    assert first.remaining == 1
    assert second.ok
    assert third.ok is False
    assert third.retry_after == 60


def test_rate_limiter_validates_config():
    with pytest.raises(ValueError):
        RateLimiter(None, bucket_key="b", window=0, max_count=1)
    with pytest.raises(ValueError):
        RateLimiter(None, bucket_key="b", window=1, max_count=0)


def test_session_cookie_helpers():
    response = FakeResponse()

    set_session_cookie(response, "sid", secure=True)
    clear_session_cookie(response, secure=False)

    assert response.cookies[0][0] == (SESSION_COOKIE_NAME, "sid")
    assert response.cookies[0][1]["httponly"]
    assert response.cookies[0][1]["secure"]
    assert response.deleted[0][0] == (SESSION_COOKIE_NAME,)


@pytest.mark.asyncio
async def test_optional_user_returns_none_without_session_or_redis():
    assert await optional_user(FakeRequest(), FakeResponse()) is None

    with patch("core.middleware.auth.get_redis", return_value=None):
        request = FakeRequest(cookies={SESSION_COOKIE_NAME: "sid"})
        assert await optional_user(request, FakeResponse()) is None


@pytest.mark.asyncio
async def test_optional_user_returns_user_and_refreshes_cookie():
    redis = FakeRedis()
    user_id = uuid4()
    session_id = await create_session(redis, user_id, "127.0.0.1", "ua")
    response = FakeResponse()

    with patch("core.middleware.auth.get_redis", return_value=redis), \
         patch("core.middleware.auth.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("core.middleware.auth.UserRepository") as repo_cls:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=user_record(user_id))
        user = await optional_user(
            FakeRequest(cookies={SESSION_COOKIE_NAME: session_id}, scheme="https"),
            response,
        )

    assert user is not None
    assert user.id == user_id
    assert response.cookies[0][1]["secure"]


@pytest.mark.asyncio
async def test_optional_user_handles_missing_session_and_user():
    redis = FakeRedis()
    with patch("core.middleware.auth.get_redis", return_value=redis):
        assert await optional_user(FakeRequest(cookies={SESSION_COOKIE_NAME: "missing"}), FakeResponse()) is None

    user_id = uuid4()
    session_id = await create_session(redis, user_id, None, None)
    with patch("core.middleware.auth.get_redis", return_value=redis), \
         patch("core.middleware.auth.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("core.middleware.auth.UserRepository") as repo_cls:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
        assert await optional_user(FakeRequest(cookies={SESSION_COOKIE_NAME: session_id}), FakeResponse()) is None


@pytest.mark.asyncio
async def test_get_current_user_raises_when_missing():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(FakeRequest(), FakeResponse())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_authenticated_user():
    user_id = uuid4()
    user = user_record(user_id)

    with patch("core.middleware.auth.optional_user", new_callable=AsyncMock, return_value=user):
        assert await get_current_user(FakeRequest(), FakeResponse()) == user
