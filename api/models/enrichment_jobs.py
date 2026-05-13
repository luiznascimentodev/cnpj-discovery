from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from models.filters import ProspectingFilters, normalize_cnpj


JobSourceType = Literal["selection", "filter"]
JobStatus = Literal[
    "draft",
    "estimating",
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "cancelled",
    "failed",
]
JobItemStatus = Literal[
    "pending",
    "leased",
    "cache_hit",
    "enriched",
    "no_public_contact",
    "skipped_inactive",
    "failed_retryable",
    "failed_terminal",
    "cancelled",
]


class EnrichmentEstimateRequest(BaseModel):
    cnpjs: list[str] | None = Field(None, min_length=1, max_length=50_000)
    filters: ProspectingFilters | None = None
    max_items: int = Field(5_000, ge=1, le=50_000)
    stale_after_days: int = Field(180, ge=1, le=365)

    @model_validator(mode="after")
    def validate_source(self) -> "EnrichmentEstimateRequest":
        if bool(self.cnpjs) == bool(self.filters):
            raise ValueError("Informe cnpjs ou filters, mas não ambos")
        if self.cnpjs:
            normalized = []
            seen = set()
            for cnpj in self.cnpjs:
                value = normalize_cnpj(cnpj)
                if len(value) != 14 or not value.isdigit():
                    raise ValueError("Todos os CNPJs devem ter 14 dígitos numéricos")
                if value not in seen:
                    normalized.append(value)
                    seen.add(value)
            self.cnpjs = normalized[: self.max_items]
        return self

    @property
    def source_type(self) -> JobSourceType:
        return "selection" if self.cnpjs else "filter"


class EnrichmentJobCreateRequest(EnrichmentEstimateRequest):
    confirm_estimate: bool = True


class EnrichmentEstimateResponse(BaseModel):
    source_type: JobSourceType
    requested_count: int
    eligible_count: int
    cache_hit_count: int
    new_count: int
    skipped_inactive_count: int
    cost_credits: int
    estimated_seconds_min: int
    estimated_seconds_max: int


class EnrichmentJobResponse(EnrichmentEstimateResponse):
    job_id: int
    status: JobStatus
    idempotency_key: str | None = None
    created_at: datetime | None = None


class EnrichmentJobSummary(BaseModel):
    id: int
    status: JobStatus
    source_type: JobSourceType
    requested_count: int
    accepted_count: int
    cache_hit_count: int
    skipped_count: int
    failed_count: int
    ready_count: int
    cost_credits: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class EnrichmentJobItem(BaseModel):
    cnpj: str
    status: JobItemStatus
    result_source: str | None = None
    attempts: int = 0
    last_error: str | None = None
    updated_at: datetime | None = None


class EnrichmentJobItemsResponse(BaseModel):
    job_id: int
    items: list[EnrichmentJobItem]


class EnrichmentJobListResponse(BaseModel):
    jobs: list[EnrichmentJobSummary]


class EnrichmentJobCancelResponse(BaseModel):
    job_id: int
    cancelled_items: int
