"""Centralized error codes and factory for pipeline module."""
from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(str, Enum):
    PIPELINE_NOT_FOUND = "pipeline_not_found"
    STAGE_NOT_FOUND = "stage_not_found"
    CARD_NOT_FOUND = "card_not_found"
    ACTIVITY_NOT_FOUND = "activity_not_found"
    TASK_NOT_FOUND = "task_not_found"
    CNPJ_NOT_FOUND = "cnpj_not_found"
    CARD_DUPLICATE = "card_duplicate"
    CANNOT_DELETE_LAST_STAGE = "cannot_delete_last_stage"
    STAGE_HAS_CARDS = "stage_has_cards"
    STAGE_NOT_IN_PIPELINE = "stage_not_in_pipeline"
    NOT_ARCHIVED = "not_archived"
    PAYLOAD_TOO_LARGE = "payload_too_large"


_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.PIPELINE_NOT_FOUND: 404,
    ErrorCode.STAGE_NOT_FOUND: 404,
    ErrorCode.CARD_NOT_FOUND: 404,
    ErrorCode.ACTIVITY_NOT_FOUND: 404,
    ErrorCode.TASK_NOT_FOUND: 404,
    ErrorCode.CNPJ_NOT_FOUND: 422,
    ErrorCode.CARD_DUPLICATE: 409,
    ErrorCode.CANNOT_DELETE_LAST_STAGE: 409,
    ErrorCode.STAGE_HAS_CARDS: 409,
    ErrorCode.STAGE_NOT_IN_PIPELINE: 422,
    ErrorCode.NOT_ARCHIVED: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
}


def pipeline_error(code: ErrorCode, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"code": code.value, **extra}
    return HTTPException(status_code=_STATUS_MAP[code], detail=detail)
