from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import api.auth as auth
from api.auth import (
    AccountContext,
    AuthenticatedService,
    is_valid_internal_api_key,
    require_account_context,
    require_internal_api_key,
)
from api.schemas import (
    AccessAuditEvent,
    EnqueueTargetRequest,
    EnqueueTargetResponse,
    EnrichmentContact,
    EnrichmentDetailResponse,
    EnrichmentDomain,
    EvidenceItem,
    EvidenceResponse,
    ServiceStatusResponse,
    normalize_cnpj,
    split_cnpj,
)
from config import DEFAULT_INTERNAL_API_KEY


class TestAuth:
    def test_is_valid_internal_api_key_accepts_match(self):
        assert is_valid_internal_api_key("secret", "secret") is True

    def test_is_valid_internal_api_key_rejects_missing_or_mismatch(self):
        assert is_valid_internal_api_key(None, "secret") is False
        assert is_valid_internal_api_key("", "secret") is False
        assert is_valid_internal_api_key("wrong", "secret") is False

    @pytest.mark.asyncio
    async def test_require_internal_api_key_accepts_valid_key(self):
        original_key = auth.settings.enrichment_api_key
        original_environment = auth.settings.environment
        auth.settings.enrichment_api_key = "secret"
        auth.settings.environment = "development"
        try:
            result = await require_internal_api_key("secret")
            assert result == AuthenticatedService()
        finally:
            auth.settings.enrichment_api_key = original_key
            auth.settings.environment = original_environment

    @pytest.mark.asyncio
    async def test_require_internal_api_key_rejects_invalid_key(self):
        original_key = auth.settings.enrichment_api_key
        original_environment = auth.settings.environment
        auth.settings.enrichment_api_key = "secret"
        auth.settings.environment = "development"
        try:
            with pytest.raises(HTTPException) as exc:
                await require_internal_api_key("wrong")
            assert exc.value.status_code == 401
        finally:
            auth.settings.enrichment_api_key = original_key
            auth.settings.environment = original_environment

    @pytest.mark.asyncio
    async def test_require_internal_api_key_rejects_insecure_production_config(self):
        original_key = auth.settings.enrichment_api_key
        original_environment = auth.settings.environment
        auth.settings.enrichment_api_key = DEFAULT_INTERNAL_API_KEY
        auth.settings.environment = "production"
        try:
            with pytest.raises(HTTPException) as exc:
                await require_internal_api_key(DEFAULT_INTERNAL_API_KEY)
            assert exc.value.status_code == 503
        finally:
            auth.settings.enrichment_api_key = original_key
            auth.settings.environment = original_environment

    @pytest.mark.asyncio
    async def test_require_account_context_strips_account_and_keeps_request(self):
        context = await require_account_context(" account-1 ", "req-1")
        assert context == AccountContext(account_id="account-1", request_id="req-1")

    @pytest.mark.asyncio
    async def test_require_account_context_rejects_missing_account(self):
        with pytest.raises(HTTPException) as exc:
            await require_account_context(" ", None)
        assert exc.value.status_code == 400


class TestSchemas:
    def test_normalize_cnpj_strips_punctuation(self):
        assert normalize_cnpj("12.345.678/0001-90") == "12345678000190"

    def test_normalize_cnpj_rejects_invalid_value(self):
        with pytest.raises(ValueError, match="14 digits"):
            normalize_cnpj("123")

    def test_split_cnpj(self):
        assert split_cnpj("12.345.678/0001-90") == ("12345678", "0001", "90")

    def test_service_status_response(self):
        assert ServiceStatusResponse(status="ok", version="0.1.0").status == "ok"

    def test_enqueue_request_defaults_priority(self):
        payload = EnqueueTargetRequest(reason="manual")
        assert payload.priority == 50

    def test_enqueue_request_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            EnqueueTargetRequest(reason="")

    def test_enqueue_response_normalizes_cnpj(self):
        response = EnqueueTargetResponse(
            cnpj="12.345.678/0001-90",
            status="queued",
            reason="manual",
            priority=80,
        )
        assert response.cnpj == "12345678000190"

    def test_enrichment_domain(self):
        now = datetime.now(timezone.utc)
        domain = EnrichmentDomain(
            domain="example.com.br",
            homepage_url="https://example.com.br",
            source="rf_email_domain",
            confidence=90,
            status="verified",
            first_seen=now,
            last_seen=now,
        )
        assert domain.confidence == 90

    def test_enrichment_contact(self):
        contact = EnrichmentContact(
            contact_type="email",
            value="contato@example.com.br",
            normalized_value="contato@example.com.br",
            source="official_site",
            confidence=95,
        )
        assert contact.contact_type == "email"

    def test_enrichment_detail_response_normalizes_cnpj(self):
        response = EnrichmentDetailResponse(
            cnpj="12.345.678/0001-90",
            status="not_enriched",
        )
        assert response.cnpj == "12345678000190"

    def test_evidence_item_and_response(self):
        item = EvidenceItem(
            id=1,
            source="official_site",
            extractor="mailto",
        )
        response = EvidenceResponse(cnpj="12.345.678/0001-90", items=[item])
        assert response.items[0].extractor == "mailto"

    def test_access_audit_event_normalizes_optional_cnpj(self):
        event = AccessAuditEvent(
            account_id="acct",
            route="/v1/enrichment/{cnpj}",
            action="read",
            cnpj="12.345.678/0001-90",
            record_count=1,
        )
        assert event.cnpj == "12345678000190"

    def test_access_audit_event_allows_missing_cnpj(self):
        event = AccessAuditEvent(
            account_id="acct",
            route="/v1/paid/export",
            action="export",
        )
        assert event.cnpj is None

