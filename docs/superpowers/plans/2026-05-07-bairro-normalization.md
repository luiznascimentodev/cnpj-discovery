# Bairro Normalization & Disambiguation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw, noisy `bairros_lookup` materialized view with a normalized canonical version, update the API to return structured items with city disambiguation, and update the autocomplete component to display and wire the disambiguation into the filters.

**Architecture:** The Receita Federal data has 1.3M raw `(uf, bairro)` pairs because the same neighborhood appears under dozens of typographical variants (e.g., `"B-N.C-SITIO CERCADO"`, `"*CENTRO"`, `".CENTRO"` all refer to the same place). We normalize by stripping leading non-alphanumeric garbage and collapsing whitespace, reducing to a canonical `bairro_canonical` per `(uf, municipio)`. The API query aggregates: if a canonical name exists in only one city within the UF it returns `municipio: null`; if in multiple cities it returns one row per city. The frontend renders `"SITIO CERCADO"` or `"CENTRO · CURITIBA"` accordingly, and on selection emits `{bairro, municipio?}` so FilterPanel can set both filters at once.

**Tech Stack:** PostgreSQL `regexp_replace` for normalization, `pg_trgm` GIN index for ILIKE autocomplete, asyncpg, FastAPI/Pydantic, React Query, TypeScript.

---

## Files

| File | Action | Responsibility |
|---|---|---|
| `db/migrations/007_bairros_canonical.sql` | Create | Drop old view, recreate with normalization + municipio join |
| `api/routers/bairros.py` | Modify | New SQL with city aggregation, add `BairroItem` Pydantic model |
| `api/tests/test_routers.py` | Modify | Update `TestBairrosRouter` for new `BairroItem` response shape |
| `frontend/src/api/client.ts` | Modify | Add `BairroItem` interface, update `getBairros` return type |
| `frontend/src/components/BairroAutocomplete.tsx` | Modify | New display logic (`name · city`), new `onChange({bairro, municipio?})` signature |
| `frontend/src/components/FilterPanel.tsx` | Modify | Add `municipio` state, `handleBairroChange`, wire into `buildFilters` + `handleClear` |

---

## Task 1: Migration — rebuild `bairros_lookup` with normalization

**Files:**
- Create: `db/migrations/007_bairros_canonical.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- db/migrations/007_bairros_canonical.sql
-- Rebuilds bairros_lookup with normalized canonical names and municipality info.
-- Normalization: strip leading non-alphanumeric garbage chars, collapse whitespace, uppercase.
-- Schema: (uf, municipio, municipio_descricao, bairro_canonical) — unique per tuple.
-- Refresh after each ETL: REFRESH MATERIALIZED VIEW CONCURRENTLY bairros_lookup;

DROP MATERIALIZED VIEW IF EXISTS bairros_lookup;

CREATE MATERIALIZED VIEW bairros_lookup AS
SELECT DISTINCT
    est.uf,
    est.municipio,
    m.descricao AS municipio_descricao,
    trim(regexp_replace(
        regexp_replace(upper(est.bairro), E'^[^A-Z0-9]+', ''),
        E'\\s+', ' ', 'g'
    )) AS bairro_canonical
FROM estabelecimentos est
JOIN municipios m ON m.codigo = est.municipio
WHERE est.uf IS NOT NULL
  AND est.bairro IS NOT NULL
  AND est.bairro != ''
  AND length(trim(regexp_replace(
        regexp_replace(upper(est.bairro), E'^[^A-Z0-9]+', ''),
        E'\\s+', ' ', 'g'
      ))) >= 2
ORDER BY uf, bairro_canonical, municipio_descricao;

CREATE UNIQUE INDEX idx_bairros_lookup_unique
    ON bairros_lookup (uf, municipio, bairro_canonical);

CREATE INDEX idx_bairros_lookup_trgm
    ON bairros_lookup USING gin (bairro_canonical gin_trgm_ops);
```

- [ ] **Step 2: Run migration in background (it takes a few minutes)**

```bash
# Run from project root — copy script into container and execute detached
cat > /tmp/run_007.py << 'EOF'
import asyncio, asyncpg, time
from config import settings

SQL = open("/app/db/migrations/007_bairros_canonical.sql").read()

async def run():
    conn = await asyncpg.connect(settings.dsn, command_timeout=600)
    t0 = time.time()
    print("Running migration 007...")
    for stmt in [s.strip() for s in SQL.split(';') if s.strip() and not s.strip().startswith('--')]:
        print(f"  {stmt[:60]}...")
        await conn.execute(stmt)
    count = await conn.fetchval("SELECT COUNT(*) FROM bairros_lookup")
    print(f"Done in {time.time()-t0:.0f}s — {count} rows")
    await conn.close()

asyncio.run(run())
EOF

# Copy migration file and runner into running api container
docker cp db/migrations/007_bairros_canonical.sql cnpj-api:/app/db/migrations/
docker cp /tmp/run_007.py cnpj-api:/tmp/run_007.py
docker exec -d cnpj-api python /tmp/run_007.py
```

- [ ] **Step 3: Verify migration completed**

```bash
docker exec cnpj-api python -c "
import asyncio, asyncpg
from config import settings
async def run():
    conn = await asyncpg.connect(settings.dsn)
    count = await conn.fetchval('SELECT COUNT(*) FROM bairros_lookup')
    sample = await conn.fetch(\"SELECT bairro_canonical, municipio_descricao FROM bairros_lookup WHERE uf='PR' AND bairro_canonical ILIKE '%sitio cercado%' LIMIT 5\")
    print('Total rows:', count)
    for r in sample:
        print(' ', r['bairro_canonical'], '|', r['municipio_descricao'])
    await conn.close()
asyncio.run(run())
"
```

Expected: `bairro_canonical = 'SITIO CERCADO'` should appear once per city (e.g., CURITIBA), not 1M times.

- [ ] **Step 4: Commit migration file**

```bash
git add db/migrations/007_bairros_canonical.sql
git commit -m "db: normalize bairros_lookup with canonical names and municipality join"
```

---

## Task 2: API — `BairroItem` model + new disambiguation SQL

**Files:**
- Modify: `api/routers/bairros.py` (full rewrite)

- [ ] **Step 1: Write the failing tests first**

In `api/tests/test_routers.py`, replace the entire `TestBairrosRouter` class (lines 583–636) with:

```python
class TestBairrosRouter:
    @pytest.mark.asyncio
    async def test_returns_empty_when_q_too_short(self, client: AsyncClient):
        response = await client.get("/v1/bairros?uf=SP&q=c")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_q_missing(self, client: AsyncClient):
        response = await client.get("/v1/bairros?uf=SP")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_requires_uf(self, client: AsyncClient):
        response = await client.get("/v1/bairros?q=centro")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cache_hit_returns_data(self, client: AsyncClient):
        cached = [{"bairro": "CENTRO", "municipio": None, "municipio_descricao": None}]
        with patch("routers.bairros.cache_get", AsyncMock(return_value=cached)):
            response = await client.get("/v1/bairros?uf=SP&q=centro")
        assert response.status_code == 200
        assert response.json() == cached

    @pytest.mark.asyncio
    async def test_unique_bairro_has_null_municipio(self, client: AsyncClient):
        """When bairro exists in only one city, municipio must be null."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"bairro": "SITIO CERCADO", "municipio": None, "municipio_descricao": None},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("routers.bairros.cache_get", AsyncMock(return_value=None)):
            with patch("routers.bairros.cache_set", AsyncMock()):
                with patch("routers.bairros.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/bairros?uf=PR&q=sitio")
        data = response.json()
        assert response.status_code == 200
        assert data[0]["bairro"] == "SITIO CERCADO"
        assert data[0]["municipio"] is None
        assert data[0]["municipio_descricao"] is None

    @pytest.mark.asyncio
    async def test_ambiguous_bairro_has_municipio(self, client: AsyncClient):
        """When same bairro exists in multiple cities, each entry has municipio populated."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"bairro": "CENTRO", "municipio": 4106902, "municipio_descricao": "CURITIBA"},
            {"bairro": "CENTRO", "municipio": 4113700, "municipio_descricao": "LONDRINA"},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("routers.bairros.cache_get", AsyncMock(return_value=None)):
            with patch("routers.bairros.cache_set", AsyncMock()):
                with patch("routers.bairros.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/bairros?uf=PR&q=centro")
        data = response.json()
        assert response.status_code == 200
        assert len(data) == 2
        assert data[0]["municipio"] == 4106902
        assert data[1]["municipio_descricao"] == "LONDRINA"

    @pytest.mark.asyncio
    async def test_uf_is_uppercased(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"bairro": "FLAMENGO", "municipio": None, "municipio_descricao": None},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("routers.bairros.cache_get", AsyncMock(return_value=None)):
            with patch("routers.bairros.cache_set", AsyncMock()):
                with patch("routers.bairros.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/bairros?uf=rj&q=flamengo")
        assert response.status_code == 200
        call_args = mock_conn.fetch.call_args[0]
        assert call_args[1] == "RJ"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker compose build api && docker compose run --rm api sh -c \
  "pip install -q -r requirements-dev.txt && python -m pytest tests/test_routers.py::TestBairrosRouter -v 2>&1 | tail -20"
```

Expected: several tests FAIL because current router returns `list[str]`, not `list[BairroItem]`.

- [ ] **Step 3: Rewrite `api/routers/bairros.py`**

```python
"""Autocomplete de bairros por UF com normalização e desambiguação por município."""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cache import cache_get, cache_set
from database import get_pool

router = APIRouter()

_CACHE_TTL = 3600  # 1h — bairros são dados estáticos


class BairroItem(BaseModel):
    bairro: str
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None


# CTE agrupa: se o bairro canônico existe em mais de 1 município no UF → retorna
# um registro por cidade com municipio preenchido. Se único → municipio null.
_SQL = """
WITH matches AS (
    SELECT
        bairro_canonical,
        municipio,
        municipio_descricao,
        COUNT(municipio) OVER (PARTITION BY bairro_canonical) AS n_cities
    FROM bairros_lookup
    WHERE uf = $1 AND bairro_canonical ILIKE $2
    LIMIT 60
)
SELECT DISTINCT
    bairro_canonical                                              AS bairro,
    CASE WHEN n_cities > 1 THEN municipio          ELSE NULL END AS municipio,
    CASE WHEN n_cities > 1 THEN municipio_descricao ELSE NULL END AS municipio_descricao
FROM matches
ORDER BY bairro, municipio_descricao NULLS FIRST
LIMIT 30
"""


@router.get("/bairros", tags=["prospecting"], summary="Autocomplete de bairros por UF")
async def list_bairros(
    uf: str = Query(..., min_length=2, max_length=2, description="Sigla do estado (ex: SP)"),
    q: str = Query("", max_length=100, description="Prefixo ou trecho do nome do bairro"),
):
    q = q.strip()
    if len(q) < 2:
        return []

    uf_upper = uf.upper()
    cache_key = f"cnpj:bairros:{uf_upper}:{q.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, uf_upper, f"%{q}%")

    result = [
        BairroItem(
            bairro=r["bairro"],
            municipio=r["municipio"],
            municipio_descricao=r["municipio_descricao"],
        ).model_dump()
        for r in rows
    ]
    await cache_set(cache_key, result, ttl=_CACHE_TTL)
    return result
```

- [ ] **Step 4: Run tests — all should pass, coverage 100%**

```bash
docker compose build api && docker compose run --rm api sh -c \
  "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q 2>&1 | tail -15"
```

Expected: `197 passed` and `Total coverage: 100.00%`.

- [ ] **Step 5: Commit**

```bash
git add api/routers/bairros.py api/tests/test_routers.py
git commit -m "feat: bairro autocomplete returns BairroItem with city disambiguation"
```

---

## Task 3: Frontend — `BairroItem` type + `getBairros` return type

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add `BairroItem` interface and update `getBairros`**

In `frontend/src/api/client.ts`, replace:

```typescript
export const getBairros = (uf: string, q: string): Promise<string[]> =>
  api.get<string[]>('/bairros', { params: { uf, q } }).then(r => r.data)
```

With:

```typescript
export interface BairroItem {
  bairro: string
  municipio: number | null
  municipio_descricao: string | null
}

export const getBairros = (uf: string, q: string): Promise<BairroItem[]> =>
  api.get<BairroItem[]>('/bairros', { params: { uf, q } }).then(r => r.data)
```

Place the `BairroItem` interface just before the `getBairros` line.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build fails at `BairroAutocomplete.tsx` because it still uses `string[]`. That is the expected failure — TypeScript now enforces the type.

---

## Task 4: Frontend — `BairroAutocomplete` with new display and callback

**Files:**
- Modify: `frontend/src/components/BairroAutocomplete.tsx`

- [ ] **Step 1: Rewrite `BairroAutocomplete.tsx`**

Full file replacement:

```tsx
import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { BairroItem } from '../api/client'
import { getBairros } from '../api/client'

interface BairroSelection {
  bairro: string
  municipio?: number
}

interface Props {
  uf: string
  value: string
  onChange: (selection: BairroSelection) => void
}

function labelFor(item: BairroItem): string {
  return item.municipio_descricao ? `${item.bairro} · ${item.municipio_descricao}` : item.bairro
}

export function BairroAutocomplete({ uf, value, onChange }: Props) {
  const [q, setQ] = useState(value)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setQ(value) }, [value])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const trimmed = q.trim()
  const { data = [] } = useQuery({
    queryKey: ['bairros', uf, trimmed],
    queryFn: () => getBairros(uf, trimmed),
    enabled: !!uf && trimmed.length >= 2,
    staleTime: 1000 * 60 * 60,
  })

  const handleInput = (v: string) => {
    setQ(v)
    setOpen(true)
    if (!v.trim()) onChange({ bairro: '' })
  }

  const handleSelect = (item: BairroItem) => {
    setQ(labelFor(item))
    onChange({
      bairro: item.bairro,
      ...(item.municipio !== null && { municipio: item.municipio }),
    })
    setOpen(false)
  }

  const disabled = !uf

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={q}
        disabled={disabled}
        onChange={e => handleInput(e.target.value)}
        onFocus={() => data.length > 0 && setOpen(true)}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
        placeholder={disabled ? 'Selecione uma UF primeiro' : 'Digite o bairro…'}
        autoComplete="off"
      />
      {open && data.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
          {data.map((item, i) => (
            <li
              key={`${item.bairro}-${item.municipio ?? i}`}
              onMouseDown={() => handleSelect(item)}
              className="cursor-pointer px-3 py-1.5 text-sm hover:bg-blue-50"
            >
              {labelFor(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build fails at `FilterPanel.tsx` because `onChange={setBairro}` is now wrong type (string setter vs `BairroSelection` object). That is the expected failure.

---

## Task 5: Frontend — `FilterPanel` wires `municipio` from bairro selection

**Files:**
- Modify: `frontend/src/components/FilterPanel.tsx`

- [ ] **Step 1: Add `municipio` state, `handleBairroChange`, and update `buildFilters` + `handleClear`**

Apply these changes to `FilterPanel.tsx`:

**a) Add `municipio` state after `bairro` state (line 23):**
```tsx
  const [bairro, setBairro] = useState('')
  const [municipioBairro, setMunicipioBairro] = useState<number | undefined>(undefined)
```

**b) Replace `handleUfChange` to also clear `municipioBairro` (line 25):**
```tsx
  const handleUfChange = (newUf: string) => {
    setUf(newUf)
    setBairro('')
    setMunicipioBairro(undefined)
  }
```

**c) Add `handleBairroChange` after `handleUfChange`:**
```tsx
  const handleBairroChange = ({ bairro: b, municipio: mun }: { bairro: string; municipio?: number }) => {
    setBairro(b)
    setMunicipioBairro(mun)
  }
```

**d) Update `buildFilters` to include `municipioBairro` when present (after the `bairro` spread):**
```tsx
      ...(bairro.trim() && { bairro: bairro.trim() }),
      ...(municipioBairro !== undefined && { municipio: municipioBairro }),
```

**e) Add `setMunicipioBairro(undefined)` to `handleClear` (after `setBairro('')`):**
```tsx
    setBairro('')
    setMunicipioBairro(undefined)
```

**f) Update `BairroAutocomplete` prop (line 112) from `onChange={setBairro}` to:**
```tsx
    <BairroAutocomplete uf={uf} value={bairro} onChange={handleBairroChange} />
```

- [ ] **Step 2: Verify TypeScript compiles clean**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected:
```
✓ built in ~350ms
```
No type errors.

- [ ] **Step 3: Commit frontend changes**

```bash
git add frontend/src/api/client.ts \
        frontend/src/components/BairroAutocomplete.tsx \
        frontend/src/components/FilterPanel.tsx
git commit -m "feat: bairro autocomplete shows city disambiguation and sets municipio filter"
```

---

## Task 6: Rebuild API container and smoke-test end-to-end

**Files:** none — operational step

- [ ] **Step 1: Rebuild and restart API**

```bash
docker compose build api && docker compose up -d api
```

Expected: `Container cnpj-api Started`

- [ ] **Step 2: Smoke-test bairros endpoint**

```bash
curl -s "http://localhost:8000/v1/bairros?uf=PR&q=sitio+cercado" | python3 -m json.tool
```

Expected: a small list of `BairroItem` objects — `SITIO CERCADO` should appear once (not 1M times) with `municipio` populated only if it exists in multiple cities in PR.

```bash
curl -s "http://localhost:8000/v1/bairros?uf=PR&q=centro" | python3 -m json.tool | head -30
```

Expected: `CENTRO` entries each with `municipio_descricao` showing different cities.

- [ ] **Step 3: Run full test suite one last time**

```bash
docker compose run --rm api sh -c \
  "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q 2>&1 | tail -10"
```

Expected: `197 passed` and `Total coverage: 100.00%`.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: rebuild api container with bairro normalization"
```

---

## Self-Review

**Spec coverage:**
- ✅ Normalize bairro names (strip leading garbage, collapse whitespace) — Task 1
- ✅ Deduplicate to one entry per canonical bairro per municipality — Task 1 (DISTINCT)
- ✅ Same bairro in multiple cities → show city name — Task 2 (CTE) + Task 4 (display)
- ✅ When city-disambiguated, set municipio filter automatically — Task 5
- ✅ Tests updated for new response format — Task 2
- ✅ 100% coverage maintained — Task 2 + Task 6

**Type consistency:**
- `BairroItem` (Python Pydantic) matches `BairroItem` (TypeScript interface) — same fields
- `BairroSelection.municipio` is `number | undefined` in TS, aligns with `Optional[int]` in Python
- `handleBairroChange` receives `{bairro: string, municipio?: number}` = matches `BairroSelection`
- `labelFor(item: BairroItem)` used consistently in render and in `handleSelect` display

**No placeholders:** All code blocks are complete and runnable.
