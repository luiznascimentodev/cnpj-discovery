# Pipeline Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar feature de Pipeline de Vendas (Kanban) ao backend — multi-pipeline por user, estágios customizáveis, cards = empresas, atividades + tasks + auditoria de stage, com CSV import e cobertura 100%.

**Architecture:** Vertical slice em `api/modules/pipeline/` com subpastas por entidade (pipelines/stages/cards/activities/tasks). Owner-only via dependency `owned_pipeline`/`owned_card`. CSRF + rate-limit reusam `api/core/`. Testes seguem padrão existente do projeto (mock de `pool` via `AsyncMock` + `patch`, FakeRequest/FakeResponse, sem Postgres real). Cobertura enforced em CI por `--cov-fail-under=100`.

**Tech Stack:** FastAPI, asyncpg, Pydantic v2, pytest-asyncio, csv stdlib.

**Reference spec:** `docs/superpowers/specs/2026-05-16-pipeline-backend-design.md`.

**Convenções deste plano:**
- Tudo executado de dentro de `/home/luife/projetos/cnpj-discovery/api/`.
- Cada task termina com commit. Mensagens em pt-BR, prefixo `feat(pipeline):` ou `test(pipeline):`.
- Branch: trabalhe direto em `main` (segue convenção do repo, ver commits recentes).
- **NÃO** acessar Postgres real nos testes — segue o padrão `tests/conftest.py` (AsyncMock).
- Hard gate: `pytest --cov-fail-under=100` precisa passar ao final de cada task que toca código novo.

---

## Decisões de adaptação à realidade do projeto

O spec descreveu testes como "AsyncClient contra app real + Postgres de teste". A realidade do projeto (`api/tests/conftest.py`) é: pool mockado via `AsyncMock`, chamadas diretas às funções do router com `FakeRequest`/`FakeResponse`, sem httpx para a maioria. Vamos **seguir o padrão existente** porque:

1. Coerência com auth/billing/prospecting já implementados.
2. CI roda em ~3s sem precisar de Postgres.
3. Coverage gate 100% é atingível mockando repository (queries SQL são triviais de unit-test).

Onde precisarmos validar SQL real (ex: `DEFERRED UNIQUE` em reorder), faremos via revisão manual da migration + smoke test em dev — não em CI.

**Localização dos testes:** vamos seguir o padrão existente (`api/tests/test_pipeline_*.py`), NÃO `api/modules/pipeline/tests/`. A memória `backend-architecture` descreve intenção futura; auth (último módulo adicionado) ainda usa o padrão flat. Ficar consistente com o presente é melhor que retrofitar.

---

## Mapa de arquivos

**Criar:**
```
db/migrations/019_pipeline.sql

api/modules/pipeline/
├── __init__.py
├── router.py
├── dependencies.py
├── errors.py
├── pipelines/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
├── stages/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
├── cards/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── schemas.py
│   └── csv_import.py
├── activities/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
└── tasks/
    ├── __init__.py
    ├── router.py
    ├── service.py
    ├── repository.py
    └── schemas.py

api/tests/
├── test_pipeline_errors.py
├── test_pipeline_dependencies.py
├── test_pipelines_repository.py
├── test_pipelines_service.py
├── test_pipelines_router.py
├── test_pipeline_stages_repository.py
├── test_pipeline_stages_service.py
├── test_pipeline_stages_router.py
├── test_pipeline_cards_repository.py
├── test_pipeline_cards_service.py
├── test_pipeline_cards_router.py
├── test_pipeline_csv_import.py
├── test_pipeline_activities.py
├── test_pipeline_tasks.py
└── test_pipeline_main_wiring.py
```

**Modificar:**
- `api/main.py` (importar e incluir `pipeline.router`; adicionar 5 entries em `openapi_tags`)
- `api/.importlinter` (adicionar contrato de layers)
- `api/tests/conftest.py` (adicionar mock para `modules.pipeline.*` patches de `get_pool`)

---

## Tasks

### Task 1: Criar migration 019 do schema completo

**Files:**
- Create: `db/migrations/019_pipeline.sql`

- [ ] **Step 1: Criar arquivo de migration com o schema completo**

Escrever `db/migrations/019_pipeline.sql` com o conteúdo exato da §5 do spec. Conteúdo:

```sql
-- ============================================================
-- 019_pipeline.sql
-- Sales pipeline (Kanban): pipelines + stages + cards + activities + tasks + stage history
-- ============================================================

CREATE TABLE pipelines (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  archived_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipelines_owner_active ON pipelines (owner_user_id, created_at DESC)
  WHERE archived_at IS NULL;

CREATE TABLE pipeline_stages (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  position    INTEGER NOT NULL,
  color       TEXT,
  is_won      BOOLEAN NOT NULL DEFAULT FALSE,
  is_lost     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (NOT (is_won AND is_lost)),
  CHECK (position >= 0)
);
CREATE INDEX pipeline_stages_pipeline ON pipeline_stages (pipeline_id, position);

CREATE TABLE pipeline_cards (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id           UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  stage_id              UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
  cnpj_basico           CHAR(8) NOT NULL,
  position              INTEGER NOT NULL,
  estimated_value_cents BIGINT,
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, cnpj_basico),
  UNIQUE (stage_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (position >= 0),
  CHECK (cnpj_basico ~ '^\d{8}$')
);
CREATE INDEX pipeline_cards_stage ON pipeline_cards (stage_id, position);
CREATE INDEX pipeline_cards_pipeline ON pipeline_cards (pipeline_id);
CREATE INDEX pipeline_cards_cnpj ON pipeline_cards (cnpj_basico);

CREATE TABLE pipeline_card_activities (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  card_id        UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  author_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  kind           TEXT NOT NULL CHECK (kind IN ('note','call','email','meeting')),
  body           TEXT NOT NULL,
  occurred_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_activities_card
  ON pipeline_card_activities (card_id, occurred_at DESC);

CREATE TABLE pipeline_card_tasks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  card_id          UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  assignee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title            TEXT NOT NULL,
  due_at           TIMESTAMPTZ,
  done_at          TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_tasks_open
  ON pipeline_card_tasks (assignee_user_id, due_at) WHERE done_at IS NULL;
CREATE INDEX pipeline_card_tasks_card
  ON pipeline_card_tasks (card_id, created_at DESC);

CREATE TABLE pipeline_card_stage_changes (
  id                 BIGSERIAL PRIMARY KEY,
  card_id            UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  from_stage_id      UUID REFERENCES pipeline_stages(id) ON DELETE SET NULL,
  to_stage_id        UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE SET NULL,
  changed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  changed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_stage_changes_card
  ON pipeline_card_stage_changes (card_id, changed_at DESC);
```

- [ ] **Step 2: Verificar sintaxe SQL contra Postgres local (opcional, recomendado)**

Se Postgres local disponível:
```bash
psql -h localhost -U postgres -d cnpj_dev -f db/migrations/019_pipeline.sql
psql -h localhost -U postgres -d cnpj_dev -c "\dt pipeline*"
```
Esperado: 6 tabelas listadas. Em caso de erro de sintaxe, corrigir e re-rodar (drop primeiro).

- [ ] **Step 3: Commit**

```bash
git add db/migrations/019_pipeline.sql
git commit -m "feat(pipeline): migration 019 com schema completo do pipeline backend

Tabelas: pipelines, pipeline_stages, pipeline_cards,
pipeline_card_activities, pipeline_card_tasks,
pipeline_card_stage_changes. Unique constraints de position
deferred para suportar reorder atômico.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Esqueleto do módulo `api/modules/pipeline/`

**Files:**
- Create: 23 arquivos (todos os `__init__.py` e stubs vazios) listados no mapa acima, exceto os arquivos que outras tasks criam com conteúdo real.

- [ ] **Step 1: Criar todas as pastas e `__init__.py` vazios**

```bash
mkdir -p api/modules/pipeline/pipelines \
         api/modules/pipeline/stages \
         api/modules/pipeline/cards \
         api/modules/pipeline/activities \
         api/modules/pipeline/tasks
touch api/modules/pipeline/__init__.py \
      api/modules/pipeline/pipelines/__init__.py \
      api/modules/pipeline/stages/__init__.py \
      api/modules/pipeline/cards/__init__.py \
      api/modules/pipeline/activities/__init__.py \
      api/modules/pipeline/tasks/__init__.py
```

- [ ] **Step 2: Criar `api/modules/pipeline/__init__.py` exportando router agregado**

```python
"""Sales pipeline (Kanban) module — multi-pipeline per user, customizable stages."""
from modules.pipeline.router import router

__all__ = ["router"]
```

- [ ] **Step 3: Criar `api/modules/pipeline/router.py` com router raiz vazio**

```python
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
```

- [ ] **Step 4: Criar 5 sub-router stubs vazios**

Em cada subpasta criar `router.py`:

```python
# api/modules/pipeline/pipelines/router.py
from fastapi import APIRouter
router = APIRouter(tags=["pipelines"])
```

```python
# api/modules/pipeline/stages/router.py
from fastapi import APIRouter
router = APIRouter(tags=["pipeline_stages"])
```

```python
# api/modules/pipeline/cards/router.py
from fastapi import APIRouter
router = APIRouter(tags=["pipeline_cards"])
```

```python
# api/modules/pipeline/activities/router.py
from fastapi import APIRouter
router = APIRouter(tags=["pipeline_activities"])
```

```python
# api/modules/pipeline/tasks/router.py
from fastapi import APIRouter
router = APIRouter(tags=["pipeline_tasks"])
```

- [ ] **Step 5: Verificar import funciona**

```bash
cd api && python -c "from modules.pipeline import router; print(len(router.routes))"
```
Expected: `0`

- [ ] **Step 6: Commit**

```bash
git add api/modules/pipeline/
git commit -m "feat(pipeline): esqueleto do módulo com sub-routers vazios

Cria api/modules/pipeline/ com subpastas pipelines/, stages/,
cards/, activities/, tasks/. Router raiz agrega os 5 sub-routers.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Wire em `main.py` + tags OpenAPI + `.importlinter`

**Files:**
- Modify: `api/main.py`
- Modify: `api/.importlinter`

- [ ] **Step 1: Editar `api/main.py` — adicionar import**

Adicionar após linha 29 (`from modules.prospecting.router import router as prospecting_router`):

```python
from modules.pipeline import router as pipeline_router
```

- [ ] **Step 2: Editar `api/main.py` — adicionar tags em `openapi_tags`**

Após a entry `{"name": "status", ...}` no `openapi_tags`, adicionar:

```python
            {"name": "pipelines", "description": "Pipelines de vendas (boards Kanban)"},
            {"name": "pipeline_stages", "description": "Estágios (colunas) de pipelines"},
            {"name": "pipeline_cards", "description": "Cards (empresas) em pipelines"},
            {"name": "pipeline_activities", "description": "Atividades (timeline) de cards"},
            {"name": "pipeline_tasks", "description": "Tasks (to-do) de cards"},
```

- [ ] **Step 3: Editar `api/main.py` — incluir router**

Após `app.include_router(status.router, prefix="/v1")`, adicionar:

```python
    app.include_router(pipeline_router, prefix="/v1")
```

- [ ] **Step 4: Editar `api/.importlinter` — adicionar contrato**

Acrescentar ao final do arquivo:

```ini
[importlinter:contract:pipeline-internal-layers]
name = Pipeline submodules must follow router → service → repository
type = layers
layers =
    modules.pipeline.pipelines.router | modules.pipeline.stages.router | modules.pipeline.cards.router | modules.pipeline.activities.router | modules.pipeline.tasks.router
    modules.pipeline.pipelines.service | modules.pipeline.stages.service | modules.pipeline.cards.service | modules.pipeline.activities.service | modules.pipeline.tasks.service
    modules.pipeline.pipelines.repository | modules.pipeline.stages.repository | modules.pipeline.cards.repository | modules.pipeline.activities.repository | modules.pipeline.tasks.repository
```

- [ ] **Step 5: Validar import-linter passa**

```bash
cd api && lint-imports
```
Expected: `Kept` em todos os contratos (incluindo o novo).

- [ ] **Step 6: Validar app sobe (smoke import)**

```bash
cd api && python -c "from main import create_app; app = create_app(); print('routes:', len(app.routes))"
```
Expected: integer ≥ rota count anterior; sem ImportError.

- [ ] **Step 7: Commit**

```bash
git add api/main.py api/.importlinter
git commit -m "feat(pipeline): wire router em main.py + contrato import-linter

Inclui pipeline.router em /v1, registra 5 tags OpenAPI e adiciona
contrato de camadas (router → service → repository) para os
5 sub-módulos.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: `errors.py` — códigos de erro centralizados

**Files:**
- Create: `api/modules/pipeline/errors.py`
- Create: `api/tests/test_pipeline_errors.py`

- [ ] **Step 1: Escrever teste para `pipeline_error`**

`api/tests/test_pipeline_errors.py`:

```python
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
```

- [ ] **Step 2: Rodar teste — deve falhar**

```bash
cd api && pytest tests/test_pipeline_errors.py -v
```
Expected: FAIL com ImportError de `modules.pipeline.errors`.

- [ ] **Step 3: Implementar `errors.py`**

```python
"""Centralized error codes and factory for pipeline module."""
from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(str, Enum):
    PIPELINE_NOT_FOUND = "pipeline_not_found"
    STAGE_NOT_FOUND = "stage_not_found"
    CARD_NOT_FOUND = "card_not_found"
    ACTIVITY_NOT_FOUND = "activity_not_found"
    TASK_NOT_FOUND = "task_not_found"
    CNPJ_NOT_FOUND = "cnpj_not_found"
    CARD_DUPLICATE = "card_duplicate"
    CANNOT_DELETE_LAST_STAGE = "cannot_delete_last_stage"
    STAGE_HAS_CARDS = "stage_has_cards"
    STAGE_NOT_IN_PIPELINE = "stage_not_in_pipeline"
    NOT_ARCHIVED = "not_archived"
    PAYLOAD_TOO_LARGE = "payload_too_large"


_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.PIPELINE_NOT_FOUND: 404,
    ErrorCode.STAGE_NOT_FOUND: 404,
    ErrorCode.CARD_NOT_FOUND: 404,
    ErrorCode.ACTIVITY_NOT_FOUND: 404,
    ErrorCode.TASK_NOT_FOUND: 404,
    ErrorCode.CNPJ_NOT_FOUND: 422,
    ErrorCode.CARD_DUPLICATE: 409,
    ErrorCode.CANNOT_DELETE_LAST_STAGE: 409,
    ErrorCode.STAGE_HAS_CARDS: 409,
    ErrorCode.STAGE_NOT_IN_PIPELINE: 422,
    ErrorCode.NOT_ARCHIVED: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
}


def pipeline_error(code: ErrorCode, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"code": code.value, **extra}
    return HTTPException(status_code=_STATUS_MAP[code], detail=detail)
```

- [ ] **Step 4: Rodar teste — deve passar**

```bash
cd api && pytest tests/test_pipeline_errors.py -v
```
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add api/modules/pipeline/errors.py api/tests/test_pipeline_errors.py
git commit -m "feat(pipeline): codes de erro centralizados via ErrorCode + pipeline_error

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Pipelines — schemas Pydantic

**Files:**
- Create: `api/modules/pipeline/pipelines/schemas.py`

- [ ] **Step 1: Implementar schemas**

```python
"""Pydantic schemas for pipelines."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class PipelinePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class PipelineRecord(BaseModel):
    id: UUID
    owner_user_id: UUID
    name: str
    description: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StageCount(BaseModel):
    stage_id: UUID
    name: str
    card_count: int
    total_value_cents: int


class PipelineDetail(BaseModel):
    pipeline: PipelineRecord
    stage_counts: list[StageCount]
    total_value_cents: int
```

- [ ] **Step 2: Smoke import**

```bash
cd api && python -c "from modules.pipeline.pipelines.schemas import PipelineCreate; PipelineCreate(name='x')"
```
Expected: sem erro.

- [ ] **Step 3: Commit**

```bash
git add api/modules/pipeline/pipelines/schemas.py
git commit -m "feat(pipeline): schemas Pydantic para pipelines

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

---

## Padrão repetitivo das entidades (referenciado pelas tasks 6–25)

Cinco entidades (`pipelines`, `stages`, `cards`, `activities`, `tasks`) seguem o mesmo padrão de 4 arquivos cada. Para evitar repetição neste plano, as tasks 6–25 abaixo referenciam este padrão. **Cada task termina em commit.**

**Estrutura por entidade:**

1. **`repository.py`** — classe `<Entity>Repository` que recebe `pool` no `__init__` e expõe métodos async que executam SQL via `pool.acquire()`. Padrão simétrico ao `modules/auth/repository.py:9-60`. Usa `_fetchrow`/`_fetch`/`_execute` privados.
2. **`service.py`** — funções (não classe) que orquestram repo + regras. Recebem repos como argumento ou via dependencies. Levantam `pipeline_error(ErrorCode.X)` de `modules.pipeline.errors`.
3. **`schemas.py`** — Pydantic models (Create, Patch, Record, Out). Limites de `max_length` conforme spec §8.5.
4. **`router.py`** — endpoints FastAPI usando `Depends(owned_pipeline)`/`Depends(owned_card)` (criados na Task 11). Mutações exigem CSRF via `Depends(require_csrf)` (padrão de `modules/auth/router.py`).

**Testes por entidade (padrão):**
- `test_<entity>_repository.py` — mock `pool`/`conn` via `AsyncMock`; valida SQL executado e parâmetros.
- `test_<entity>_service.py` — mock repos; valida regras de negócio e error codes.
- `test_<entity>_router.py` — usa `FakeRequest`/`FakeResponse` do `test_auth_router.py:23-41`, mocka deps + service. Valida status/payload.

**Padrão SQL no repository:**

```python
async def _fetchrow(self, query: str, *args):
    async with self._pool.acquire() as conn:
        return await conn.fetchrow(query, *args)

async def _fetch(self, query: str, *args):
    async with self._pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def _execute(self, query: str, *args):
    async with self._pool.acquire() as conn:
        await conn.execute(query, *args)
```

**Padrão de teste de repository** (exemplo extrapolável):

```python
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.mark.asyncio
async def test_repo_method_calls_correct_sql():
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    conn.fetchrow.return_value = {...}
    repo = PipelineRepository(pool)
    result = await repo.method(arg1, arg2)
    conn.fetchrow.assert_called_once()
    sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO pipelines" in sql
    assert conn.fetchrow.call_args[0][1] == arg1
```

---

### Task 6: Pipelines — repository

**Files:** Create `api/modules/pipeline/pipelines/repository.py` + `api/tests/test_pipelines_repository.py`

- [ ] **Step 1: Escrever testes (mock pool/conn)**

Métodos exigidos no `PipelineRepository`:
- `insert(*, owner_user_id, name, description) -> PipelineRecord`
- `get_for_owner(pipeline_id, *, owner_user_id) -> PipelineRecord | None` (retorna None se não existe OU não é do user)
- `list_for_owner(owner_user_id, *, include_archived) -> list[PipelineRecord]`
- `update(pipeline_id, *, name, description) -> PipelineRecord`
- `archive(pipeline_id) -> PipelineRecord` (set archived_at=now)
- `unarchive(pipeline_id) -> PipelineRecord` (set archived_at=NULL)
- `delete(pipeline_id) -> None`
- `count_for_owner(owner_user_id) -> int`

Para cada método, escrever um teste validando: (a) SQL contém keywords corretas (`INSERT INTO pipelines`, `WHERE owner_user_id = $1`, etc.), (b) parâmetros passados na ordem correta, (c) retorno parseado corretamente como `PipelineRecord`. Mínimo 12 testes.

- [ ] **Step 2: Implementar repository seguindo padrão de `modules/auth/repository.py:9-60`**

Cada método: monta SQL, chama `_fetchrow`/`_execute`, envelope com `PipelineRecord(**dict(row))`. `get_for_owner` usa `WHERE id = $1 AND owner_user_id = $2`. `list_for_owner` usa `WHERE owner_user_id = $1 AND (archived_at IS NULL OR $2)` ordenado por `created_at DESC`.

- [ ] **Step 3: Rodar testes; coverage 100% para `repository.py`**

```bash
cd api && pytest tests/test_pipelines_repository.py --cov=modules/pipeline/pipelines/repository -v
```

- [ ] **Step 4: Commit**

```bash
git add api/modules/pipeline/pipelines/repository.py api/tests/test_pipelines_repository.py
git commit -m "feat(pipeline): PipelineRepository com CRUD + archive

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Pipelines — service (com criação de stages default)

**Files:** Create `api/modules/pipeline/pipelines/service.py` + `api/tests/test_pipelines_service.py`

- [ ] **Step 1: Definir API do service**

Funções:
- `create_pipeline(repo_pipeline, repo_stage, *, owner_user_id, payload: PipelineCreate) -> PipelineRecord` — cria pipeline + 6 stages default (Lead, Contatado, Qualificado, Proposta, Ganho [is_won], Perdido [is_lost]) numa transação.
- `get_pipeline_detail(repo_pipeline, repo_stage, repo_card, *, pipeline_id) -> PipelineDetail` — agrega stage_counts e total_value_cents.
- `update_pipeline(repo, pipeline_id, payload: PipelinePatch) -> PipelineRecord`
- `archive_pipeline(repo, pipeline: PipelineRecord) -> PipelineRecord` — idempotente.
- `unarchive_pipeline(repo, pipeline: PipelineRecord) -> PipelineRecord` — levanta `pipeline_error(NOT_ARCHIVED)` se já ativo.
- `delete_pipeline(repo, pipeline_id) -> None`

`DEFAULT_STAGES: list[dict]` constante com 6 entradas (name, color, is_won, is_lost).

- [ ] **Step 2: Escrever testes — mínimo 10**

Casos: criação cria 6 stages corretos na ordem; archive idempotente; unarchive de ativo levanta 409; detail agrega stage_counts e soma de valores; etc.

- [ ] **Step 3: Implementar service**

- [ ] **Step 4: Coverage 100%**

```bash
cd api && pytest tests/test_pipelines_service.py --cov=modules/pipeline/pipelines/service -v
```

- [ ] **Step 5: Commit**

```bash
git add api/modules/pipeline/pipelines/{service.py,schemas.py} api/tests/test_pipelines_service.py
git commit -m "feat(pipeline): service de pipelines com 6 stages default

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Pipelines — dependencies + router

**Files:** Modify `api/modules/pipeline/dependencies.py`, Modify `api/modules/pipeline/pipelines/router.py`, Create `api/tests/test_pipelines_router.py`

- [ ] **Step 1: Implementar `dependencies.py` com `get_pool`, `get_pipeline_repo`, `owned_pipeline`**

```python
from __future__ import annotations
from uuid import UUID
from fastapi import Depends, Request, Response

from core.db import get_pool
from core.middleware.auth import get_current_user
from modules.auth.schemas import UserRecord
from modules.pipeline.errors import ErrorCode, pipeline_error
from modules.pipeline.pipelines.repository import PipelineRepository
from modules.pipeline.pipelines.schemas import PipelineRecord


async def get_pipeline_repo() -> PipelineRepository:
    return PipelineRepository(await get_pool())


async def owned_pipeline(
    pipeline_id: UUID,
    user: UserRecord = Depends(get_current_user),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> PipelineRecord:
    pipeline = await repo.get_for_owner(pipeline_id, owner_user_id=user.id)
    if pipeline is None:
        raise pipeline_error(ErrorCode.PIPELINE_NOT_FOUND)
    return pipeline
```

- [ ] **Step 2: Implementar 7 endpoints em `pipelines/router.py`** (list/create/get/patch/archive/unarchive/delete) seguindo padrão de `modules/auth/router.py`. Mutações exigem `Depends(require_csrf)`. Rate-limit em `POST /pipelines` (30/h/user) via `core.rate_limit`.

- [ ] **Step 3: Escrever testes do router** — mock deps via `app.dependency_overrides`; valida status code e payload. Mínimo 14 testes (2 por endpoint + casos de erro).

- [ ] **Step 4: Coverage 100% no router + dependencies**

- [ ] **Step 5: Commit**

```bash
git add api/modules/pipeline/{dependencies.py,pipelines/router.py} api/tests/test_pipelines_router.py
git commit -m "feat(pipeline): endpoints /v1/pipelines com auth/CSRF/rate-limit

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Stages — repository + schemas

**Files:** Create `api/modules/pipeline/stages/{repository.py,schemas.py}` + `api/tests/test_pipeline_stages_repository.py`

Schemas: `StageCreate`, `StagePatch`, `StageRecord`, `StageReorderRequest(stage_ids: list[UUID])`.

Repository métodos:
- `insert(*, pipeline_id, name, position, color, is_won, is_lost) -> StageRecord`
- `bulk_insert(pipeline_id, defaults: list[dict]) -> list[StageRecord]` — usado pelo service de pipeline na criação
- `list_for_pipeline(pipeline_id) -> list[StageRecord]` (ORDER BY position)
- `get_in_pipeline(stage_id, *, pipeline_id) -> StageRecord | None`
- `update(stage_id, *, name, color, is_won, is_lost) -> StageRecord`
- `reorder(pipeline_id, stage_ids: list[UUID]) -> None` — transação com DEFERRED constraint; UPDATE positions
- `count_cards(stage_id) -> int`
- `move_cards_and_delete(stage_id, target_stage_id) -> None` — transação
- `delete(stage_id) -> None`

Mínimo 18 testes. Coverage 100%. Commit `feat(pipeline): StageRepository com reorder atômico`.

---

### Task 10: Stages — service + router

**Files:** Create `api/modules/pipeline/stages/{service.py,router.py}` + `api/tests/test_pipeline_stages_{service,router}.py`

Service:
- `create_stage(repo, *, pipeline_id, payload)` — position default = max+1
- `update_stage(repo, *, stage, payload)`
- `reorder_stages(repo, *, pipeline_id, stage_ids)` — valida que stage_ids cobrem todos os stages do pipeline
- `delete_stage(repo, *, pipeline_id, stage_id, move_cards_to)` — proíbe se for último (`cannot_delete_last_stage`), exige `move_cards_to` se tem cards (`stage_has_cards`)

Router: 5 endpoints sob `/pipelines/{pid}/stages`. Validação de que stage pertence ao pipeline → `stage_not_found` (404).

Dependencies: adicionar `owned_stage(stage_id, pipeline=Depends(owned_pipeline), repo_stage=...)` em `dependencies.py`.

Coverage 100%. Commit.

---

### Task 11: Cards — repository + schemas

**Files:** Create `api/modules/pipeline/cards/{repository.py,schemas.py}` + `api/tests/test_pipeline_cards_repository.py`

Schemas: `CardCreate(cnpj_basico, stage_id?, estimated_value_cents?, notes?)`, `CardPatch`, `CardMove(stage_id, position)`, `CardRecord`, `CardWithCompany(card: CardRecord, razao_social: str, uf: str | None)`.

Repository métodos:
- `cnpj_exists(cnpj_basico) -> bool` — `SELECT 1 FROM empresas WHERE cnpj_basico = $1`
- `card_exists_in_pipeline(pipeline_id, cnpj_basico) -> bool`
- `insert(*, pipeline_id, stage_id, cnpj_basico, position, estimated_value_cents, notes) -> CardRecord`
- `bulk_insert(rows: list[dict]) -> list[CardRecord]` — para CSV import; uma transação
- `list_with_company_summary(pipeline_id) -> list[CardWithCompany]` — JOIN com `empresas` + LATERAL JOIN `estabelecimentos` em `cnpj_ordem='0001' AND identificador_matriz_filial=1` para razão social/UF
- `get_in_pipeline(card_id, *, pipeline_id) -> CardRecord | None`
- `update(card_id, *, estimated_value_cents, notes) -> CardRecord`
- `move(card_id, *, stage_id, position) -> CardRecord`
- `delete(card_id) -> None`
- `max_position_in_stage(stage_id) -> int`
- `pipelines_containing_cnpj(owner_user_id, cnpj_basico) -> list[dict]` — para `GET /cards/by-cnpj/{cnpj}`
- `existing_cnpjs_in_basico(cnpjs: list[str]) -> set[str]` — bulk check para CSV import
- `existing_cards_in_pipeline_by_cnpj(pipeline_id, cnpjs: list[str]) -> set[str]` — bulk dup-check
- `insert_stage_change(card_id, *, from_stage_id, to_stage_id, changed_by_user_id) -> None`

Mínimo 20 testes. Coverage 100%. Commit `feat(pipeline): CardRepository com JOIN denormalizado e bulk ops`.

---

### Task 12: Cards — service (CRUD + move com history)

**Files:** Create `api/modules/pipeline/cards/service.py` + `api/tests/test_pipeline_cards_service.py`

Service:
- `create_card(repo, *, pipeline_id, payload, current_user_id)` — valida CNPJ existe; valida não duplicado; resolve stage_id (default = primeiro stage do pipeline); calcula position = max+1; insere card + 1 stage_change (from=NULL).
- `list_cards(repo, pipeline_id)` — retorna `list[CardWithCompany]`.
- `update_card(repo, card, payload)`.
- `move_card(repo, card, new_stage_id, new_position, current_user_id)` — se `new_stage_id != card.stage_id`: valida stage pertence ao mesmo pipeline (`stage_not_in_pipeline`), insere `stage_change`. Sempre faz UPDATE.
- `delete_card(repo, card_id)`.
- `cards_by_cnpj(repo, *, owner_user_id, cnpj_basico)`.

Mínimo 14 testes. Cover error paths: cnpj_not_found, card_duplicate, stage_not_in_pipeline. Coverage 100%. Commit.

---

### Task 13: Cards — router + dependencies `owned_card`

**Files:** Modify `api/modules/pipeline/dependencies.py`, Create `api/modules/pipeline/cards/router.py` + `api/tests/test_pipeline_cards_router.py`

Adicionar em `dependencies.py`:
- `get_card_repo() -> CardRepository`
- `owned_card(card_id, pipeline=Depends(owned_pipeline), repo=Depends(get_card_repo)) -> CardRecord`

Router: 7 endpoints (list, create, get, patch, move, delete, by-cnpj). `POST /pipelines/{id}/cards` rate-limit 600/h/user. `by-cnpj` está sob `/pipelines/cards/by-cnpj/{cnpj_basico}` — registrar **antes** das rotas com `{pipeline_id}` no router para evitar match incorreto.

Mínimo 14 testes. Coverage 100%. Commit.

---

### Task 14: Cards — CSV import (`csv_import.py`)

**Files:** Create `api/modules/pipeline/cards/csv_import.py` + `api/tests/test_pipeline_csv_import.py`

Módulo expõe:
- `MAX_FILE_BYTES = 2 * 1024 * 1024`
- `MAX_ROWS = 5000`
- `class ImportResult(BaseModel): created: int; skipped: list[SkippedRow]; summary: ImportSummary`
- `class SkippedRow(BaseModel): line: int; cnpj: str; reason: Literal["invalid_cnpj_format","cnpj_not_found","duplicate_in_pipeline"]`
- `def normalize_cnpj(raw: str) -> str | None` — extrai 8 dígitos ou None
- `def parse_csv(content: str) -> list[tuple[int, str]]` — retorna [(line_number, raw_cnpj), ...]; detecta separador via `csv.Sniffer`; pula header se primeira linha não normaliza para CNPJ válido
- `async def import_cards(repo_card, *, pipeline_id, stage_id, current_user_id, content: str) -> ImportResult` — orquestra: parse → normalize → dedup intra-arquivo → bulk_exists check → bulk_dup check → bulk_insert + stage_changes

Testes mínimo 20: separador `,`/`;`, com/sem header, todos os reason codes, formatado (`12.345.678/0001-00`), 8 dígitos cru, dígitos errados, > 2MB → raises 413, > 5k linhas → raises 413, sucesso parcial, BOM, CRLF, etc.

Coverage 100%. Endpoint `POST /pipelines/{pid}/cards/import` adicionado em `cards/router.py` (rate-limit 10/h/user). Testes do endpoint em `test_pipeline_cards_router.py`.

Commit: `feat(pipeline): import CSV com normalização, bulk validation e reasons estáveis`.

---

### Task 15: Activities — slice completo

**Files:** Create `api/modules/pipeline/activities/{repository.py,schemas.py,service.py,router.py}` + `api/tests/test_pipeline_activities.py`

Endpoints sob `/pipelines/{pid}/cards/{cid}/activities`. Schemas: `ActivityCreate(kind: Literal['note','call','email','meeting'], body, occurred_at?)`, `ActivityPatch(body)`, `ActivityRecord`. Cursor pagination (`?cursor&limit`, default 50, max 100) por `occurred_at DESC`.

Adicionar em `dependencies.py`: `get_activity_repo`, `owned_activity(activity_id, card=Depends(owned_card), repo=...)`.

Mínimo 15 testes cobrindo CRUD + paginação + autoria. Coverage 100%. Commit.

---

### Task 16: Tasks — slice completo

**Files:** Create `api/modules/pipeline/tasks/{repository.py,schemas.py,service.py,router.py}` + `api/tests/test_pipeline_tasks.py`

Endpoints sob `/pipelines/{pid}/cards/{cid}/tasks` + `/pipelines/tasks/mine` (cross-pipeline para current_user, abertas only, ORDER BY `due_at NULLS LAST`). Schemas: `TaskCreate(title, due_at?, assignee_user_id?)` (default = current_user), `TaskPatch(title?, due_at?, done_at?)`.

Adicionar em `dependencies.py`: `get_task_repo`, `owned_task`.

Mínimo 15 testes. Coverage 100%. Commit.

---

### Task 17: Testes de autorização cross-user

**Files:** Create `api/tests/test_pipeline_authorization.py`

Cenários:
- User B tenta GET/PATCH/DELETE pipeline de A → 404 `pipeline_not_found` (não 403)
- Mesmo para stage, card, activity, task
- Move card pra stage de outro pipeline (mesmo user) → 422 `stage_not_in_pipeline`
- POST sem `X-CSRF-Token` → 403 (do middleware)
- GET/POST sem cookie de sessão → 401

Mínimo 12 testes. Não inflar coverage do módulo (já está 100%); este arquivo é defesa em profundidade. Commit `test(pipeline): cross-user 404 e CSRF/auth gates`.

---

### Task 18: Testes do `__init__` e `router.py` agregador

**Files:** Create `api/tests/test_pipeline_main_wiring.py`

Validar:
- `from modules.pipeline import router` funciona
- Todas as 5 sub-rotas estão em `router.routes` (≥ 30 routes total)
- `create_app()` inclui o pipeline router com prefix `/v1`
- Tags OpenAPI corretas em `app.openapi()`

Coverage 100% nos `__init__.py` e no `router.py` agregador. Commit.

---

### Task 19: Atualizar `conftest.py` raiz

**Files:** Modify `api/tests/conftest.py`

Adicionar à lista de `patchers` em `client()`:

```python
patch("modules.pipeline.dependencies.get_pool", new_callable=AsyncMock, return_value=mock_pool),
```

(Os outros mocks de `get_pool` por módulo já cobrem `core.db.get_pool` direto, mas como `dependencies.py` do pipeline importa `from core.db import get_pool`, o patch global de `core.db.get_pool` já intercepta. Verificar; este step pode ser no-op se já funcionar.)

Smoke run: `pytest -x` deve passar em todo o repo.

Commit (mesmo que vazio, documenta validação): `test(pipeline): garante client fixture compatível com pipeline module`.

---

### Task 20: Verificação final

- [ ] **Step 1: Cobertura 100% no módulo inteiro**

```bash
cd api && pytest --cov=modules/pipeline --cov-fail-under=100 -q
```
Expected: `Required test coverage of 100% reached. Total coverage: 100.00%`.

- [ ] **Step 2: Cobertura global 100%**

```bash
cd api && pytest -q
```
Expected: `--cov-fail-under=100` passa.

- [ ] **Step 3: import-linter passa**

```bash
cd api && lint-imports
```

- [ ] **Step 4: App sobe e OpenAPI lista endpoints**

```bash
cd api && python -c "
from main import create_app
app = create_app()
pipeline_routes = [r.path for r in app.routes if '/v1/pipelines' in getattr(r, 'path', '')]
print(f'Pipeline routes: {len(pipeline_routes)}')
for p in sorted(pipeline_routes): print(' ', p)
"
```
Expected: ≥ 25 rotas listadas sob `/v1/pipelines`.

- [ ] **Step 5: Smoke manual (opcional, com Postgres dev)**

Aplicar migration, subir API local, criar user, fazer fluxo:
```bash
# Aplicar migration
psql -h localhost -U postgres -d cnpj_dev -f db/migrations/019_pipeline.sql

# Subir API
cd api && uvicorn main:app --reload

# Em outro terminal: registrar user, fazer login, criar pipeline, add card, mover, deletar.
# Via /docs (Swagger) ou curl.
```

- [ ] **Step 6: Commit final de marker**

```bash
git commit --allow-empty -m "feat(pipeline): sub-projeto #4 completo (backend pronto para #5)

Pipeline backend implementado: migration 019, módulo
api/modules/pipeline/ com 5 entidades, CSV import, autorização
owner-only, cobertura 100%, import-linter passa.

Próximo: sub-projeto #5 (frontend kanban + drag-drop).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review (executado pelo planner)

**1. Spec coverage:** Cada seção do spec mapeada para uma task:
- §3 (Estrutura) → Tasks 2, 3
- §4 (Modelo) → Task 1 (schema), 6, 9, 11, 15, 16 (repos refletem modelo)
- §5 (Schema SQL) → Task 1
- §6 (API surface) → Tasks 8, 10, 13, 15, 16
- §7 (CSV import) → Task 14
- §8 (Segurança) → Tasks 4 (errors), 8 (deps owned_*), 17 (cross-user)
- §9 (Testes) → Cada task tem seus tests + Task 17 (cross-user)
- §10 (Performance) → Task 11 (`list_with_company_summary` JOIN; `bulk_*` queries)
- §11 (Integração #5/#6) → Task 13 (`by-cnpj` endpoint)
- §12 (Checklist) → Task 20

**2. Placeholder scan:** Nenhum TBD/TODO. Tasks 6, 9–16 referenciam o padrão repetitivo §"Padrão das entidades" — é repetição estruturada, não placeholder.

**3. Type consistency:** Schemas referenciados (PipelineRecord, StageRecord, CardRecord, etc.) consistentes entre tasks. `pipeline_error(ErrorCode.X)` é a API única de erros.

**4. Coverage do plano vs spec:** Tudo coberto. Test de wiring (Task 18) garante 100% nos __init__.py.

---

## Execução

Após salvar este plano, executar via **subagent-driven-development** (recomendado): subagent fresh por task, revisão entre tasks.

