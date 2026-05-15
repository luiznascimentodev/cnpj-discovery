import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from modules.billing.service import (
    ALL_FEATURES,
    DEFAULT_PLAN_FEATURES,
    SUPPORTED_STATUSES,
    SubscriptionEvent,
    apply_subscription_event,
    features_for_plan,
    parse_subscription_event,
)
from modules.billing.stripe_signature import (
    SignatureVerificationError,
    verify_stripe_signature,
)


# ---------- Fakes ----------


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeTransaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self):
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    def transaction(self):
        return FakeTransaction()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def _sign(payload: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


# ---------- stripe_signature ----------


class TestStripeSignature:
    def test_verifies_correct_signature(self):
        payload = b'{"hello":"world"}'
        secret = "whsec_x"
        ts = 1700000000
        header = _sign(payload, secret, ts)

        verified = verify_stripe_signature(
            payload=payload,
            header=header,
            secret=secret,
            tolerance_seconds=600,
            now_fn=lambda: ts,
        )

        assert verified == ts

    def test_rejects_missing_secret(self):
        with pytest.raises(SignatureVerificationError, match="secret"):
            verify_stripe_signature(payload=b"x", header="t=1,v1=abc", secret="")

    def test_rejects_missing_header(self):
        with pytest.raises(SignatureVerificationError, match="Missing"):
            verify_stripe_signature(payload=b"x", header="", secret="s")

    def test_rejects_malformed_header(self):
        with pytest.raises(SignatureVerificationError, match="Malformed"):
            verify_stripe_signature(
                payload=b"x", header="invalid", secret="s"
            )

    def test_rejects_invalid_timestamp(self):
        with pytest.raises(SignatureVerificationError, match="Invalid timestamp"):
            verify_stripe_signature(
                payload=b"x", header="t=notanint,v1=abc", secret="s"
            )

    def test_rejects_timestamp_outside_tolerance(self):
        with pytest.raises(SignatureVerificationError, match="tolerance"):
            verify_stripe_signature(
                payload=b"x",
                header="t=1700000000,v1=abc",
                secret="s",
                tolerance_seconds=10,
                now_fn=lambda: 1700001000,
            )

    def test_rejects_signature_mismatch(self):
        with pytest.raises(SignatureVerificationError, match="mismatch"):
            verify_stripe_signature(
                payload=b"x",
                header="t=1,v1=deadbeef",
                secret="s",
                tolerance_seconds=10**9,
                now_fn=lambda: 1,
            )


# ---------- billing parse + apply ----------


class TestParseSubscriptionEvent:
    def test_returns_none_for_non_subscription_event(self):
        assert parse_subscription_event({"type": "invoice.paid"}) is None

    def test_returns_none_when_required_fields_missing(self):
        payload = {
            "type": "customer.subscription.created",
            "data": {"object": {"id": "sub_1"}},
        }
        assert parse_subscription_event(payload) is None

    def test_uses_metadata_plan_code_when_present(self):
        payload = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "active",
                    "metadata": {"plan_code": "pro"},
                    "current_period_end": 123,
                    "cancel_at_period_end": True,
                }
            },
        }
        event = parse_subscription_event(payload)
        assert event is not None
        assert event.plan_code == "pro"
        assert event.cancel_at_period_end is True
        assert event.current_period_end == 123

    def test_falls_back_to_lookup_key(self):
        payload = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_2",
                    "customer": "cus_2",
                    "status": "trialing",
                    "items": {"data": [{"lookup_key": "starter"}]},
                }
            },
        }
        event = parse_subscription_event(payload)
        assert event is not None
        assert event.plan_code == "starter"

    def test_falls_back_to_price_lookup_key(self):
        payload = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_3",
                    "customer": "cus_3",
                    "status": "active",
                    "items": {
                        "data": [
                            "ignored_string_item",
                            {"price": {"lookup_key": "business"}},
                        ]
                    },
                }
            },
        }
        event = parse_subscription_event(payload)
        assert event is not None
        assert event.plan_code == "business"

    def test_returns_empty_plan_code_when_no_signal(self):
        payload = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_4",
                    "customer": "cus_4",
                    "status": "active",
                    "items": {"data": [{}]},
                }
            },
        }
        event = parse_subscription_event(payload)
        assert event is not None
        assert event.plan_code == ""


class TestFeaturesForPlan:
    def test_returns_known_features(self):
        assert features_for_plan("pro") == DEFAULT_PLAN_FEATURES["pro"]

    def test_returns_empty_for_unknown(self):
        assert features_for_plan("anything") == ()


class TestApplySubscriptionEvent:
    @pytest.mark.asyncio
    async def test_active_subscription_enables_plan_features(self):
        conn = FakeConnection()
        event = SubscriptionEvent(
            event_type="customer.subscription.created",
            account_id="cus_1",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
            plan_code="pro",
            current_period_end=1234567890,
            cancel_at_period_end=False,
        )

        await apply_subscription_event(FakePool(conn), event)

        # 1 account upsert + 1 subscription upsert + 3 entitlement upserts
        assert len(conn.execute_calls) == 2 + len(ALL_FEATURES)
        feature_calls = conn.execute_calls[2:]
        enabled_map = {call[1][1]: call[1][2] for call in feature_calls}
        assert enabled_map["crawler_contacts"] is True
        assert enabled_map["crawler_exports"] is True
        assert enabled_map["bulk_enrichment"] is False

    @pytest.mark.asyncio
    async def test_deleted_event_disables_all_features(self):
        conn = FakeConnection()
        event = SubscriptionEvent(
            event_type="customer.subscription.deleted",
            account_id="cus_1",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
            plan_code="pro",
        )

        await apply_subscription_event(FakePool(conn), event)

        sub_query, sub_args = conn.execute_calls[1][0], conn.execute_calls[1][1]
        assert "billing_subscriptions" in sub_query
        assert sub_args[2] == "canceled"

        feature_calls = conn.execute_calls[2:]
        for call in feature_calls:
            assert call[1][2] is False

    @pytest.mark.asyncio
    async def test_unsupported_status_raises(self):
        conn = FakeConnection()
        event = SubscriptionEvent(
            event_type="customer.subscription.updated",
            account_id="cus_1",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="bogus",
            plan_code="pro",
        )

        with pytest.raises(ValueError, match="Unsupported"):
            await apply_subscription_event(FakePool(conn), event)

    @pytest.mark.asyncio
    async def test_blank_plan_code_falls_back_to_unknown(self):
        conn = FakeConnection()
        event = SubscriptionEvent(
            event_type="customer.subscription.updated",
            account_id="cus_1",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
            plan_code="",
        )

        await apply_subscription_event(FakePool(conn), event)

        sub_args = conn.execute_calls[1][1]
        assert sub_args[3] == "unknown"

    def test_supported_statuses_match_db_constraint(self):
        # safety net so we keep parity with the CHECK constraint in 010_enrichment.sql
        assert "active" in SUPPORTED_STATUSES
        assert "canceled" in SUPPORTED_STATUSES


# ---------- HTTP webhook ----------


class TestWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_rejects_missing_signature(self, client):
        response = await client.post("/v1/billing/webhook", content=b"{}")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_invalid_signature(self, client):
        with patch("core.config.settings.stripe_webhook_secret", "whsec"):
            response = await client.post(
                "/v1/billing/webhook",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=deadbeef"},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_received_for_unrelated_event(self, client):
        secret = "whsec_test"
        payload = json.dumps({"type": "invoice.paid"}).encode()
        ts = int(time.time())
        header = _sign(payload, secret, ts)

        with patch("core.config.settings.stripe_webhook_secret", secret):
            response = await client.post(
                "/v1/billing/webhook",
                content=payload,
                headers={"Stripe-Signature": header},
            )

        assert response.status_code == 200
        assert response.json() == {"received": True, "applied": False}

    @pytest.mark.asyncio
    async def test_rejects_invalid_json(self, client):
        secret = "whsec_test"
        payload = b"not-json"
        ts = int(time.time())
        header = _sign(payload, secret, ts)

        with patch("core.config.settings.stripe_webhook_secret", secret):
            response = await client.post(
                "/v1/billing/webhook",
                content=payload,
                headers={"Stripe-Signature": header},
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_applies_subscription_event(self, client):
        secret = "whsec_test"
        payload_obj = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "active",
                    "metadata": {"plan_code": "starter"},
                }
            },
        }
        payload = json.dumps(payload_obj).encode()
        ts = int(time.time())
        header = _sign(payload, secret, ts)

        with (
            patch("core.config.settings.stripe_webhook_secret", secret),
            patch(
                "modules.billing.router.apply_subscription_event",
                new_callable=AsyncMock,
            ) as apply,
        ):
            response = await client.post(
                "/v1/billing/webhook",
                content=payload,
                headers={"Stripe-Signature": header},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is True
        assert body["event_type"] == "customer.subscription.created"
        apply.assert_awaited_once()
