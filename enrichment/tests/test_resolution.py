from extraction import ExtractedContact
from resolution import resolve_contacts, score_contact


def make_candidate(**overrides):
    values = {
        "contact_type": "email",
        "value": "contato@example.com.br",
        "normalized_value": "contato@example.com.br",
        "label": "Contato",
        "context": "Contato",
        "confidence": 78,
        "source_url": "https://example.com.br/contato",
        "source_domain": "example.com.br",
        "extractor": "visible_text",
    }
    values.update(overrides)
    return ExtractedContact(**values)


class TestResolution:
    def test_score_contact_boosts_verified_domain_and_extractor(self):
        candidate = make_candidate(extractor="mailto")

        assert score_contact(candidate, verified_domains={"example.com.br"}) == 100

    def test_score_contact_boosts_whatsapp(self):
        candidate = make_candidate(
            contact_type="whatsapp",
            value="5511912345678",
            normalized_value="11912345678",
            confidence=92,
            extractor="whatsapp_link",
        )

        assert score_contact(candidate, verified_domains=set()) == 99

    def test_score_contact_handles_email_without_domain(self):
        candidate = make_candidate(normalized_value="invalid")

        assert score_contact(candidate, verified_domains={"example.com.br"}) == 86

    def test_resolve_contacts_filters_public_values_and_low_confidence(self):
        resolved = resolve_contacts(
            [
                make_candidate(normalized_value="public@example.com.br"),
                make_candidate(value="low@example.net", normalized_value="low@example.net", confidence=40),
            ],
            verified_domains={"example.com.br"},
            public_normalized_values={"public@example.com.br"},
            min_confidence=80,
        )

        assert resolved == []

    def test_resolve_contacts_requires_verified_source_and_dedupes_best(self):
        low = make_candidate(confidence=78, extractor="visible_text")
        high = make_candidate(confidence=88, extractor="mailto")
        external = make_candidate(
            value="social",
            normalized_value="https://instagram.com/example",
            contact_type="social",
            confidence=82,
            source_domain="other.com",
            extractor="social_link",
        )

        resolved = resolve_contacts(
            [low, high, external],
            verified_domains={"example.com.br"},
            public_normalized_values=set(),
            min_confidence=80,
        )

        assert [contact.normalized_value for contact in resolved] == [
            "contato@example.com.br",
        ]
        assert resolved[0].source == "official_site"

    def test_resolve_contacts_filters_unverified_high_confidence_contacts(self):
        resolved = resolve_contacts(
            [
                make_candidate(
                    value="social",
                    normalized_value="https://instagram.com/example",
                    contact_type="social",
                    confidence=100,
                    source_domain="other.com",
                    extractor="social_link",
                )
            ],
            verified_domains={"example.com.br"},
            public_normalized_values=set(),
            min_confidence=80,
        )

        assert resolved == []
