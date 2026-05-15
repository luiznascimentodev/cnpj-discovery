from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request, status

CSRF_COOKIE_NAME = "cnpj_csrf"
CSRF_HEADER_NAME = "x-csrf-token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


async def csrf_dependency(request: Request) -> None:
    if verify_csrf(request.cookies.get(CSRF_COOKIE_NAME), request.headers.get(CSRF_HEADER_NAME)):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF token inválido",
    )
