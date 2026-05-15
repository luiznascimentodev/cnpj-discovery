from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from core.cache import get_redis
from core.config import settings
from core.csrf import CSRF_COOKIE_NAME, csrf_dependency, generate_csrf_token
from core.db import get_pool
from core.middleware.auth import (
    clear_session_cookie,
    get_current_user,
    set_session_cookie,
)
from core.rate_limit import RateLimiter
from core.security.sessions import create_session, destroy_session, destroy_user_sessions
from modules.auth.emails import send_reset_email, send_verification_email
from modules.auth.repository import (
    AuthEventRepo,
    EmailVerificationRepo,
    PasswordResetRepo,
    UserRepository,
)
from modules.auth.schemas import (
    CsrfResponse,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserOut,
    UserRecord,
    to_user_out,
)
from modules.auth.service import check_pwned, hash_password, hash_token, make_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_VERIFY_TTL = timedelta(hours=24)
_RESET_TTL = timedelta(hours=1)
_DUMMY_HASH = hash_password("dummy password for timing checks")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _secure_cookie(request: Request) -> bool:
    return settings.environment == "production" or request.url.scheme == "https"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _limit(request: Request, key: str, *, window: int, max_count: int) -> None:
    redis = get_redis()
    result = await RateLimiter(
        redis,
        bucket_key=f"rate:{key}",
        window=window,
        max_count=max_count,
    ).try_acquire()
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(result.retry_after)},
        )


async def _create_and_send_verification(user: UserRecord, pool) -> None:
    raw, token_hash = make_token()
    await EmailVerificationRepo(pool).insert(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=_now() + _VERIFY_TTL,
    )
    await send_verification_email(user, raw)


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(response: Response, request: Request) -> CsrfResponse:
    token = generate_csrf_token()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=604800,
        httponly=False,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    return CsrfResponse(csrf=token)


@router.post(
    "/register",
    response_model=MessageResponse,
    dependencies=[Depends(csrf_dependency)],
)
async def register(payload: RegisterRequest, request: Request) -> MessageResponse:
    ip = _client_ip(request)
    await _limit(request, f"register:ip:{ip}", window=3600, max_count=5)
    await _limit(request, f"register:email:{payload.email}", window=3600, max_count=3)
    if len(payload.password) < 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Senha deve ter no mínimo 12 caracteres")
    if await check_pwned(payload.password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Senha comprometida em vazamentos conhecidos")

    pool = await get_pool()
    users = UserRepository(pool)
    existing = await users.get_by_email(str(payload.email))
    if existing is not None:
        return MessageResponse(message="Se o e-mail puder ser cadastrado, enviaremos instruções.")

    user = await users.insert(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
    )
    await AuthEventRepo(pool).record(event="register", user_id=user.id, ip=ip, user_agent=request.headers.get("user-agent"))
    await _create_and_send_verification(user, pool)
    return MessageResponse(message="Cadastro criado. Verifique seu e-mail.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: TokenRequest, request: Request) -> MessageResponse:
    await _limit(request, f"verify:ip:{_client_ip(request)}", window=3600, max_count=20)
    pool = await get_pool()
    repo = EmailVerificationRepo(pool)
    row = await repo.get_valid(hash_token(payload.token))
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido ou expirado")

    user_id = UUID(str(row["user_id"]))
    await UserRepository(pool).mark_verified(user_id, _now())
    await repo.mark_used(hash_token(payload.token))
    await AuthEventRepo(pool).record(event="verify", user_id=user_id, ip=_client_ip(request), user_agent=request.headers.get("user-agent"))
    return MessageResponse(message="E-mail verificado.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(csrf_dependency)],
)
async def resend_verification(payload: EmailRequest, request: Request) -> MessageResponse:
    await _limit(request, f"resend:email:{payload.email}", window=3600, max_count=3)
    pool = await get_pool()
    user = await UserRepository(pool).get_by_email(str(payload.email))
    if user is not None and user.email_verified_at is None:
        await _create_and_send_verification(user, pool)
    return MessageResponse(message="Se o e-mail existir, enviaremos uma nova verificação.")


@router.post("/login", response_model=UserOut, dependencies=[Depends(csrf_dependency)])
async def login(payload: LoginRequest, request: Request, response: Response) -> UserOut:
    ip = _client_ip(request)
    await _limit(request, f"login:ip:{ip}", window=900, max_count=10)
    await _limit(request, f"login:email:{payload.email}", window=900, max_count=5)
    pool = await get_pool()
    user = await UserRepository(pool).get_by_email(str(payload.email))
    password_hash = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(payload.password, password_hash)
    if user is None or not valid:
        await AuthEventRepo(pool).record(event="login_fail", ip=ip, user_agent=request.headers.get("user-agent"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="E-mail ainda não verificado")
    redis = get_redis()
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sessões indisponíveis")
    session_id = await create_session(redis, user.id, ip, request.headers.get("user-agent"))
    set_session_cookie(response, session_id, secure=_secure_cookie(request))
    await AuthEventRepo(pool).record(event="login_ok", user_id=user.id, ip=ip, user_agent=request.headers.get("user-agent"))
    return to_user_out(user)


@router.post("/logout", response_model=MessageResponse, dependencies=[Depends(csrf_dependency)])
async def logout(request: Request, response: Response) -> MessageResponse:
    redis = get_redis()
    session_id = request.cookies.get("cnpj_session")
    if redis is not None and session_id:
        await destroy_session(redis, session_id)
    clear_session_cookie(response, secure=_secure_cookie(request))
    return MessageResponse(message="Logout realizado.")


@router.get("/me", response_model=UserOut)
async def me(user: UserRecord = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(csrf_dependency)],
)
async def forgot_password(payload: EmailRequest, request: Request) -> MessageResponse:
    ip = _client_ip(request)
    await _limit(request, f"forgot:ip:{ip}", window=3600, max_count=5)
    await _limit(request, f"forgot:email:{payload.email}", window=3600, max_count=3)
    pool = await get_pool()
    user = await UserRepository(pool).get_by_email(str(payload.email))
    if user is not None:
        raw, token_hash = make_token()
        await PasswordResetRepo(pool).insert(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=_now() + _RESET_TTL,
        )
        await send_reset_email(user, raw)
    return MessageResponse(message="Se o e-mail existir, enviaremos instruções de recuperação.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, request: Request) -> MessageResponse:
    await _limit(request, f"reset:ip:{_client_ip(request)}", window=3600, max_count=10)
    if len(payload.new_password) < 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Senha deve ter no mínimo 12 caracteres")
    if await check_pwned(payload.new_password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Senha comprometida em vazamentos conhecidos")
    pool = await get_pool()
    repo = PasswordResetRepo(pool)
    token_hash = hash_token(payload.token)
    row = await repo.get_valid(token_hash)
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido ou expirado")

    user_id = UUID(str(row["user_id"]))
    await UserRepository(pool).update_password(user_id, hash_password(payload.new_password))
    await repo.mark_used(token_hash)
    redis = get_redis()
    if redis is not None:
        await destroy_user_sessions(redis, user_id)
    await AuthEventRepo(pool).record(event="reset_ok", user_id=user_id, ip=_client_ip(request), user_agent=request.headers.get("user-agent"))
    return MessageResponse(message="Senha redefinida.")
