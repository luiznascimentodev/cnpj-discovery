import pytest
from fastapi import HTTPException

from modules.pipeline.errors import pipeline_error, ErrorCode


def test_pipeline_error_returns_http_exception_with_code_in_detail():
    exc = pipeline_error(ErrorCode.PIPELINE_NOT_FOUND)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {"code": "pipeline_not_found"}


def test_pipeline_error_with_extra_detail_merges_fields():
    exc = pipeline_error(ErrorCode.CARD_DUPLICATE, cnpj_basico="12345678")
    assert exc.status_code == 409
    assert exc.detail == {"code": "card_duplicate", "cnpj_basico": "12345678"}


@pytest.mark.parametrize("code,expected_status", [
    (ErrorCode.PIPELINE_NOT_FOUND, 404),
    (ErrorCode.STAGE_NOT_FOUND, 404),
    (ErrorCode.CARD_NOT_FOUND, 404),
    (ErrorCode.ACTIVITY_NOT_FOUND, 404),
    (ErrorCode.TASK_NOT_FOUND, 404),
    (ErrorCode.CNPJ_NOT_FOUND, 422),
    (ErrorCode.CARD_DUPLICATE, 409),
    (ErrorCode.CANNOT_DELETE_LAST_STAGE, 409),
    (ErrorCode.STAGE_HAS_CARDS, 409),
    (ErrorCode.STAGE_NOT_IN_PIPELINE, 422),
    (ErrorCode.NOT_ARCHIVED, 409),
    (ErrorCode.PAYLOAD_TOO_LARGE, 413),
])
def test_status_code_mapping(code, expected_status):
    assert pipeline_error(code).status_code == expected_status
