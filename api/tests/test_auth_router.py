from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import URL

from core.security.sessions import create_session, destroy_user_sessions
from modules.auth import router as auth_router
from modules.auth.schemas import (
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
)
from modules.auth.service import hash_password, hash_token
from modules.auth.schemas import UserRecord


class FakeRequest:
    def __init__(self, *, cookies=None, headers=None, scheme="http", client_host="127.0.0.1"):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = URL(f"{scheme}://test.local")
        self.client = SimpleNamespace(host=client_host) if client_host is not None else None


class FakeResponse:
    def __init__(self):
        self.cookies = []
        self.deleted = []

    def set_cookie(self, *args, **kwargs):
        self.cookies.append((args, kwargs))

    def delete_cookie(self, *args, **kwargs):
        self.deleted.append((args, kwargs))


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.expirations = {}
        self.deleted = []

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
        self.deleted.append(key)
        self.values.pop(key, None)
        self.sets.pop(key, None)

    async def srem(self, key, value):
        self.sets.setdefault(key, set()).discard(value)

    async def smembers(self, key):
        return self.sets.get(key, set())


def user_record(*, verified=True, password_hash=None):
    now = datetime.now(timezone.utc)
    return UserRecord(
        id=uuid4(),
        email="user@example.com",
        password_hash=password_hash or hash_password("correct horse battery staple"),
        name="User",
        email_verified_at=now if verified else None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_csrf_endpoint_sets_cookie_and_secure_flag():
    response = FakeResponse()

    result = await auth_router.csrf(response, FakeRequest(scheme="https"))

    assert result.csrf
    assert response.cookies[0][0][0] == "cnpj_csrf"
    assert response.cookies[0][1]["secure"]


@pytest.mark.asyncio
async def test_limit_raises_429_when_bucket_is_exhausted():
    limiter = AsyncMock()
    limiter.try_acquire.return_value = SimpleNamespace(ok=False, retry_after=42)

    with patch("modules.auth.router.RateLimiter", return_value=limiter):
        with pytest.raises(HTTPException) as exc:
            await auth_router._limit(FakeRequest(), "key", window=1, max_count=1)

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "42"


@pytest.mark.asyncio
async def test_create_and_send_verification_persists_token_and_sends_email():
    repo = AsyncMock()
    user = user_record()

    with patch("modules.auth.router.EmailVerificationRepo", return_value=repo), \
         patch("modules.auth.router.send_verification_email", new_callable=AsyncMock) as send:
        await auth_router._create_and_send_verification(user, object())

    assert repo.insert.await_count == 1
    assert send.await_count == 1


@pytest.mark.asyncio
async def test_register_validation_existing_and_success():
    request = FakeRequest(headers={"user-agent": "ua"})
    payload = RegisterRequest(name=" User ", email="user@example.com", password="correct horse battery staple")

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.check_pwned", new_callable=AsyncMock, return_value=False), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.UserRepository") as users_cls:
        users_cls.return_value.get_by_email = AsyncMock(return_value=user_record())
        result = await auth_router.register(payload, request)
        assert result.ok

        users_cls.return_value.get_by_email = AsyncMock(return_value=None)
        users_cls.return_value.insert = AsyncMock(return_value=user_record())
        with patch("modules.auth.router.AuthEventRepo") as events_cls, \
             patch("modules.auth.router._create_and_send_verification", new_callable=AsyncMock) as send:
            events_cls.return_value.record = AsyncMock()
            result = await auth_router.register(payload, request)
            assert result.message.startswith("Cadastro")
            assert send.await_count == 1

    with pytest.raises(HTTPException):
        await auth_router.register(RegisterRequest(name="U", email="user@example.com", password="short"), request)

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.check_pwned", new_callable=AsyncMock, return_value=True):
        with pytest.raises(HTTPException) as exc:
            await auth_router.register(payload, request)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_verify_email_invalid_and_success():
    request = FakeRequest(headers={"user-agent": "ua"})
    repo = AsyncMock()
    user_id = uuid4()

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.EmailVerificationRepo", return_value=repo):
        repo.get_valid = AsyncMock(return_value=None)
        with pytest.raises(HTTPException):
            await auth_router.verify_email(TokenRequest(token="bad"), request)

        repo.get_valid = AsyncMock(return_value={"user_id": user_id})
        repo.mark_used = AsyncMock()
        with patch("modules.auth.router.UserRepository") as users_cls, \
             patch("modules.auth.router.AuthEventRepo") as events_cls:
            users_cls.return_value.mark_verified = AsyncMock()
            events_cls.return_value.record = AsyncMock()
            result = await auth_router.verify_email(TokenRequest(token="ok"), request)
            assert result.ok


@pytest.mark.asyncio
async def test_resend_verification_handles_missing_verified_and_unverified():
    request = FakeRequest()
    payload = EmailRequest(email="user@example.com")

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.UserRepository") as users_cls, \
         patch("modules.auth.router._create_and_send_verification", new_callable=AsyncMock) as send:
        users_cls.return_value.get_by_email = AsyncMock(return_value=None)
        assert (await auth_router.resend_verification(payload, request)).ok

        users_cls.return_value.get_by_email = AsyncMock(return_value=user_record(verified=True))
        assert (await auth_router.resend_verification(payload, request)).ok

        users_cls.return_value.get_by_email = AsyncMock(return_value=user_record(verified=False))
        assert (await auth_router.resend_verification(payload, request)).ok
        assert send.await_count == 1


@pytest.mark.asyncio
async def test_login_failure_unverified_no_redis_and_success():
    request = FakeRequest(headers={"user-agent": "ua"}, scheme="https")
    response = FakeResponse()
    payload = LoginRequest(email="user@example.com", password="correct horse battery staple")

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.UserRepository") as users_cls, \
         patch("modules.auth.router.AuthEventRepo") as events_cls:
        events_cls.return_value.record = AsyncMock()
        users_cls.return_value.get_by_email = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await auth_router.login(payload, request, response)
        assert exc.value.status_code == 401

        users_cls.return_value.get_by_email = AsyncMock(return_value=user_record(verified=False))
        with pytest.raises(HTTPException) as exc:
            await auth_router.login(payload, request, response)
        assert exc.value.status_code == 403

        users_cls.return_value.get_by_email = AsyncMock(return_value=user_record(verified=True))
        with patch("modules.auth.router.get_redis", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await auth_router.login(payload, request, response)
            assert exc.value.status_code == 503

        with patch("modules.auth.router.get_redis", return_value=FakeRedis()):
            result = await auth_router.login(payload, request, response)
            assert result.email == "user@example.com"
            assert response.cookies


@pytest.mark.asyncio
async def test_logout_me_and_forgot_password():
    redis = FakeRedis()
    user = user_record()
    session_id = await create_session(redis, user.id, None, None)
    response = FakeResponse()

    with patch("modules.auth.router.get_redis", return_value=redis):
        result = await auth_router.logout(FakeRequest(cookies={"cnpj_session": session_id}), response)
        assert result.ok
        assert response.deleted

    with patch("modules.auth.router.get_redis", return_value=None):
        assert (await auth_router.logout(FakeRequest(), FakeResponse())).ok

    assert (await auth_router.me(user)).id == user.id

    payload = EmailRequest(email="user@example.com")
    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.UserRepository") as users_cls, \
         patch("modules.auth.router.PasswordResetRepo") as reset_cls, \
         patch("modules.auth.router.send_reset_email", new_callable=AsyncMock) as send:
        reset_cls.return_value.insert = AsyncMock()
        users_cls.return_value.get_by_email = AsyncMock(return_value=None)
        assert (await auth_router.forgot_password(payload, FakeRequest())).ok
        users_cls.return_value.get_by_email = AsyncMock(return_value=user)
        assert (await auth_router.forgot_password(payload, FakeRequest())).ok
        assert send.await_count == 1


@pytest.mark.asyncio
async def test_reset_password_validation_invalid_and_success():
    request = FakeRequest(headers={"user-agent": "ua"})
    payload = ResetPasswordRequest(token="token", new_password="correct horse battery staple")
    user_id = uuid4()

    with patch("modules.auth.router._limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException):
            await auth_router.reset_password(ResetPasswordRequest(token="t", new_password="short"), request)

    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.check_pwned", new_callable=AsyncMock, return_value=True):
        with pytest.raises(HTTPException):
            await auth_router.reset_password(payload, request)

    repo = AsyncMock()
    with patch("modules.auth.router._limit", new_callable=AsyncMock), \
         patch("modules.auth.router.check_pwned", new_callable=AsyncMock, return_value=False), \
         patch("modules.auth.router.get_pool", new_callable=AsyncMock, return_value=object()), \
         patch("modules.auth.router.PasswordResetRepo", return_value=repo):
        repo.get_valid = AsyncMock(return_value=None)
        with pytest.raises(HTTPException):
            await auth_router.reset_password(payload, request)

        repo.get_valid = AsyncMock(return_value={"user_id": user_id})
        repo.mark_used = AsyncMock()
        with patch("modules.auth.router.UserRepository") as users_cls, \
             patch("modules.auth.router.AuthEventRepo") as events_cls, \
             patch("modules.auth.router.get_redis", return_value=FakeRedis()):
            users_cls.return_value.update_password = AsyncMock()
            events_cls.return_value.record = AsyncMock()
            result = await auth_router.reset_password(payload, request)
            assert result.ok


@pytest.mark.asyncio
async def test_destroy_user_sessions_deletes_index_and_sessions():
    redis = FakeRedis()
    user_id = uuid4()
    first = await create_session(redis, user_id, None, None)
    second = await create_session(redis, user_id, None, None)

    deleted = await destroy_user_sessions(redis, user_id)

    assert deleted == 2
    assert f"sess:{first}" in redis.deleted
    assert f"sess:{second}" in redis.deleted
