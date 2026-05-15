"""Receiver Stripe-compatível para customer.subscription.* events."""
import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.config import settings
from core.db import get_pool
from modules.billing.service import apply_subscription_event, parse_subscription_event
from modules.billing.stripe_signature import (
    SignatureVerificationError,
    verify_stripe_signature,
)

router = APIRouter()


@router.post(
    "/billing/webhook",
    status_code=status.HTTP_200_OK,
    tags=["billing"],
    summary="Stripe webhook receiver",
    include_in_schema=False,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[
        str | None, Header(alias="Stripe-Signature")
    ] = None,
) -> dict:
    payload = await request.body()
    try:
        verify_stripe_signature(
            payload=payload,
            header=stripe_signature or "",
            secret=settings.stripe_webhook_secret,
            tolerance_seconds=settings.stripe_signature_tolerance_seconds,
        )
    except SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        event_payload = json.loads(payload.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    event = parse_subscription_event(event_payload)
    if event is None:
        return {"received": True, "applied": False}

    pool = await get_pool()
    await apply_subscription_event(pool, event)
    return {"received": True, "applied": True, "event_type": event.event_type}
