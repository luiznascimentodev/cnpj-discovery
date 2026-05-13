from dataclasses import dataclass
import re

_EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
_NON_DIGIT_RE = re.compile(r"\D+")

PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "bol.com.br",
        "gmail.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "outlook.com",
        "terra.com.br",
        "uol.com.br",
        "yahoo.com",
        "yahoo.com.br",
    }
)


@dataclass(frozen=True)
class BaselineContact:
    contact_type: str
    value: str
    normalized_value: str
    classification: str


def normalize_rf_email(value: str | None) -> BaselineContact | None:
    if not value:
        return None

    normalized = value.strip().lower()
    if not normalized or not _EMAIL_RE.match(normalized):
        return None

    domain = normalized.rsplit("@", 1)[1]
    classification = "public_provider" if domain in PUBLIC_EMAIL_DOMAINS else "corporate_domain"
    return BaselineContact(
        contact_type="email",
        value=normalized,
        normalized_value=normalized,
        classification=classification,
    )


def normalize_rf_phone(ddd: str | None, phone: str | None) -> BaselineContact | None:
    ddd_digits = _NON_DIGIT_RE.sub("", ddd or "")
    phone_digits = _NON_DIGIT_RE.sub("", phone or "")
    if not ddd_digits or not phone_digits:
        return None

    normalized = f"{ddd_digits}{phone_digits}"
    if len(normalized) not in {10, 11}:
        return None

    return BaselineContact(
        contact_type="phone",
        value=f"({ddd_digits}) {phone_digits}",
        normalized_value=normalized,
        classification="rf_public",
    )


def public_normalized_values(*contacts: BaselineContact | None) -> set[str]:
    return {contact.normalized_value for contact in contacts if contact is not None}
