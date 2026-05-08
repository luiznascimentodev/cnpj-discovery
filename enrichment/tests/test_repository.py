from datetime import datetime, timezone

import pytest

from api.schemas import AccessAuditEvent, EnqueueTargetRequest
from repository import (
    enqueue_target,
    fetch_enrichment_detail,
    fetch_evidence,
    insert_access_audit,
)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self, fetch_results=None):
        self.fetch_results = list(fetch_results or [])
        self.fetch_calls = []
        self.execute_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.fetch_results.pop(0)

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "INSERT 0 1"


class TestRepository:
    @pytest.mark.asyncio
    async def test_enqueue_target_upserts_pending_target(self):
        conn = FakeConnection()
        pool = FakePool(conn)
        payload = EnqueueTargetRequest(reason="manual", priority=70)

        queued = await enqueue_target(pool, "12.345.678/0001-90", payload)

        assert queued == "12345678000190"
        assert conn.execute_calls[0][1] == ("12345678", "0001", "90", 70, "manual")

    @pytest.mark.asyncio
    async def test_fetch_enrichment_detail_maps_rows(self):
        now = datetime.now(timezone.utc)
        conn = FakeConnection(
            fetch_results=[
                [
                    {
                        "domain": "example.com.br",
                        "homepage_url": "https://example.com.br",
                        "source": "rf_email_domain",
                        "confidence": 90,
                        "status": "verified",
                        "first_seen": now,
                        "last_seen": now,
                    }
                ],
                [
                    {
                        "contact_type": "email",
                        "value": "contato@example.com.br",
                        "normalized_value": "contato@example.com.br",
                        "label": "contact",
                        "source": "official_site",
                        "confidence": 94,
                        "evidence_url": "https://example.com.br/contato",
                        "source_domain": "example.com.br",
                        "first_seen": now,
                        "last_seen": now,
                    }
                ],
            ]
        )

        detail = await fetch_enrichment_detail(FakePool(conn), "12345678000190")

        assert detail.status == "done"
        assert detail.domains[0].domain == "example.com.br"
        assert detail.contacts[0].value == "contato@example.com.br"

    @pytest.mark.asyncio
    async def test_fetch_enrichment_detail_marks_empty_result_not_enriched(self):
        conn = FakeConnection(fetch_results=[[], []])

        detail = await fetch_enrichment_detail(FakePool(conn), "12345678000190")

        assert detail.status == "not_enriched"
        assert detail.contacts == []

    @pytest.mark.asyncio
    async def test_fetch_evidence_bounds_limit_and_maps_rows(self):
        now = datetime.now(timezone.utc)
        conn = FakeConnection(
            fetch_results=[
                [
                    {
                        "id": 1,
                        "source": "official_site",
                        "source_url": "https://example.com.br",
                        "source_domain": "example.com.br",
                        "extractor": "mailto",
                        "evidence_excerpt": "contato@example.com.br",
                        "observed_at": now,
                    }
                ]
            ]
        )

        evidence = await fetch_evidence(FakePool(conn), "12345678000190", limit=999)

        assert evidence.items[0].id == 1
        assert conn.fetch_calls[0][1][-1] == 500

    @pytest.mark.asyncio
    async def test_insert_access_audit_with_cnpj(self):
        conn = FakeConnection()
        event = AccessAuditEvent(
            account_id="acct",
            request_id="req",
            route="/v1/enrichment/{cnpj}",
            action="read",
            cnpj="12345678000190",
            record_count=2,
        )

        await insert_access_audit(FakePool(conn), event)

        assert conn.execute_calls[0][1][:7] == (
            "acct",
            "req",
            "/v1/enrichment/{cnpj}",
            "read",
            "12345678",
            "0001",
            "90",
        )

    @pytest.mark.asyncio
    async def test_insert_access_audit_without_cnpj(self):
        conn = FakeConnection()
        event = AccessAuditEvent(
            account_id="acct",
            route="/v1/paid/export",
            action="export",
            filter_hash="hash",
            record_count=10,
        )

        await insert_access_audit(FakePool(conn), event)

        assert conn.execute_calls[0][1] == (
            "acct",
            None,
            "/v1/paid/export",
            "export",
            "hash",
            10,
        )

