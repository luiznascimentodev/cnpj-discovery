from __future__ import annotations

from fastapi import HTTPException, Request, Response, status

from core.cache import get_redis
from core.db import get_pool
from core.security.sessions import SESSION_TTL_SECONDS, read_session, touch_session
from modules.auth.repository import UserRepository
from modules.auth.schemas import UserRecord

SESSION_COOKIE_NAME = "cnpj_session"


def set_session_cookie(response: Response, session_id: str, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


async def optional_user(request: Request, response: Response) -> UserRecord | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    redis = get_redis()
    if not session_id or redis is None:
        return None

    session = await touch_session(redis, session_id)
    if session is None:
        return None

    user = await UserRepository(await get_pool()).get_by_id(session.user_id)
    if user is None:
        return None

    set_session_cookie(response, session_id, secure=request.url.scheme == "https")
    return user


async def get_current_user(request: Request, response: Response) -> UserRecord:
    user = await optional_user(request, response)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")
    return user
