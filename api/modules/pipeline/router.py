"""Aggregates all pipeline sub-routers."""
from fastapi import APIRouter

from modules.pipeline.activities.router import router as activities_router
from modules.pipeline.cards.router import router as cards_router
from modules.pipeline.pipelines.router import router as pipelines_router
from modules.pipeline.stages.router import router as stages_router
from modules.pipeline.tasks.router import router as tasks_router

router = APIRouter()
router.include_router(pipelines_router)
router.include_router(stages_router)
router.include_router(cards_router)
router.include_router(activities_router)
router.include_router(tasks_router)
