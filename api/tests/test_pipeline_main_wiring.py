"""Tests for pipeline package and app wiring."""
from __future__ import annotations

from fastapi.routing import APIRoute


def test_pipeline_package_exports_router():
    from modules.pipeline import router

    assert router.routes


def test_pipeline_aggregate_router_includes_all_sub_routes():
    from modules.pipeline.router import router

    paths = {route.path for route in router.routes}

    assert len(router.routes) >= 25
    assert "/pipelines" in paths
    assert "/pipelines/{pipeline_id}/stages" in paths
    assert "/pipelines/{pipeline_id}/cards" in paths
    assert "/pipelines/{pipeline_id}/cards/{card_id}/activities" in paths
    assert "/pipelines/{pipeline_id}/cards/{card_id}/tasks" in paths
    assert "/pipelines/tasks/mine" in paths


def test_create_app_includes_pipeline_routes_under_v1():
    from main import create_app

    app = create_app()
    pipeline_routes = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/v1/pipelines")
    ]

    assert len(pipeline_routes) >= 25
    assert "/v1/pipelines" in pipeline_routes
    assert "/v1/pipelines/{pipeline_id}/cards/{card_id}/move" in pipeline_routes
    assert "/v1/pipelines/{pipeline_id}/cards/{card_id}/activities/{activity_id}" in pipeline_routes


def test_openapi_has_pipeline_tags():
    from main import create_app

    app = create_app()
    tags = {tag["name"] for tag in app.openapi()["tags"]}

    assert {
        "pipelines",
        "pipeline_stages",
        "pipeline_cards",
        "pipeline_activities",
        "pipeline_tasks",
    }.issubset(tags)
