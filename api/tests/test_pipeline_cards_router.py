"""Tests for pipeline card router and dependencies."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import URL

from modules.pipeline.cards import router as cards_router_module
from modules.pipeline.cards.csv_import import ImportResult, ImportSummary
from modules.pipeline.cards.schemas import (
    CardCreate,
    CardMove,
    CardPatch,
    CardRecord,
    ImportBatchRecord,
)
from modules.pipeline.pipelines.schemas import PipelineRecord


class FakeRequest:
    def __init__(self):
        self.url = URL("http://test.local")
        self.client = SimpleNamespace(host="127.0.0.1")
        self.headers = {}
        self.cookies = {}


def _pipeline(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        owner_user_id=uuid4(),
        name="Pipeline",
        description=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return PipelineRecord(**base)


def _card(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        cnpj_basico="12345678",
        position=0,
        estimated_value_cents=None,
        notes=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return CardRecord(**base)


def _batch(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=uuid4(),
        owner_user_id=uuid4(),
        stage_id=uuid4(),
        filename="cards.csv",
        file_size_bytes=5,
        content_sha256="a" * 64,
        total_rows=0,
        created_count=0,
        skipped_count=0,
        created_at=now,
    )
    base.update(overrides)
    return ImportBatchRecord(**base)


def _user(user_id=None):
    return type("User", (), {"id": user_id or uuid4()})()


@pytest.mark.asyncio
async def test_cards_by_cnpj_endpoint_delegates_to_service():
    user = _user()
    repo = AsyncMock()
    with patch(
        "modules.pipeline.cards.router.cards_by_cnpj",
        new_callable=AsyncMock,
        return_value=[],
    ) as svc:
        result = await cards_router_module.cards_by_cnpj_endpoint(
            cnpj_basico="12345678",
            user=user,
            repo=repo,
        )

    svc.assert_awaited_once_with(repo, owner_user_id=user.id, cnpj_basico="12345678")
    assert result == []


@pytest.mark.asyncio
async def test_list_cards_endpoint_delegates_to_service():
    pipeline = _pipeline()
    repo = AsyncMock()
    with patch(
        "modules.pipeline.cards.router.list_cards",
        new_callable=AsyncMock,
        return_value=[],
    ) as svc:
        result = await cards_router_module.list_cards_endpoint(pipeline=pipeline, repo=repo)

    svc.assert_awaited_once_with(repo, pipeline.id)
    assert result == []


@pytest.mark.asyncio
async def test_create_card_endpoint_rate_limits_and_delegates():
    user = _user()
    pipeline = _pipeline(owner_user_id=user.id)
    card = _card(pipeline_id=pipeline.id)
    repo = AsyncMock()
    payload = CardCreate(cnpj_basico="12345678")

    with patch("modules.pipeline.cards.router._limit", new_callable=AsyncMock) as limiter, \
         patch(
             "modules.pipeline.cards.router.create_card",
             new_callable=AsyncMock,
             return_value=card,
         ) as svc:
        result = await cards_router_module.create_card_endpoint(
            payload=payload,
            request=FakeRequest(),
            user=user,
            pipeline=pipeline,
            repo=repo,
        )

    limiter.assert_awaited_once()
    svc.assert_awaited_once_with(
        repo,
        pipeline_id=pipeline.id,
        payload=payload,
        current_user_id=user.id,
    )
    assert result == card


@pytest.mark.asyncio
async def test_create_card_endpoint_propagates_rate_limit():
    with patch(
        "modules.pipeline.cards.router._limit",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=429, detail="limited"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await cards_router_module.create_card_endpoint(
                payload=CardCreate(cnpj_basico="12345678"),
                request=FakeRequest(),
                user=_user(),
                pipeline=_pipeline(),
                repo=AsyncMock(),
            )

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_get_card_endpoint_returns_owned_card():
    card = _card()

    result = await cards_router_module.get_card_endpoint(card=card)

    assert result == card


@pytest.mark.asyncio
async def test_get_card_import_metadata_endpoint_delegates_to_repo():
    card = _card()
    repo = AsyncMock()
    repo.list_import_rows_for_card.return_value = []

    result = await cards_router_module.get_card_import_metadata_endpoint(card=card, repo=repo)

    repo.list_import_rows_for_card.assert_awaited_once_with(card.id)
    assert result == []


@pytest.mark.asyncio
async def test_update_card_endpoint_delegates_to_service():
    card = _card()
    payload = CardPatch(notes="n")
    repo = AsyncMock()
    with patch(
        "modules.pipeline.cards.router.update_card",
        new_callable=AsyncMock,
        return_value=card,
    ) as svc:
        result = await cards_router_module.update_card_endpoint(payload=payload, card=card, repo=repo)

    svc.assert_awaited_once_with(repo, card=card, payload=payload)
    assert result == card


@pytest.mark.asyncio
async def test_move_card_endpoint_delegates_to_service():
    user = _user()
    card = _card()
    payload = CardMove(stage_id=uuid4(), position=2)
    repo = AsyncMock()
    with patch(
        "modules.pipeline.cards.router.move_card",
        new_callable=AsyncMock,
        return_value=card,
    ) as svc:
        result = await cards_router_module.move_card_endpoint(
            payload=payload,
            user=user,
            card=card,
            repo=repo,
        )

    svc.assert_awaited_once_with(repo, card=card, payload=payload, current_user_id=user.id)
    assert result == card


@pytest.mark.asyncio
async def test_delete_card_endpoint_delegates_to_service():
    card = _card()
    repo = AsyncMock()
    with patch("modules.pipeline.cards.router.delete_card", new_callable=AsyncMock) as svc:
        result = await cards_router_module.delete_card_endpoint(card=card, repo=repo)

    svc.assert_awaited_once_with(repo, card_id=card.id)
    assert result is None


@pytest.mark.asyncio
async def test_import_cards_endpoint_rate_limits_and_delegates():
    user = _user()
    pipeline = _pipeline(owner_user_id=user.id)
    repo = AsyncMock()
    stage_id = uuid4()
    import_result = ImportResult(
        batch=_batch(pipeline_id=pipeline.id, owner_user_id=user.id, stage_id=stage_id),
        created=0,
        skipped=[],
        summary=ImportSummary(total_rows=0, valid_rows=0, invalid_rows=0, duplicates_in_file=0),
    )
    file = SimpleNamespace(filename="cards.csv", read=AsyncMock(return_value=b"cnpj\n"))

    with patch("modules.pipeline.cards.router._limit", new_callable=AsyncMock) as limiter, \
         patch(
             "modules.pipeline.cards.router.import_cards",
             new_callable=AsyncMock,
             return_value=import_result,
         ) as svc:
        result = await cards_router_module.import_cards_endpoint(
            request=FakeRequest(),
            stage_id=stage_id,
            file=file,
            user=user,
            pipeline=pipeline,
            repo=repo,
        )

    limiter.assert_awaited_once()
    svc.assert_awaited_once_with(
        repo,
        pipeline_id=pipeline.id,
        stage_id=stage_id,
        current_user_id=user.id,
        filename="cards.csv",
        file_size_bytes=5,
        content="cnpj\n",
    )
    assert result == import_result


@pytest.mark.asyncio
async def test_import_cards_endpoint_propagates_rate_limit():
    with patch(
        "modules.pipeline.cards.router._limit",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=429, detail="limited"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await cards_router_module.import_cards_endpoint(
                request=FakeRequest(),
                stage_id=uuid4(),
                file=SimpleNamespace(filename="cards.csv", read=AsyncMock(return_value=b"cnpj\n")),
                user=_user(),
                pipeline=_pipeline(),
                repo=AsyncMock(),
            )

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_import_cards_endpoint_rejects_non_utf8_file():
    with patch("modules.pipeline.cards.router._limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await cards_router_module.import_cards_endpoint(
                request=FakeRequest(),
                stage_id=uuid4(),
                file=SimpleNamespace(filename="cards.csv", read=AsyncMock(return_value=b"\xff\xfe")),
                user=_user(),
                pipeline=_pipeline(),
                repo=AsyncMock(),
            )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_limit_helper_passes_when_bucket_allows():
    limiter = AsyncMock()
    limiter.try_acquire.return_value = SimpleNamespace(ok=True, retry_after=0)

    with patch("modules.pipeline.cards.router.RateLimiter", return_value=limiter), \
         patch("modules.pipeline.cards.router.get_redis", return_value=object()):
        result = await cards_router_module._limit(
            FakeRequest(),
            "cards:test",
            window=3600,
            max_count=1,
        )

    limiter.try_acquire.assert_awaited_once()
    assert result is None


@pytest.mark.asyncio
async def test_limit_helper_raises_429_when_bucket_exhausted():
    limiter = AsyncMock()
    limiter.try_acquire.return_value = SimpleNamespace(ok=False, retry_after=30)

    with patch("modules.pipeline.cards.router.RateLimiter", return_value=limiter), \
         patch("modules.pipeline.cards.router.get_redis", return_value=object()):
        with pytest.raises(HTTPException) as exc_info:
            await cards_router_module._limit(
                FakeRequest(),
                "cards:test",
                window=3600,
                max_count=1,
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_owned_card_returns_card_when_found():
    from modules.pipeline.dependencies import owned_card

    pipeline = _pipeline()
    card = _card(pipeline_id=pipeline.id)
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = card

    result = await owned_card(card_id=card.id, pipeline=pipeline, repo=repo)

    repo.get_in_pipeline.assert_awaited_once_with(card.id, pipeline_id=pipeline.id)
    assert result == card


@pytest.mark.asyncio
async def test_owned_card_raises_404_when_not_found():
    from modules.pipeline.dependencies import owned_card

    repo = AsyncMock()
    repo.get_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_card(card_id=uuid4(), pipeline=_pipeline(), repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "card_not_found"
