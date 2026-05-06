"""Router de exportação — streaming CSV sem carregar tudo na RAM."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from database import get_pool
from models.filters import ProspectingFilters
from services.query_builder import build_prospecting_query

router = APIRouter()


@router.get(
    "/export/csv",
    tags=["export"],
    summary="Exportar resultados como CSV",
)
async def export_csv(filters: ProspectingFilters = Depends()):
    filters = filters.model_copy(update={"limit": 100_000})
    pool = await get_pool()
    sql, params = build_prospecting_query(filters)

    async def generate():
        header_written = False
        async with pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor(sql, *params):
                    buf = io.StringIO()
                    writer = csv.DictWriter(buf, fieldnames=row.keys())
                    if not header_written:
                        writer.writeheader()
                        header_written = True
                    writer.writerow(dict(row))
                    yield buf.getvalue().encode("utf-8-sig")

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
