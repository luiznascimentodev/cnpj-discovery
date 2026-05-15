from __future__ import annotations

import hashlib
import secrets

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)
_HIBP_URL = "https://api.pwnedpasswords.com/range/{prefix}"


def hash_password(plain: str) -> str:
    return _HASHER.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _HASHER.verify(password_hash, plain)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def make_token() -> tuple[str, bytes]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


async def check_pwned(plain: str, *, timeout: float = 2.0) -> bool:
    digest = hashlib.sha1(plain.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(_HIBP_URL.format(prefix=prefix))
            response.raise_for_status()
    except httpx.HTTPError:
        return False

    for line in response.text.splitlines():
        candidate, _, _count = line.partition(":")
        if candidate.upper() == suffix:
            return True
    return False
