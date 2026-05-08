from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import router
from database import close_pool, create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    try:
        yield
    finally:
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CNPJ Enrichment Service",
        description=(
            "Standalone internal REST API for crawler-derived paid enrichment data. "
            "Public API consumers must access this service through the main API entitlement boundary."
        ),
        version="0.1.0",
        openapi_tags=[
            {"name": "health", "description": "Liveness endpoint"},
            {"name": "enrichment", "description": "Internal enrichment service endpoints"},
        ],
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/v1")
    return app


app = create_app()

