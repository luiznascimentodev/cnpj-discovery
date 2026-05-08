from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from domain_discovery import normalize_domain

_EMAIL_RE = re.compile(r"(?<![\w.+-])([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?55[\s().-]*)?(?:\(?[1-9][0-9]\)?[\s.-]*)?(?:9[\s.-]*)?[0-9]{4}[\s.-]*[0-9]{4}(?!\d)"
)
_NON_DIGIT_RE = re.compile(r"\D+")
_SKIP_EMAIL_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js")
_SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}


@dataclass(frozen=True)
class ExtractedContact:
    contact_type: str
    value: str
    normalized_value: str
    label: str | None
    context: str | None
    confidence: int
    source_url: str
    source_domain: str | None
    extractor: str


class _ContactHtmlParser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.links: list[tuple[str, str | None]] = []
        self.text_parts: list[str] = []
        self._current_link: str | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if tag == "a":
            self._current_link = attrs_dict.get("href")
            if self._current_link:
                self.links.append((urljoin(self.source_url, self._current_link), None))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "a":
            self._current_link = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.text_parts.append(text)
        if self._current_link and self.links:
            href, label = self.links[-1]
            self.links[-1] = (href, text if label is None else f"{label} {text}")


def normalize_email(value: str) -> str | None:
    normalized = value.strip().strip(".,;:()[]{}<>").lower()
    if normalized.endswith(_SKIP_EMAIL_SUFFIXES):
        return None
    if not _EMAIL_RE.fullmatch(normalized):
        return None
    return normalized


def normalize_phone(value: str) -> str | None:
    digits = _NON_DIGIT_RE.sub("", unquote(value))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) not in {10, 11}:
        return None
    if len(set(digits)) <= 2:
        return None
    return digits


def _source_domain(source_url: str) -> str | None:
    return normalize_domain(urlparse(source_url).hostname or source_url)


def _dedupe(contacts: list[ExtractedContact]) -> list[ExtractedContact]:
    result: dict[tuple[str, str], ExtractedContact] = {}
    for contact in contacts:
        key = (contact.contact_type, contact.normalized_value)
        current = result.get(key)
        if not current or contact.confidence > current.confidence:
            result[key] = contact
    return sorted(result.values(), key=lambda item: (item.contact_type, item.normalized_value))


def _email_contacts(text: str, *, source_url: str, source_domain: str | None, extractor: str) -> list[ExtractedContact]:
    contacts: list[ExtractedContact] = []
    for match in _EMAIL_RE.finditer(text):
        normalized = normalize_email(match.group(1))
        if normalized:
            contacts.append(
                ExtractedContact(
                    contact_type="email",
                    value=match.group(1),
                    normalized_value=normalized,
                    label=None,
                    context=match.group(0),
                    confidence=78 if extractor == "visible_text" else 88,
                    source_url=source_url,
                    source_domain=source_domain,
                    extractor=extractor,
                )
            )
    return contacts


def _phone_contact(
    raw_value: str,
    *,
    contact_type: str,
    source_url: str,
    source_domain: str | None,
    extractor: str,
    label: str | None = None,
) -> ExtractedContact | None:
    normalized = normalize_phone(raw_value)
    if not normalized:
        return None
    return ExtractedContact(
        contact_type=contact_type,
        value=raw_value,
        normalized_value=normalized,
        label=label,
        context=label,
        confidence=92 if extractor in {"whatsapp_link", "tel_link"} else 70,
        source_url=source_url,
        source_domain=source_domain,
        extractor=extractor,
    )


def _social_contact(href: str, *, source_url: str, source_domain: str | None, label: str | None) -> ExtractedContact | None:
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in _SOCIAL_HOSTS:
        return None

    normalized = parsed._replace(fragment="", query="").geturl().rstrip("/")
    return ExtractedContact(
        contact_type="social",
        value=href,
        normalized_value=normalized,
        label=label,
        context=label,
        confidence=82,
        source_url=source_url,
        source_domain=source_domain,
        extractor="social_link",
    )


def extract_contacts_from_html(html: str, *, source_url: str) -> list[ExtractedContact]:
    parser = _ContactHtmlParser(source_url)
    parser.feed(html)
    source_domain = _source_domain(source_url)
    contacts: list[ExtractedContact] = []

    for href, label in parser.links:
        parsed = urlparse(href)
        if parsed.scheme == "mailto":
            contacts.extend(
                _email_contacts(
                    unquote(parsed.path),
                    source_url=source_url,
                    source_domain=source_domain,
                    extractor="mailto",
                )
            )
        elif parsed.scheme == "tel":
            contact = _phone_contact(
                parsed.path,
                contact_type="phone",
                source_url=source_url,
                source_domain=source_domain,
                extractor="tel_link",
                label=label,
            )
            if contact:
                contacts.append(contact)
        elif parsed.hostname in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
            phone_value = parsed.path
            query_phone = parse_qs(parsed.query).get("phone", [None])[0]
            contact = _phone_contact(
                query_phone or phone_value,
                contact_type="whatsapp",
                source_url=source_url,
                source_domain=source_domain,
                extractor="whatsapp_link",
                label=label,
            )
            if contact:
                contacts.append(contact)
        else:
            social = _social_contact(
                href,
                source_url=source_url,
                source_domain=source_domain,
                label=label,
            )
            if social:
                contacts.append(social)

    visible_text = " ".join(parser.text_parts)
    contacts.extend(
        _email_contacts(
            visible_text,
            source_url=source_url,
            source_domain=source_domain,
            extractor="visible_text",
        )
    )
    for match in _PHONE_RE.finditer(visible_text):
        contact = _phone_contact(
            match.group(0),
            contact_type="phone",
            source_url=source_url,
            source_domain=source_domain,
            extractor="visible_text",
        )
        if contact:
            contacts.append(contact)

    return _dedupe(contacts)
