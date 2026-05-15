import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CNPJ_STRIP_RE = re.compile(r"[.\-/\s]")

ContactType = Literal["email", "phone", "whatsapp", "website", "social"]
EnrichmentStatus = Literal["not_enriched", "no_public_data", "done"]


def normalize_cnpj(value: str) -> str:
    normalized = _CNPJ_STRIP_RE.sub("", value)
    if len(normalized) != 14 or not normalized.isdigit():
        raise ValueError("CNPJ must have exactly 14 digits")
    return normalized


def split_cnpj(value: str) -> tuple[str, str, str]:
    normalized = normalize_cnpj(value)
    return normalized[:8], normalized[8:12], normalized[12:]


class ServiceStatusResponse(BaseModel):
    status: Literal["ok"]
    version: str


class EnqueueTargetRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=80)
    priority: int = Field(default=50, ge=0, le=100)


class EnqueueTargetResponse(BaseModel):
    cnpj: str
    status: Literal["queued"]
    reason: str
    priority: int

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        return normalize_cnpj(value)


class EnrichmentDomain(BaseModel):
    domain: str
    homepage_url: str | None = None
    source: str
    confidence: int = Field(ge=0, le=100)
    status: Literal["candidate", "verified", "rejected", "stale"]
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class EnrichmentContact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_type: ContactType
    value: str
    normalized_value: str
    label: str | None = None
    source: str
    confidence: int = Field(ge=0, le=100)
    evidence_url: str | None = None
    source_domain: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class EnrichmentDetailResponse(BaseModel):
    cnpj: str
    status: EnrichmentStatus
    domains: list[EnrichmentDomain] = Field(default_factory=list)
    contacts: list[EnrichmentContact] = Field(default_factory=list)

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        return normalize_cnpj(value)


class EvidenceItem(BaseModel):
    id: int
    source: str
    source_url: str | None = None
    source_domain: str | None = None
    extractor: str
    evidence_excerpt: str | None = None
    observed_at: datetime | None = None


class EvidenceResponse(BaseModel):
    cnpj: str
    items: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        return normalize_cnpj(value)


class AccessAuditEvent(BaseModel):
    account_id: str
    request_id: str | None = None
    route: str
    action: Literal["read", "export", "feedback", "admin"]
    cnpj: str | None = None
    filter_hash: str | None = None
    record_count: int | None = Field(default=None, ge=0)

    @field_validator("cnpj")
    @classmethod
    def validate_optional_cnpj(cls, value: str | None) -> str | None:
        return normalize_cnpj(value) if value else value


class SuppressionRequestPayload(BaseModel):
    cnpj: str
    contact_type: ContactType
    normalized_value: str = Field(min_length=1, max_length=320)
    reason: str = Field(min_length=1, max_length=500)
    requested_by: str = Field(min_length=1, max_length=120)

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        return normalize_cnpj(value)


class SuppressionResponse(BaseModel):
    cnpj: str
    contact_type: ContactType
    normalized_value: str
    suppressed: Literal[True] = True


class FeedbackPayload(BaseModel):
    feedback: Literal["valid", "invalid", "bounced", "not_company"]
    note: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    contact_id: int
    feedback: Literal["valid", "invalid", "bounced", "not_company"]
    new_status: Literal["active", "rejected", "suppressed"]
    confidence: int = Field(ge=0, le=100)
