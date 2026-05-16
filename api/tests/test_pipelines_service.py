"""Tests for modules.pipeline.pipelines.service."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, call
from uuid import uuid4

from fastapi import HTTPException

from modules.pipeline.cards.schemas import CardRecord, CardWithCompany, CompanySummary
from modules.pipeline.pipelines.schemas import PipelineCreate, PipelinePatch, PipelineRecord
from modules.pipeline.stages.schemas import StageRecord
from modules.pipeline.pipelines.service import (
    DEFAULT_STAGES,
    archive_pipeline,
    create_pipeline,
    delete_pipeline,
    get_pipeline_detail,
    unarchive_pipeline,
    update_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipeline(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        owner_user_id=uuid4(),
        name="X",
        description=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return PipelineRecord(**base)


def _stage(pipeline_id, position=0, **overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=pipeline_id,
        name="Stage",
        position=position,
        color=None,
        is_won=False,
        is_lost=False,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return StageRecord(**base)


def _card(pipeline_id, stage_id, position=0, estimated_value_cents=None, **overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        cnpj_basico="12345678",
        position=position,
        estimated_value_cents=estimated_value_cents,
        notes=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return CardRecord(**base)


def _card_with_company(card: CardRecord) -> CardWithCompany:
    return CardWithCompany(card=card, company=CompanySummary(razao_social=None, uf=None))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_inserts_and_creates_6_default_stages():
    pipeline = _pipeline()
    repo_pipeline = AsyncMock()
    repo_stage = AsyncMock()
    repo_pipeline.insert.return_value = pipeline
    repo_stage.bulk_insert.return_value = []

    owner_id = uuid4()
    payload = PipelineCreate(name="My Pipeline")

    result = await create_pipeline(
        repo_pipeline,
        repo_stage,
        owner_user_id=owner_id,
        payload=payload,
    )

    repo_pipeline.insert.assert_called_once_with(
        owner_user_id=owner_id,
        name="My Pipeline",
        description=None,
    )

    # bulk_insert called once with 6 stage dicts
    repo_stage.bulk_insert.assert_called_once()
    args = repo_stage.bulk_insert.call_args
    stages_arg = args[0][1]  # second positional arg

    assert len(stages_arg) == 6

    # positions must be 0..5
    positions = [s["position"] for s in stages_arg]
    assert positions == list(range(6))

    # Ganho (index 4) has is_won=True
    assert stages_arg[4]["name"] == "Ganho"
    assert stages_arg[4]["is_won"] is True
    assert stages_arg[4]["is_lost"] is False

    # Perdido (index 5) has is_lost=True
    assert stages_arg[5]["name"] == "Perdido"
    assert stages_arg[5]["is_won"] is False
    assert stages_arg[5]["is_lost"] is True

    assert result == pipeline


@pytest.mark.asyncio
async def test_create_pipeline_default_stages_constant_has_correct_structure():
    expected_names = ["Lead", "Contatado", "Qualificado", "Proposta", "Ganho", "Perdido"]
    assert len(DEFAULT_STAGES) == 6
    assert [s["name"] for s in DEFAULT_STAGES] == expected_names

    # Only Ganho is_won=True
    won_stages = [s for s in DEFAULT_STAGES if s["is_won"]]
    assert len(won_stages) == 1
    assert won_stages[0]["name"] == "Ganho"

    # Only Perdido is_lost=True
    lost_stages = [s for s in DEFAULT_STAGES if s["is_lost"]]
    assert len(lost_stages) == 1
    assert lost_stages[0]["name"] == "Perdido"

    # All stages have a color
    for s in DEFAULT_STAGES:
        assert "color" in s and s["color"] is not None


@pytest.mark.asyncio
async def test_update_pipeline_delegates_to_repo():
    pipeline = _pipeline()
    repo = AsyncMock()
    repo.update.return_value = pipeline

    payload = PipelinePatch(name="Renamed", description="desc")
    result = await update_pipeline(repo, pipeline_id=pipeline.id, payload=payload)

    repo.update.assert_called_once_with(
        pipeline.id,
        name="Renamed",
        description="desc",
    )
    assert result == pipeline


@pytest.mark.asyncio
async def test_archive_pipeline_when_active_calls_repo():
    pipeline = _pipeline(archived_at=None)
    archived = _pipeline(id=pipeline.id, archived_at=datetime.now(timezone.utc))
    repo = AsyncMock()
    repo.archive.return_value = archived

    result = await archive_pipeline(repo, pipeline)

    repo.archive.assert_called_once_with(pipeline.id)
    assert result == archived


@pytest.mark.asyncio
async def test_archive_pipeline_when_already_archived_is_idempotent():
    pipeline = _pipeline(archived_at=datetime.now(timezone.utc))
    repo = AsyncMock()

    result = await archive_pipeline(repo, pipeline)

    repo.archive.assert_not_called()
    assert result is pipeline


@pytest.mark.asyncio
async def test_unarchive_pipeline_when_archived_calls_repo():
    pipeline = _pipeline(archived_at=datetime.now(timezone.utc))
    unarchived = _pipeline(id=pipeline.id, archived_at=None)
    repo = AsyncMock()
    repo.unarchive.return_value = unarchived

    result = await unarchive_pipeline(repo, pipeline)

    repo.unarchive.assert_called_once_with(pipeline.id)
    assert result == unarchived


@pytest.mark.asyncio
async def test_unarchive_pipeline_when_active_raises_not_archived():
    pipeline = _pipeline(archived_at=None)
    repo = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await unarchive_pipeline(repo, pipeline)

    repo.unarchive.assert_not_called()
    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.detail["code"] == "not_archived"


@pytest.mark.asyncio
async def test_delete_pipeline_delegates_to_repo():
    pipeline_id = uuid4()
    repo = AsyncMock()

    await delete_pipeline(repo, pipeline_id=pipeline_id)

    repo.delete.assert_called_once_with(pipeline_id)


@pytest.mark.asyncio
async def test_get_pipeline_detail_aggregates_counts_and_total_value():
    pipeline = _pipeline()
    stage_a = _stage(pipeline.id, position=0, name="A")
    stage_b = _stage(pipeline.id, position=1, name="B")
    stage_c = _stage(pipeline.id, position=2, name="C")

    # 3 cards in A (2 with value), 2 cards in B (1 with value), 0 in C
    cards = [
        _card_with_company(_card(pipeline.id, stage_a.id, estimated_value_cents=1000)),
        _card_with_company(_card(pipeline.id, stage_a.id, estimated_value_cents=2000)),
        _card_with_company(_card(pipeline.id, stage_a.id, estimated_value_cents=None)),
        _card_with_company(_card(pipeline.id, stage_b.id, estimated_value_cents=500)),
        _card_with_company(_card(pipeline.id, stage_b.id, estimated_value_cents=None)),
    ]

    repo_pipeline = AsyncMock()
    repo_stage = AsyncMock()
    repo_card = AsyncMock()
    repo_stage.list_for_pipeline.return_value = [stage_a, stage_b, stage_c]
    repo_card.list_with_company_summary.return_value = cards

    detail = await get_pipeline_detail(
        repo_pipeline,
        repo_stage,
        repo_card,
        pipeline=pipeline,
    )

    assert detail.pipeline == pipeline
    assert len(detail.stage_counts) == 3
    assert detail.total_value_cents == 3500  # 1000 + 2000 + 500

    counts_by_name = {sc.name: sc for sc in detail.stage_counts}
    assert counts_by_name["A"].card_count == 3
    assert counts_by_name["A"].total_value_cents == 3000
    assert counts_by_name["B"].card_count == 2
    assert counts_by_name["B"].total_value_cents == 500
    assert counts_by_name["C"].card_count == 0
    assert counts_by_name["C"].total_value_cents == 0


@pytest.mark.asyncio
async def test_get_pipeline_detail_with_empty_stages_and_cards():
    pipeline = _pipeline()
    repo_pipeline = AsyncMock()
    repo_stage = AsyncMock()
    repo_card = AsyncMock()
    repo_stage.list_for_pipeline.return_value = []
    repo_card.list_with_company_summary.return_value = []

    detail = await get_pipeline_detail(
        repo_pipeline,
        repo_stage,
        repo_card,
        pipeline=pipeline,
    )

    assert detail.pipeline == pipeline
    assert detail.stage_counts == []
    assert detail.total_value_cents == 0
