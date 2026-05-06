"""
CNPJ Discovery API — FastAPI application factory.

Expõe dados de CNPJs da Receita Federal via REST API com filtros avançados.
Documentação interativa disponível em /docs (Swagger UI).

Endpoints:
    GET /v1/health          Health check
    GET /v1/prospecting     Busca empresas com filtros
    GET /v1/export/csv      Exporta resultado filtrado como CSV
    GET /v1/status          Status do ETL e estatísticas do banco
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import create_pool, close_pool
from routers import prospecting, export, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: inicializa pool no startup, fecha no shutdown."""
    await create_pool()
    yield
    await close_pool()


def create_app() -> FastAPI:
    """
    Factory da aplicação FastAPI.
    Separar a criação da instância permite testar sem subir o servidor.
    """
    app = FastAPI(
        title="CNPJ Discovery API",
        description=(
            "API para prospecção B2B utilizando a base completa de CNPJs da Receita Federal. "
            "Suporta filtros por UF, município, CNAE, porte, situação cadastral, capital social "
            "e busca textual por razão social ou nome fantasia. "
            "Exportação de resultados em CSV via streaming.\n\n"
            "**Base de dados:** ~50 milhões de registros de empresas brasileiras.\n\n"
            "**Atualização:** Mensal, via ETL automatizado.\n\n"
            "**Paginação:** Keyset pagination via parâmetros `cursor_cnpj_basico` e `cursor_cnpj_ordem`."
        ),
        version="1.0.0",
        contact={
            "name": "CNPJ Discovery",
            "url": "https://github.com/seu-usuario/cnpj-discovery",
        },
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "health", "description": "Health check e liveness probe"},
            {"name": "prospecting", "description": "Busca e filtros de empresas"},
            {"name": "export", "description": "Exportação de dados em CSV"},
            {"name": "status", "description": "Status do ETL e estatísticas"},
        ],
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Health check — sem dependência de DB para responder rápido em probes
    @app.get(
        "/v1/health",
        tags=["health"],
        summary="Health check",
        response_description="API está operacional",
        responses={200: {"content": {"application/json": {"example": {"status": "ok", "version": "1.0.0"}}}}},
    )
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    app.include_router(prospecting.router, prefix="/v1")
    app.include_router(export.router, prefix="/v1")
    app.include_router(status.router, prefix="/v1")

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
