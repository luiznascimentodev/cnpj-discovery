"""Verificação de assinatura HMAC do Stripe-Signature header.

Implementação nativa (sem dep `stripe`). Stripe usa um header no formato
`t=<unix>,v1=<hex>,v0=<...>`. Calculamos `HMAC_SHA256(secret, "{t}.{body}")`
e comparamos com o `v1` em tempo constante. Tolerância de timestamp evita
replay attacks.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Callable


class SignatureVerificationError(Exception):
    pass


def _parse_header(header: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for part in header.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            parsed.setdefault(key.strip(), []).append(value.strip())
    return parsed


def verify_stripe_signature(
    *,
    payload: bytes,
    header: str,
    secret: str,
    tolerance_seconds: int = 300,
    now_fn: Callable[[], float] = time.time,
) -> int:
    """Valida o header e devolve o timestamp `t` se a assinatura conferir."""
    if not secret:
        raise SignatureVerificationError("Webhook secret not configured")
    if not header:
        raise SignatureVerificationError("Missing Stripe-Signature header")

    parsed = _parse_header(header)
    timestamps = parsed.get("t", [])
    signatures = parsed.get("v1", [])
    if not timestamps or not signatures:
        raise SignatureVerificationError("Malformed signature header")

    try:
        ts_int = int(timestamps[0])
    except ValueError as exc:
        raise SignatureVerificationError("Invalid timestamp") from exc

    if abs(now_fn() - ts_int) > tolerance_seconds:
        raise SignatureVerificationError("Timestamp outside tolerance window")

    signed_payload = f"{ts_int}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    for candidate in signatures:
        if hmac.compare_digest(expected, candidate):
            return ts_int

    raise SignatureVerificationError("Signature mismatch")
