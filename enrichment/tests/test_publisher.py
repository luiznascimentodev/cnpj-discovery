import pytest

from resolution import ResolvedContact
from resolver.publisher import (
    PUBLISH_THRESHOLD,
    PublishStats,
    publish_resolved_contacts,
)


class FakeConnection:
    def __init__(self, evidence_ids):
        self._evidence_ids = list(evidence_ids)
        self.fetchval_calls = []
        self.execute_calls = []

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self._evidence_ids.pop(0)

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _contact(**overrides) -> ResolvedContact:
    base = {
        "contact_type": "email",
        "value": "contato@acme.com.br",
        "normalized_value": "contato@acme.com.br",
        "label": "Contato",
        "source": "official_site",
        "confidence": 90,
        "evidence_url": "https://acme.com.br/contato",
        "source_domain": "acme.com.br",
    }
    base.update(overrides)
    return ResolvedContact(**base)


class TestPublishResolvedContacts:
    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_input(self):
        conn = FakeConnection(evidence_ids=[])

        stats = await publish_resolved_contacts(
            conn,
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            crawl_page_id=99,
            contacts=[],
        )

        assert stats == PublishStats(0, 0, 0)
        assert conn.fetchval_calls == []
        assert conn.execute_calls == []

    @pytest.mark.asyncio
    async def test_publishes_high_confidence_contact(self):
        conn = FakeConnection(evidence_ids=[42])

        stats = await publish_resolved_contacts(
            conn,
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            crawl_page_id=11,
            contacts=[_contact(confidence=PUBLISH_THRESHOLD + 5)],
        )

        assert stats.evidence_written == 1
        assert stats.raw_candidates_written == 1
        assert stats.contacts_published == 1

        evidence_args = conn.fetchval_calls[0][1]
        assert evidence_args[0:3] == ("12345678", "0001", "90")
        assert evidence_args[6] == 11  # crawl_page_id
        assert evidence_args[7] == "resolver"

        candidate_args = conn.execute_calls[0][1]
        assert candidate_args[0] == 42  # evidence_id
        assert candidate_args[2] == "contato@acme.com.br"

        published_args = conn.execute_calls[1][1]
        assert published_args[10] == 42  # evidence_id linked
        assert published_args[9] == "active"

    @pytest.mark.asyncio
    async def test_holds_low_confidence_as_candidate_only(self):
        conn = FakeConnection(evidence_ids=[7])

        stats = await publish_resolved_contacts(
            conn,
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            crawl_page_id=None,
            contacts=[_contact(confidence=70)],
        )

        assert stats.contacts_published == 0
        assert stats.raw_candidates_written == 1
        # apenas evidence + raw_candidate; NÃO insere em enriched_contacts
        assert len(conn.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_truncates_label_excerpt_to_500(self):
        conn = FakeConnection(evidence_ids=[1])
        long_label = "x" * 1000

        await publish_resolved_contacts(
            conn,
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            crawl_page_id=None,
            contacts=[_contact(label=long_label, confidence=PUBLISH_THRESHOLD)],
        )

        evidence_args = conn.fetchval_calls[0][1]
        evidence_excerpt = evidence_args[9]
        assert len(evidence_excerpt) == 500
