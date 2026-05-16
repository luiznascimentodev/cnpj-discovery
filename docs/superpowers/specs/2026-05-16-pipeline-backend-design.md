# Pipeline Backend — Design

**Data:** 2026-05-16
**Projeto:** CNPJ Discovery
**Sub-projeto #4 de 6** no plano de embelezamento (ver spec `2026-05-14-design-system-foundation-design.md` §1)
**Depende de:** #2 (Auth — em produção)
**Status:** Spec aprovado pelo usuário — pronto para writing-plans

---

## 1. Objetivo

Adicionar ao backend (FastAPI, Modular Monolith) a feature de **Pipeline de Vendas estilo Kanban**: o usuário autenticado cria múltiplos pipelines, cada um com estágios customizáveis e cards representando empresas (CNPJs) em movimento por esses estágios. Inclui atividades (timeline de notas/calls/emails/meetings), tarefas (to-dos com due date) e auditoria automática de mudança de estágio.

Sub-projeto #5 (frontend kanban + drag-drop + batch import) e #6 (refator Prospecting com botão "enviar para pipeline") consomem esta API.

## 2. Decisões fechadas (resumo do brainstorming)

| Tema | Decisão |
|---|---|
| Cardinalidade pipeline ↔ user | **Multi-pipeline** por usuário, estágios **customizáveis** |
| O que é um card | **Empresa** = 1 `cnpj_basico` (8 dígitos) |
| Escopo de features | **Completo**: cards + activities + tasks + history de stage |
| Permissões | **Owner-only** (sem teams/workspaces agora) |
| Adicionar cards | **Manual** (1 por vez) + **import CSV** (lote) |
| Formato de import | **CSV apenas** (stdlib `csv`, sem `openpyxl`) |
| Organização do módulo | **Único `api/modules/pipeline/`** com subpastas internas por entidade |

## 3. Arquitetura

### 3.1 Lugar no projeto

`api/modules/pipeline/` — vertical slice padrão do Modular Monolith do projeto (ver memória `backend-architecture`). Cross-cutting (DB pool, CSRF, rate-limit, current_user) reutiliza `api/core/` existente.

### 3.2 Estrutura de arquivos

```
api/modules/pipeline/
├── __init__.py              # exporta router público
├── router.py                # APIRouter raiz que monta sub-routers
├── dependencies.py          # owned_pipeline, owned_card, owned_stage, get_*_repo
├── errors.py                # mapping code → HTTPException
│
├── pipelines/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
│
├── stages/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py           # inclui DEFAULT_STAGES e reorder
│   ├── repository.py
│   └── schemas.py
│
├── cards/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py        # inclui list_with_company_summary (JOIN empresas+estabelecimentos)
│   ├── schemas.py
│   └── csv_import.py        # parser, normalizer, batch insert
│
├── activities/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
│
├── tasks/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_pipelines.py
    ├── test_stages.py
    ├── test_cards.py
    ├── test_csv_import.py
    ├── test_activities.py
    ├── test_tasks.py
    ├── test_authorization.py
    └── test_audit_history.py
```

### 3.3 Wiring em `api/main.py`

Uma linha de import e uma linha de `include_router`:

```python
from modules.pipeline import router as pipeline_router
# ...
app.include_router(pipeline_router, prefix="/v1")
```

`openapi_tags` ganha: `pipelines`, `pipeline_stages`, `pipeline_cards`, `pipeline_activities`, `pipeline_tasks`.

### 3.4 Import-linter

Adicionar em `api/.importlinter`:

```ini
[importlinter:contract:pipeline-internal-layers]
name = Pipeline submodules must follow router → service → repository
type = layers
layers =
    modules.pipeline.**.router
    modules.pipeline.**.service
    modules.pipeline.**.repository
```

## 4. Modelo de domínio

```
users (já existe)
  └── pipelines (1:N — owner_user_id)
        ├── pipeline_stages (1:N — ordenadas via position)
        └── pipeline_cards (1:N) — referencia stage_id e cnpj_basico
              ├── pipeline_card_activities (1:N)
              ├── pipeline_card_tasks       (1:N)
              └── pipeline_card_stage_changes (1:N — auditoria automática)
```

### 4.1 Regras

- Pipeline tem **pelo menos 1 stage** sempre. Criação do pipeline cria stages default.
- Stages default: `Lead → Contatado → Qualificado → Proposta → Ganho → Perdido` (usuário renomeia/reordena/apaga depois). `Ganho` é criado com `is_won=true`; `Perdido` com `is_lost=true`.
- Card é único por `(pipeline_id, cnpj_basico)` — não duplica a mesma empresa no mesmo pipeline (mas pode aparecer em pipelines diferentes do mesmo user).
- Apagar pipeline cascateia tudo (stages, cards, activities, tasks, history).
- Apagar stage com cards: **proibido** se for o último; senão exige `?move_cards_to={sid}` na request.
- Apagar card cascateia activities/tasks/history.
- `pipeline_card_stage_changes` é populado **automaticamente** pelo service ao criar ou mover card. Não é endpoint manual.
- `cnpj_basico` no card **não** tem FK pra `empresas`. Razão: `empresas` é re-importada por ETL mensal e FK travaria/atrapalharia o ETL; validação acontece na camada de service.

### 4.2 Cascades

| De | Para | Cascade on delete |
|---|---|---|
| user | pipeline | CASCADE |
| pipeline | stage | CASCADE |
| pipeline | card | CASCADE |
| stage | card | RESTRICT (precisa mover antes) |
| card | activity, task, stage_change | CASCADE |
| user | activity.author / task.assignee | RESTRICT (limitação conhecida enquanto owner-only) |

## 5. Schema SQL (`db/migrations/019_pipeline.sql`)

```sql
-- ============================================================
-- Pipelines (boards)
-- ============================================================
CREATE TABLE pipelines (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  description  TEXT,
  archived_at  TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipelines_owner_active ON pipelines (owner_user_id, created_at DESC)
  WHERE archived_at IS NULL;

-- ============================================================
-- Stages (colunas do kanban)
-- ============================================================
CREATE TABLE pipeline_stages (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id  UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  position     INTEGER NOT NULL,
  color        TEXT,
  is_won       BOOLEAN NOT NULL DEFAULT FALSE,
  is_lost      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (NOT (is_won AND is_lost)),
  CHECK (position >= 0)
);
CREATE INDEX pipeline_stages_pipeline ON pipeline_stages (pipeline_id, position);

-- ============================================================
-- Cards (empresas no pipeline)
-- ============================================================
CREATE TABLE pipeline_cards (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id     UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  stage_id        UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
  cnpj_basico     CHAR(8) NOT NULL,
  position        INTEGER NOT NULL,
  estimated_value_cents BIGINT,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, cnpj_basico),
  UNIQUE (stage_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (position >= 0),
  CHECK (cnpj_basico ~ '^\d{8}$')
);
CREATE INDEX pipeline_cards_stage ON pipeline_cards (stage_id, position);
CREATE INDEX pipeline_cards_pipeline ON pipeline_cards (pipeline_id);
CREATE INDEX pipeline_cards_cnpj ON pipeline_cards (cnpj_basico);

-- ============================================================
-- Atividades (timeline)
-- ============================================================
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

-- ============================================================
-- Tasks (to-do)
-- ============================================================
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

-- ============================================================
-- Histórico de mudança de stage
-- ============================================================
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

### 5.1 Notas de schema

1. `UNIQUE (pipeline_id, position)` e `UNIQUE (stage_id, position)` são **DEFERRABLE INITIALLY DEFERRED** — permite UPDATE em batch de positions numa transação sem conflito intermediário (essencial pra drag-drop).
2. `cnpj_basico` sem FK pra `empresas` (justificativa em §4.1).
3. `is_won`/`is_lost` no stage habilita relatórios de funil sem hardcodar nomes.
4. `position` INTEGER simples (não fractional indexing). Drag-drop faz UPDATE em batch.
5. CHECK `cnpj_basico ~ '^\d{8}$'` defesa em profundidade contra dados malformados; Pydantic também valida.

## 6. API surface

Prefixo `/v1`. Todos os endpoints exigem `Depends(get_current_user)`; mutações exigem CSRF (header `X-CSRF-Token`).

### 6.1 Pipelines

| Método | Path | Resumo |
|---|---|---|
| `GET`    | `/pipelines` | Lista; `?archived=true` inclui arquivados |
| `POST`   | `/pipelines` | Cria; `{name, description?}`; cria stages default |
| `GET`    | `/pipelines/{id}` | Detalhe + counts (cards/stage, valor total) |
| `PATCH`  | `/pipelines/{id}` | Atualiza `name`, `description` |
| `POST`   | `/pipelines/{id}/archive` | Soft-delete (`archived_at = now()`) |
| `POST`   | `/pipelines/{id}/unarchive` | Reverte (409 se não arquivado) |
| `DELETE` | `/pipelines/{id}` | Hard delete (cascade); confirmação no frontend |

### 6.2 Stages

| Método | Path | Resumo |
|---|---|---|
| `GET`    | `/pipelines/{pid}/stages` | Lista ordenada |
| `POST`   | `/pipelines/{pid}/stages` | `{name, color?, is_won?, is_lost?, position?}` |
| `PATCH`  | `/pipelines/{pid}/stages/{sid}` | `name`, `color`, `is_won`, `is_lost` |
| `POST`   | `/pipelines/{pid}/stages/reorder` | `{stage_ids: [...]}` ordem desejada |
| `DELETE` | `/pipelines/{pid}/stages/{sid}` | Apaga; `?move_cards_to={sid}` se tem cards; 409 se for o último |

### 6.3 Cards

| Método | Path | Resumo |
|---|---|---|
| `GET`    | `/pipelines/{pid}/cards` | Lista do pipeline com JOIN denormalizado (razão social + UF) |
| `POST`   | `/pipelines/{pid}/cards` | `{cnpj_basico, stage_id?, estimated_value_cents?, notes?}`; valida CNPJ |
| `GET`    | `/pipelines/{pid}/cards/{cid}` | Detalhe + activities + tasks + history em 1 payload |
| `PATCH`  | `/pipelines/{pid}/cards/{cid}` | `estimated_value_cents`, `notes` |
| `POST`   | `/pipelines/{pid}/cards/{cid}/move` | `{stage_id, position}`; registra `stage_change` se stage mudou |
| `DELETE` | `/pipelines/{pid}/cards/{cid}` | Apaga (cascade) |
| `POST`   | `/pipelines/{pid}/cards/import` | Import CSV — ver §7 |
| `GET`    | `/pipelines/cards/by-cnpj/{cnpj_basico}` | `[{pipeline_id, pipeline_name, card_id, stage_name}]` — para Prospecting |

### 6.4 Activities

| Método | Path | Resumo |
|---|---|---|
| `GET`    | `/pipelines/{pid}/cards/{cid}/activities` | Cursor pagination DESC por `occurred_at` |
| `POST`   | `/pipelines/{pid}/cards/{cid}/activities` | `{kind, body, occurred_at?}` |
| `PATCH`  | `/pipelines/{pid}/cards/{cid}/activities/{aid}` | `body` (só autor) |
| `DELETE` | `/pipelines/{pid}/cards/{cid}/activities/{aid}` | Apaga |

### 6.5 Tasks

| Método | Path | Resumo |
|---|---|---|
| `GET`    | `/pipelines/{pid}/cards/{cid}/tasks` | Lista do card |
| `POST`   | `/pipelines/{pid}/cards/{cid}/tasks` | `{title, due_at?, assignee_user_id?}` (default = current_user) |
| `PATCH`  | `/pipelines/{pid}/cards/{cid}/tasks/{tid}` | `title`, `due_at`, `done_at` (PATCH `done_at:now` = concluir) |
| `DELETE` | `/pipelines/{pid}/cards/{cid}/tasks/{tid}` | Apaga |
| `GET`    | `/pipelines/tasks/mine` | Tasks abertas do user, cross-pipeline, sort `due_at NULLS LAST` |

### 6.6 Error codes (corpo: `{detail: {code: "..."}}`)

| Code | HTTP | Quando |
|---|---|---|
| `pipeline_not_found` | 404 | Pipeline inexistente OU de outro user |
| `stage_not_found`    | 404 | Idem para stage |
| `card_not_found`     | 404 | Idem para card |
| `activity_not_found` | 404 | Idem para activity |
| `task_not_found`     | 404 | Idem para task |
| `cnpj_not_found`     | 422 | CNPJ não existe em `empresas` |
| `card_duplicate`     | 409 | Card já existe para `(pipeline, cnpj_basico)` |
| `cannot_delete_last_stage` | 409 | Tentativa de apagar único stage |
| `stage_has_cards`    | 409 | Apagar stage com cards sem `move_cards_to` |
| `stage_not_in_pipeline` | 422 | `stage_id` em request não pertence ao pipeline |
| `not_archived`       | 409 | `unarchive` em pipeline não arquivado |

### 6.7 Convenções

- **Cursor pagination** em listagens longas (activities, tasks): `?cursor=...&limit=50`, `limit` ≤ 100. Mesmo padrão de prospecting.
- **404 vs 403:** retornamos **404** para recursos de outros users (não 403) — evita vazar existência de IDs.
- **assignee_user_id** em tasks: enquanto owner-only, na prática só faz sentido `current_user`; mantido pra não quebrar quando `pipeline_members` for adicionado.

## 7. CSV Import

### 7.1 Endpoint

`POST /v1/pipelines/{pid}/cards/import`

- **Content-Type:** `multipart/form-data` (campo `file`) **ou** `text/csv` (body cru).
- **Query opcional:** `?stage_id={sid}` — destino dos cards. Default: stage com menor `position`.
- **Limites:** arquivo ≤ 2 MB, ≤ 5.000 linhas. Erro `413 payload_too_large` se exceder.
- **Rate limit:** 10/h/user.

### 7.2 Formato

CSV (separador `,` ou `;` detectado via `csv.Sniffer`), com ou sem header. Uma coluna obrigatória: CNPJ.

```
cnpj
12.345.678/0001-00
98765432000199
11.222.333
```

### 7.3 Normalização

1. Tira tudo que não é dígito.
2. Se sobrar 14 dígitos: usa primeiros 8 como `cnpj_basico`.
3. Se sobrar 8 dígitos: usa direto.
4. Outra quantidade: linha rejeitada com `reason: "invalid_cnpj_format"`.

Se primeira linha não parsear como CNPJ válido, assume header e pula.

### 7.4 Resposta

```json
{
  "created": 142,
  "skipped": [
    {"line": 5,  "cnpj": "12345",    "reason": "invalid_cnpj_format"},
    {"line": 12, "cnpj": "00000000", "reason": "cnpj_not_found"},
    {"line": 38, "cnpj": "11222333", "reason": "duplicate_in_pipeline"}
  ],
  "summary": {
    "total_rows": 150,
    "invalid_format": 1,
    "not_found": 1,
    "duplicates": 1
  }
}
```

Reasons: `invalid_cnpj_format`, `cnpj_not_found`, `duplicate_in_pipeline`.

### 7.5 Implementação

1. Stream do arquivo pra `io.StringIO` (cap 2 MB).
2. `csv.Sniffer` detecta separador.
3. Coleta lista de `cnpj_basico` candidatos (até 5k); deduplica intra-arquivo (primeira ocorrência ganha).
4. **Uma query** valida quais existem: `SELECT cnpj_basico FROM empresas WHERE cnpj_basico = ANY($1)`.
5. **Uma query** detecta duplicatas com cards existentes no pipeline.
6. **Uma transação** INSERT em batch (`executemany`) para os válidos. `position` continua do `MAX + 1` do stage destino.
7. Cria 1 `stage_change` por card criado (`from_stage_id = NULL`).

### 7.6 Por quê esse formato

- 1 coluna mantém endpoint enxuto; user sobe SELECT exportado de Excel.
- Sem `pandas` ou `openpyxl` — `csv` stdlib basta.
- Resposta com `line` permite UI apontar erros sem reabrir arquivo.
- Reason codes estáveis; i18n no frontend.

## 8. Autorização e segurança

### 8.1 Dependencies declarativas

```python
# api/modules/pipeline/dependencies.py
async def owned_pipeline(
    pipeline_id: UUID,
    user: UserRecord = Depends(get_current_user),
    repo: PipelineRepo = Depends(get_pipeline_repo),
) -> PipelineRecord:
    pipeline = await repo.get_for_owner(pipeline_id, owner_user_id=user.id)
    if not pipeline:
        raise HTTPException(404, detail={"code": "pipeline_not_found"})
    return pipeline

async def owned_card(
    card_id: UUID,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: CardRepo = Depends(get_card_repo),
) -> CardRecord:
    card = await repo.get_in_pipeline(card_id, pipeline_id=pipeline.id)
    if not card:
        raise HTTPException(404, detail={"code": "card_not_found"})
    return card
```

Handlers ficam triviais:

```python
@router.delete("/pipelines/{pipeline_id}/cards/{card_id}")
async def delete_card(card: CardRecord = Depends(owned_card)):
    ...
```

### 8.2 Princípio "404, não 403"

Recursos de outros users retornam **404**, não 403 — evita vazar existência de IDs. Violação de regra de negócio em recurso já autorizado retorna **409** com `code` explícito.

### 8.3 CSRF

Todas mutações (`POST/PATCH/DELETE`) exigem `X-CSRF-Token` via middleware `core.csrf` existente. Reutiliza cookie emitido por `/v1/auth/csrf`. Sem mudanças no core.

### 8.4 Rate limit

| Endpoint | Limite (por user) |
|---|---|
| `POST /pipelines/{id}/cards/import` | 10/h |
| `POST /pipelines` | 30/h |
| `POST /pipelines/{id}/cards` | 600/h (= 10/min) |
| Demais | default global do middleware |

Via `core.rate_limit.limit("nome", user_scoped=True)`.

### 8.5 Validação de input

- Pydantic `BaseModel` em todos schemas; `Field(max_length=...)` em TEXT:
  - pipeline.name ≤ 120; pipeline.description ≤ 2000
  - stage.name ≤ 80; stage.color ≤ 32
  - card.notes ≤ 10000
  - activity.body ≤ 10000
  - task.title ≤ 200
- `cnpj_basico` `Field(pattern=r"^\d{8}$")` na escrita; no import normalizador roda antes.
- `position` ≥ 0 (CHECK no schema).
- `kind` de activity restrito ao enum `('note','call','email','meeting')` (CHECK + `Literal` Pydantic).

### 8.6 Auditoria

- `pipeline_card_stage_changes` registra automaticamente toda criação/movimentação.
- Sem auditoria genérica de CRUD (overengineering pra owner-only). `created_at`/`updated_at` em cada tabela é suficiente.

### 8.7 LGPD / delete user

`users.id` é FK `ON DELETE CASCADE` em `pipelines.owner_user_id` → cascade até history. Tasks com `assignee_user_id` para outro user bloqueiam (RESTRICT) — limitação conhecida enquanto owner-only; será tratado quando entrar `pipeline_members`.

## 9. Estratégia de testes

### 9.1 Stack

`pytest-asyncio` + `httpx.AsyncClient` (`ASGITransport`) contra o `app` real, banco Postgres de testes (fixture já existente no projeto). Sem mocks de DB.

### 9.2 Cobertura alvo

**100%** — segue regra do projeto (CI gate). Sem exceções.

### 9.3 Fixtures novas (`pipeline/tests/conftest.py`)

| Fixture | Função |
|---|---|
| `authed_client` | `AsyncClient` com sessão válida + CSRF, user criado on-the-fly |
| `other_authed_client` | Segundo user — para cross-user 404 |
| `pipeline_factory` | Cria pipeline + stages default |
| `stage_factory`, `card_factory`, `activity_factory`, `task_factory` | Builders mínimos para arrange |
| `cnpj_factory` | Insere registro mínimo em `empresas`+`estabelecimentos` para CNPJ aleatório válido |

### 9.4 Cobertura por arquivo

**`test_pipelines.py`**
- Criação cria 6 stages default na ordem correta com `is_won`/`is_lost` setados.
- Lista exclui arquivados por default; inclui com `?archived=true`.
- Archive idempotente; unarchive de não-arquivado → 409 `not_archived`.
- Delete cascateia stages/cards.
- PATCH respeita `max_length` (422).

**`test_stages.py`**
- Reorder em batch atualiza positions atomicamente (DEFERRED constraint).
- Delete último stage → 409 `cannot_delete_last_stage`.
- Delete stage com cards sem `?move_cards_to=` → 409 `stage_has_cards`; com query válida move e apaga.
- CHECK `is_won XOR is_lost` rejeita combinação inválida.

**`test_cards.py`**
- Create valida CNPJ existe; CNPJ inexistente → 422 `cnpj_not_found`.
- Create duplicado → 409 `card_duplicate`.
- `position` default = último do stage.
- Move dentro do mesmo stage (só reordena) NÃO cria `stage_change`.
- Move pra outro stage cria 1 `stage_change` com `from`/`to` corretos.
- List retorna `razao_social` e UF via JOIN.
- `GET /cards/by-cnpj/{cnpj}` retorna pipelines do user atual apenas.

**`test_csv_import.py`** (mais denso)
- Separador `,` e `;` ambos parseiam.
- Header detectado e pulado quando primeira linha não é CNPJ.
- 14 dígitos formatado (`12.345.678/0001-00`) → extrai `cnpj_basico`.
- 8 dígitos cru → aceito.
- Quantidade inválida → `invalid_cnpj_format`.
- CNPJ não existe → `cnpj_not_found`.
- Duplicado intra-arquivo → primeira ocorrência cria, demais `duplicate_in_pipeline`.
- CNPJ já no pipeline → `duplicate_in_pipeline`.
- Arquivo > 2 MB → 413.
- Mais que 5k linhas → 413.
- Sucesso parcial: `created` e `skipped` corretos.
- Cards criados ganham `stage_change` com `from = NULL`.
- 11ª chamada na mesma hora → 429.

**`test_activities.py`**
- CRUD de cada `kind`.
- `occurred_at` aceita backdate.
- Cursor pagination retorna ordem DESC consistente.

**`test_tasks.py`**
- CRUD; `done_at = now` marca concluído.
- `GET /tasks/mine` retorna só tasks abertas do user, cross-pipeline; ordena por `due_at NULLS LAST`.

**`test_authorization.py`**
- User A não vê pipeline/stage/card/activity/task de user B (404, nunca 403, nunca leak).
- Mutação sem CSRF → 403.
- Mover card pra stage de outro pipeline → 422 `stage_not_in_pipeline`.
- Endpoints sem cookie → 401.

**`test_audit_history.py`**
- Criar card → 1 `stage_change` com `from = NULL, to = stage_inicial`.
- Mover A→B→C → 3 stage_changes na ordem correta.
- Mover dentro do mesmo stage não duplica.
- Apagar card cascateia history.

### 9.5 Fora de escopo

- Smoke E2E Playwright (fica no #5).
- Load test do import com 5k linhas (validação manual; sem CI gate).
- Snapshot/contract test contra OpenAPI (nice-to-have).

## 10. Performance

- **Listagem de cards** (`GET /pipelines/{pid}/cards`) faz **1 query** com JOIN em `empresas` + LATERAL JOIN em `estabelecimentos` (matriz, `cnpj_ordem = '0001'`) para retornar `razao_social` e UF — evita N+1.
- **Detalhe do pipeline** (`GET /pipelines/{id}`): 1 query para o pipeline + 1 query agregada (count por stage, soma de `estimated_value_cents`).
- **CSV import:** 1 query de validação + 1 query de duplicate-check + 1 transação batch INSERT. Independente do tamanho do arquivo dentro do limite.
- **Drag-drop reorder** (`POST /stages/reorder` e `POST /cards/{id}/move`): UPDATE em batch numa transação (DEFERRED unique constraints permitem trocar positions sem conflito).

Nenhum endpoint deve fazer mais que ~5 queries por request no caminho normal.

## 11. Integração com outros sub-projetos

- **#5 (Pipeline frontend):** consome toda esta API. JOIN denormalizado em listagem de cards e endpoint `cards/by-cnpj` projetados para evitar N+1 no kanban.
- **#6 (Refator Prospecting):** botão "enviar para pipeline" usa `POST /pipelines/{id}/cards` (1 CNPJ por vez). Pra mostrar badge "esta empresa já está em N pipelines": `GET /cards/by-cnpj/{cnpj_basico}`.

## 12. Sucesso = checklist

- [ ] Migration `019_pipeline.sql` aplicada (CI + prod via deploy auto-migration)
- [ ] Módulo `api/modules/pipeline/` criado seguindo §3.2
- [ ] Contrato import-linter passa
- [ ] Todos endpoints de §6 funcionando, validados via tests
- [ ] Cobertura 100% no módulo
- [ ] OpenAPI (`/docs`) lista todos endpoints com tags corretas
- [ ] Smoke manual: criar pipeline → adicionar card → mover → import CSV → deletar pipeline

## 13. Riscos

| Risco | Mitigação |
|---|---|
| Position INT vs fractional indexing pode reorderear demais com muitos cards | Limitar UI a operações de drag-drop sensatas; reorder em batch é atômico. Reavaliar se algum user real passar 500 cards/stage. |
| CSV malformado (BOM, encoding, line endings) pode crashar parser | `csv.Sniffer` + try/except específico; testes cobrem CSV com BOM e CRLF/LF/CR. |
| `assignee_user_id` RESTRICT bloqueia delete de user | Aceito enquanto owner-only; quando `pipeline_members` entrar, mudar pra SET NULL ou reatribuir ao owner. |
| Cobertura 100% sob multi-subpasta pode forçar testes sem valor | Aceitável — os subpastas têm camadas reais (router/service/repository), não código trivial. |

## 14. Fora de escopo (explícito)

- ❌ Frontend (kanban, drag-drop, batch import UI) → #5
- ❌ Botão "enviar para pipeline" na página de Prospecting → #6
- ❌ Multi-tenant / workspaces / convites de team
- ❌ Webhooks de pipeline (notificar Slack, etc)
- ❌ Email reminder de task vencendo
- ❌ Exportar pipeline para CSV/Excel (somente import por enquanto)
- ❌ Filtros/busca dentro do board (deferred pra quando tiver dados reais e UI estabilizar)
- ❌ Reordering por fractional indexing
- ❌ Suporte a Excel (.xlsx) no import
