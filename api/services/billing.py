"""Aplicação idempotente de eventos de subscription do Stripe.

Inputs: payload JSON do webhook. Side-effects: upsert de
`app_private.billing_accounts`, `billing_subscriptions` e
`billing_entitlements` (com bump de `entitlement_version`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DEFAULT_PLAN_FEATURES: dict[str, tuple[str, ...]] = {
    "starter": ("crawler_contacts",),
    "pro": ("crawler_contacts", "crawler_exports"),
    "business": ("crawler_contacts", "crawler_exports", "bulk_enrichment"),
}

ALL_FEATURES = ("crawler_contacts", "crawler_exports", "bulk_enrichment")
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
SUPPORTED_STATUSES = frozenset(
    {
        "active",
        "trialing",
        "past_due",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "unpaid",
        "paused",
    }
)
SUBSCRIPTION_EVENT_PREFIX = "customer.subscription."

_SQL_UPSERT_ACCOUNT = """
    INSERT INTO app_private.billing_accounts (account_id, stripe_customer_id, updated_at)
    VALUES ($1, $2, now())
    ON CONFLICT (account_id) DO UPDATE SET
        stripe_customer_id = EXCLUDED.stripe_customer_id,
        updated_at = now()
"""

_SQL_UPSERT_SUBSCRIPTION = """
    INSERT INTO app_private.billing_subscriptions (
        account_id, stripe_subscription_id, status, plan_code,
        current_period_end, cancel_at_period_end, updated_at
    )
    VALUES ($1, $2, $3, $4, CASE WHEN $5::BIGINT IS NULL THEN NULL ELSE to_timestamp($5) END, $6, now())
    ON CONFLICT (stripe_subscription_id) DO UPDATE SET
        account_id = EXCLUDED.account_id,
        status = EXCLUDED.status,
        plan_code = EXCLUDED.plan_code,
        current_period_end = EXCLUDED.current_period_end,
        cancel_at_period_end = EXCLUDED.cancel_at_period_end,
        updated_at = now()
"""

_SQL_UPSERT_ENTITLEMENT = """
    INSERT INTO app_private.billing_entitlements (
        account_id, feature_key, is_enabled, entitlement_version, updated_at
    )
    VALUES ($1, $2, $3, 1, now())
    ON CONFLICT (account_id, feature_key) DO UPDATE SET
        is_enabled = EXCLUDED.is_enabled,
        entitlement_version = app_private.billing_entitlements.entitlement_version + 1,
        updated_at = now()
"""


@dataclass(frozen=True)
class SubscriptionEvent:
    event_type: str
    account_id: str
    stripe_customer_id: str
    stripe_subscription_id: str
    status: str
    plan_code: str
    current_period_end: int | None = None
    cancel_at_period_end: bool = False


def features_for_plan(
    plan_code: str,
    plan_features: dict[str, tuple[str, ...]] = DEFAULT_PLAN_FEATURES,
) -> tuple[str, ...]:
    return plan_features.get(plan_code, ())


def _first_lookup_key(obj: dict) -> str | None:
    items = obj.get("items", {}).get("data", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("lookup_key")
        if key:
            return key
        price = item.get("price")
        if isinstance(price, dict) and price.get("lookup_key"):
            return price["lookup_key"]
    return None


def parse_subscription_event(payload: dict) -> SubscriptionEvent | None:
    event_type = payload.get("type", "")
    if not event_type.startswith(SUBSCRIPTION_EVENT_PREFIX):
        return None

    obj = payload.get("data", {}).get("object", {}) or {}
    stripe_subscription_id = obj.get("id") or ""
    stripe_customer_id = obj.get("customer") or ""
    status = obj.get("status") or ""

    metadata = obj.get("metadata") or {}
    plan_code = (
        metadata.get("plan_code")
        or _first_lookup_key(obj)
        or ""
    )

    if not (stripe_subscription_id and stripe_customer_id and status):
        return None

    return SubscriptionEvent(
        event_type=event_type,
        account_id=stripe_customer_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        status=status,
        plan_code=plan_code,
        current_period_end=obj.get("current_period_end"),
        cancel_at_period_end=bool(obj.get("cancel_at_period_end", False)),
    )


async def apply_subscription_event(
    pool,
    event: SubscriptionEvent,
    *,
    plan_features: dict[str, tuple[str, ...]] = DEFAULT_PLAN_FEATURES,
    features: Iterable[str] = ALL_FEATURES,
) -> None:
    """Idempotente. Pode ser chamada múltiplas vezes para o mesmo evento."""
    is_deleted = event.event_type == "customer.subscription.deleted"
    final_status = "canceled" if is_deleted else event.status
    if final_status not in SUPPORTED_STATUSES:
        raise ValueError(f"Unsupported subscription status: {final_status}")

    plan_code = event.plan_code or "unknown"
    feature_set = set(features_for_plan(event.plan_code, plan_features))
    enabled_overall = (not is_deleted) and (event.status in ACTIVE_SUBSCRIPTION_STATUSES)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                _SQL_UPSERT_ACCOUNT,
                event.account_id,
                event.stripe_customer_id,
            )
            await conn.execute(
                _SQL_UPSERT_SUBSCRIPTION,
                event.account_id,
                event.stripe_subscription_id,
                final_status,
                plan_code,
                event.current_period_end,
                event.cancel_at_period_end,
            )
            for feature in features:
                feature_enabled = enabled_overall and feature in feature_set
                await conn.execute(
                    _SQL_UPSERT_ENTITLEMENT,
                    event.account_id,
                    feature,
                    feature_enabled,
                )
