from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import UUID

SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class SessionData:
    user_id: UUID
    csrf_token: str
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime


def _session_key(session_id: str) -> str:
    return f"sess:{session_id}"


def _user_sessions_key(user_id: UUID) -> str:
    return f"user_sessions:{user_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(data: SessionData) -> str:
    raw = asdict(data)
    raw["user_id"] = str(data.user_id)
    raw["created_at"] = data.created_at.isoformat()
    raw["last_seen_at"] = data.last_seen_at.isoformat()
    return json.dumps(raw)


def _deserialize(raw: str) -> SessionData:
    data = json.loads(raw)
    return SessionData(
        user_id=UUID(data["user_id"]),
        csrf_token=data["csrf_token"],
        ip=data.get("ip"),
        user_agent=data.get("user_agent"),
        created_at=datetime.fromisoformat(data["created_at"]),
        last_seen_at=datetime.fromisoformat(data["last_seen_at"]),
    )


async def create_session(redis, user_id: UUID, ip: str | None, user_agent: str | None) -> str:
    session_id = secrets.token_urlsafe(32)
    now = _now()
    data = SessionData(
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(32),
        ip=ip,
        user_agent=user_agent,
        created_at=now,
        last_seen_at=now,
    )
    await redis.setex(_session_key(session_id), SESSION_TTL_SECONDS, _serialize(data))
    await redis.sadd(_user_sessions_key(user_id), session_id)
    await redis.expire(_user_sessions_key(user_id), SESSION_TTL_SECONDS)
    return session_id


async def read_session(redis, session_id: str) -> SessionData | None:
    raw = await redis.get(_session_key(session_id))
    return _deserialize(raw) if raw else None


async def touch_session(redis, session_id: str) -> SessionData | None:
    data = await read_session(redis, session_id)
    if data is None:
        return None
    updated = SessionData(
        user_id=data.user_id,
        csrf_token=data.csrf_token,
        ip=data.ip,
        user_agent=data.user_agent,
        created_at=data.created_at,
        last_seen_at=_now(),
    )
    await redis.setex(_session_key(session_id), SESSION_TTL_SECONDS, _serialize(updated))
    await redis.expire(_user_sessions_key(data.user_id), SESSION_TTL_SECONDS)
    return updated


async def destroy_session(redis, session_id: str) -> None:
    data = await read_session(redis, session_id)
    await redis.delete(_session_key(session_id))
    if data is not None:
        await redis.srem(_user_sessions_key(data.user_id), session_id)
