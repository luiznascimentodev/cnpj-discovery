from config import settings
from server import app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "server:app",
        host=settings.enrichment_host,
        port=settings.enrichment_port,
        reload=settings.environment == "development",
    )

