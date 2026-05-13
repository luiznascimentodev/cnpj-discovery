from dataclasses import dataclass

from extraction import ExtractedContact


@dataclass(frozen=True)
class ResolvedContact:
    contact_type: str
    value: str
    normalized_value: str
    label: str | None
    source: str
    confidence: int
    evidence_url: str
    source_domain: str | None


def _email_domain(value: str) -> str | None:
    if "@" not in value:
        return None
    return value.rsplit("@", 1)[1].lower()


def score_contact(candidate: ExtractedContact, *, verified_domains: set[str]) -> int:
    score = candidate.confidence
    if candidate.source_domain in verified_domains:
        score += 8
    if candidate.contact_type == "email" and _email_domain(candidate.normalized_value) in verified_domains:
        score += 10
    if candidate.contact_type == "whatsapp":
        score += 3
    if candidate.extractor in {"mailto", "tel_link", "whatsapp_link", "social_link"}:
        score += 4
    return min(score, 100)


def resolve_contacts(
    candidates: list[ExtractedContact],
    *,
    verified_domains: set[str],
    public_normalized_values: set[str],
    min_confidence: int = 80,
) -> list[ResolvedContact]:
    deduped: dict[tuple[str, str], ResolvedContact] = {}
    for candidate in candidates:
        if candidate.normalized_value in public_normalized_values:
            continue
        if candidate.source_domain not in verified_domains:
            continue

        confidence = score_contact(candidate, verified_domains=verified_domains)
        if confidence < min_confidence:
            continue

        resolved = ResolvedContact(
            contact_type=candidate.contact_type,
            value=candidate.value,
            normalized_value=candidate.normalized_value,
            label=candidate.label,
            source="official_site" if candidate.source_domain in verified_domains else "crawler",
            confidence=confidence,
            evidence_url=candidate.source_url,
            source_domain=candidate.source_domain,
        )
        key = (resolved.contact_type, resolved.normalized_value)
        current = deduped.get(key)
        if not current or resolved.confidence > current.confidence:
            deduped[key] = resolved

    return sorted(deduped.values(), key=lambda item: (-item.confidence, item.contact_type, item.normalized_value))
