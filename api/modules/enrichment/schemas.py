from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EnrichmentDomain(BaseModel):
    domain: str
    homepage_url: Optional[str] = None
    source: str
    confidence: int = Field(ge=0, le=100)
    status: Literal["candidate", "verified", "rejected", "stale"]
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class EnrichmentContact(BaseModel):
    contact_type: Literal["email", "phone", "whatsapp", "website", "social"]
    value: str
    normalized_value: str
    label: Optional[str] = None
    source: str
    confidence: int = Field(ge=0, le=100)
    evidence_url: Optional[str] = None
    source_domain: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class PaidEnrichmentDetail(BaseModel):
    cnpj: str
    status: Literal["not_enriched", "no_public_data", "done"]
    domains: list[EnrichmentDomain] = Field(default_factory=list)
    contacts: list[EnrichmentContact] = Field(default_factory=list)

