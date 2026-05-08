from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlparse

from rf_baseline import BaselineContact

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")

LEGAL_SUFFIXES = frozenset(
    {
        "comercio",
        "eireli",
        "empresa",
        "empreendimentos",
        "industria",
        "ltda",
        "me",
        "sa",
        "servicos",
    }
)

BRAND_STOPWORDS = frozenset({"de", "da", "das", "do", "dos", "e"})


@dataclass(frozen=True)
class DomainCandidate:
    domain: str
    source: str
    confidence: int
    homepage_url: str | None = None
    reason: str | None = None


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlparse(value if "://" in value else f"https://{value}")
    domain = (parsed.hostname or "").lower().strip(".")
    if domain.startswith("www."):
        domain = domain[4:]

    if not _DOMAIN_RE.match(domain):
        return None
    return domain


def _ascii_slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
    tokens = [
        token
        for token in _TOKEN_RE.findall(ascii_text)
        if token not in LEGAL_SUFFIXES and token not in BRAND_STOPWORDS
    ]
    return "".join(tokens)


def generate_brand_slugs(legal_name: str | None, trade_name: str | None) -> list[str]:
    seen: set[str] = set()
    slugs: list[str] = []
    for name in (trade_name, legal_name):
        slug = _ascii_slug(name or "")
        if len(slug) >= 3 and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def domains_from_rf_email(email_contact: BaselineContact | None) -> list[DomainCandidate]:
    if not email_contact or email_contact.contact_type != "email":
        return []

    if email_contact.classification != "corporate_domain":
        return []

    domain = normalize_domain(email_contact.normalized_value.rsplit("@", 1)[1])
    if not domain:
        return []

    return [
        DomainCandidate(
            domain=domain,
            source="rf_email_domain",
            confidence=90,
            homepage_url=f"https://{domain}",
            reason="corporate email domain from public RF data",
        )
    ]


def domains_from_brand_slugs(slugs: list[str]) -> list[DomainCandidate]:
    candidates: list[DomainCandidate] = []
    for slug in slugs:
        for suffix, confidence in ((".com.br", 45), (".com", 35)):
            domain = normalize_domain(f"{slug}{suffix}")
            if domain:
                candidates.append(
                    DomainCandidate(
                        domain=domain,
                        source="brand_slug",
                        confidence=confidence,
                        homepage_url=f"https://{domain}",
                        reason="generated from company names",
                    )
                )
    return candidates


def discover_domain_candidates(
    *,
    legal_name: str | None,
    trade_name: str | None,
    rf_email: BaselineContact | None,
) -> list[DomainCandidate]:
    deduped: dict[str, DomainCandidate] = {}
    for candidate in [*domains_from_rf_email(rf_email), *domains_from_brand_slugs(generate_brand_slugs(legal_name, trade_name))]:
        current = deduped.get(candidate.domain)
        if not current or candidate.confidence > current.confidence:
            deduped[candidate.domain] = candidate
    return sorted(deduped.values(), key=lambda item: (-item.confidence, item.domain))
