"""Extract phone/email/website contacts from Instagram and Facebook profile pages.

Uses static HTML only — no Playwright needed. Meta tags, JSON-LD schema blocks,
tel:/mailto: links, and visible text provide enough structured data for most
business pages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from extraction import ExtractedContact, extract_contacts_from_html, normalize_phone, _source_domain, _dedupe

_SOCIAL_HOSTS_IGNORE = {
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "wa.me",
    "api.whatsapp.com",
    "web.whatsapp.com",
}

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

_META_CONTENT_RE = re.compile(
    r'<meta[^>]+(?:name=["\']description["\'][^>]+content|content[^>]+name=["\']description["\'])[^>]*content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)

# Simpler meta description extractor — handles both attribute orderings
_META_DESC_RE = re.compile(
    r'<meta\b[^>]*\bname=["\']description["\'][^>]*\bcontent=["\']([^"\']*)["\']'
    r'|<meta\b[^>]*\bcontent=["\']([^"\']*)["\'][^>]*\bname=["\']description["\']',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SocialExtractResult:
    profile_url: str
    contacts: list[ExtractedContact]


def _extract_meta_description(html: str) -> str:
    """Return the content of the first <meta name="description"> tag, or empty string."""
    match = _META_DESC_RE.search(html)
    if not match:
        return ""
    return match.group(1) or match.group(2) or ""


def _extract_json_ld_contacts(
    html: str,
    *,
    profile_url: str,
) -> list[ExtractedContact]:
    """Parse JSON-LD blocks and extract url/telephone from Organisation/LocalBusiness."""
    source_domain = _source_domain(profile_url)
    contacts: list[ExtractedContact] = []

    for script_match in _JSON_LD_RE.finditer(html):
        raw = script_match.group(1).strip()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue

        # Normalise: some pages emit an array of schemas
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            schema_type = item.get("@type", "")
            if schema_type not in {"Organization", "LocalBusiness", "Store", "Restaurant", "NGO"}:
                continue

            # Extract website URL
            url = item.get("url") or item.get("sameAs")
            if isinstance(url, str) and url.strip():
                url = url.strip()
                parsed = urlparse(url)
                host = (parsed.hostname or "").lower().lstrip("www.")
                if host and host not in _SOCIAL_HOSTS_IGNORE:
                    normalized = url.rstrip("/")
                    contacts.append(
                        ExtractedContact(
                            contact_type="website",
                            value=url,
                            normalized_value=normalized,
                            label=None,
                            context=None,
                            confidence=82,
                            source_url=profile_url,
                            source_domain=source_domain,
                            extractor="json_ld",
                        )
                    )

            # Extract telephone
            telephone = item.get("telephone")
            if isinstance(telephone, str) and telephone.strip():
                normalized_phone = normalize_phone(telephone.strip())
                if normalized_phone:
                    contacts.append(
                        ExtractedContact(
                            contact_type="phone",
                            value=telephone.strip(),
                            normalized_value=normalized_phone,
                            label=None,
                            context=None,
                            confidence=82,
                            source_url=profile_url,
                            source_domain=source_domain,
                            extractor="json_ld",
                        )
                    )

    return contacts


def _filter_social_websites(contacts: list[ExtractedContact]) -> list[ExtractedContact]:
    """Remove website contacts pointing to social platform domains."""
    result = []
    for contact in contacts:
        if contact.contact_type != "website":
            result.append(contact)
            continue
        parsed = urlparse(contact.normalized_value)
        host = (parsed.hostname or "").lower().lstrip("www.")
        if host not in _SOCIAL_HOSTS_IGNORE:
            result.append(contact)
    return result


def _extract_from_social_html(html: str, *, profile_url: str) -> SocialExtractResult:
    """Shared extraction logic for Instagram and Facebook profile pages."""
    if not html or not html.strip():
        return SocialExtractResult(profile_url=profile_url, contacts=[])

    contacts: list[ExtractedContact] = []

    # 1. Extract from JSON-LD blocks (Organisation/LocalBusiness schema)
    contacts.extend(_extract_json_ld_contacts(html, profile_url=profile_url))

    # 2. Extract from regular HTML (links, visible text, mailto:, tel:)
    contacts.extend(extract_contacts_from_html(html, source_url=profile_url))

    # 3. Extract from meta description — build a fake mini-HTML so extraction
    #    can run its regexes on the description content text.
    meta_desc = _extract_meta_description(html)
    if meta_desc:
        source_domain = _source_domain(profile_url)
        # Re-use extract_contacts_from_html on a synthetic fragment containing
        # just the description text as visible body text.
        pseudo_html = f"<html><body>{meta_desc}</body></html>"
        meta_contacts = extract_contacts_from_html(pseudo_html, source_url=profile_url)
        contacts.extend(meta_contacts)

    # 4. Filter social platform domains from website contacts
    contacts = _filter_social_websites(contacts)

    # 5. Deduplicate by (contact_type, normalized_value), keeping highest confidence
    deduped = _dedupe(contacts)

    return SocialExtractResult(profile_url=profile_url, contacts=deduped)


def extract_contacts_from_instagram_html(
    html: str,
    *,
    profile_url: str,
) -> SocialExtractResult:
    """Extract contacts from a static Instagram profile page HTML."""
    return _extract_from_social_html(html, profile_url=profile_url)


def extract_contacts_from_facebook_html(
    html: str,
    *,
    profile_url: str,
) -> SocialExtractResult:
    """Extract contacts from a static Facebook profile page HTML."""
    return _extract_from_social_html(html, profile_url=profile_url)
