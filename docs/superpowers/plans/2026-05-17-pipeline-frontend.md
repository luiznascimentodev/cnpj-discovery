# Pipeline Frontend + CSV Persistence Implementation Plan

> **Modo de execução:** implementar task-by-task, com commit ao final de cada task. Não iniciar código antes de confirmar que a spec `docs/superpowers/specs/2026-05-17-pipeline-frontend-design.md` está aprovada.

**Goal:** Entregar o sub-projeto #5 completo: Kanban frontend operacional com drag-and-drop completo, import CSV persistente/auditável, card com nome livre, activities/tasks no detalhe e otimização para centenas de cards.

**Architecture:** FSD no frontend (`pages/pipeline` compõe `features/pipeline`), backend mantém vertical slice em `api/modules/pipeline`. Drag-and-drop via `@atlaskit/pragmatic-drag-and-drop`; virtualização por coluna via `@tanstack/react-virtual` já existente.

**Hard gates:**

- Backend: `pytest --cov-fail-under=100 -q`
- Backend: `lint-imports`
- Frontend: `npm run lint`
- Frontend: `npm run build`
- Frontend: testes relevantes com Vitest
- Docker final: API rebuild + checks

---

## Task 1: Backend migration para card display_name e CSV import persistence

**Files:**

- Create: `db/migrations/020_pipeline_frontend_imports.sql`

**Implementar:**

- `ALTER TABLE pipeline_cards ADD COLUMN display_name TEXT;`
- índices:
  - `pipeline_cards_pipeline_stage_position (pipeline_id, stage_id, position)`
  - `pipeline_cards_pipeline_updated (pipeline_id, updated_at DESC)`
- tabela `pipeline_card_import_batches`
- tabela `pipeline_card_import_rows`
- `file_size_bytes` em batches.
- unique index operacional:
  - `(owner_user_id, pipeline_id, filename, file_size_bytes)`
- índices em batches/rows conforme spec.

**Validar:**

- Revisão SQL manual.
- Se Postgres dev disponível, aplicar migration.

**Commit:**

```bash
git add db/migrations/020_pipeline_frontend_imports.sql
git commit -m "feat(pipeline): persist CSV imports and card display names"
```

---

## Task 2: Backend schemas/repository para display_name e import batches

**Files:**

- Modify:
  - `api/modules/pipeline/cards/schemas.py`
  - `api/modules/pipeline/cards/repository.py`
  - `api/tests/test_pipeline_cards_repository.py`

**Implementar:**

- `CardCreate.display_name?: string`
- `CardPatch.display_name?: string`
- `CardRecord.display_name?: string`
- `ImportBatchRecord`
- `ImportRowRecord`
- repository:
  - `insert_import_batch(...)`
  - `delete_existing_import_batch_for_file(owner_user_id, pipeline_id, filename, file_size_bytes)`
  - `insert_import_rows(...)`
  - `list_import_batches(pipeline_id)`
  - `list_import_metadata_for_card(card_id)`
  - `bulk_insert` preserva `display_name`
  - `insert` aceita `display_name`
  - `update` atualiza `display_name`

**Testes:**

- Cobrir todos os métodos novos e SQL relevante.
- 100% coverage do repository/schemas tocados.

**Commit:**

```bash
git commit -m "feat(pipeline): repository de imports CSV persistentes"
```

---

## Task 3: Backend CSV import multipart + metadata

**Files:**

- Modify:
  - `api/modules/pipeline/cards/csv_import.py`
  - `api/modules/pipeline/cards/router.py`
  - `api/tests/test_pipeline_csv_import.py`
  - `api/tests/test_pipeline_cards_router.py`

**Implementar:**

- Parser detecta coluna de CNPJ por header (`cnpj`, `cnpj_basico`, `documento`) ou primeira coluna.
- Parser extrai `display_name` de `nome`, `title`, `apelido`, `card_name`.
- Parser preserva colunas extras em `metadata`.
- Calcula `content_sha256`.
- Antes de criar batch, se existir batch anterior com mesmo `owner_user_id + pipeline_id + filename + file_size_bytes`, remove o batch anterior e suas rows.
- Cria import batch mais novo sempre.
- Insere row para cada linha processada:
  - invalid format;
  - CNPJ não encontrado;
  - duplicado;
  - criado.
- Endpoint público vira `multipart/form-data` com:
  - `stage_id`;
  - `file`;
  - `default_display_name?`.
- Mantém função interna testável com `content: str`.
- `ImportResult` inclui `batch_id`.

**Regra de reimport solicitada pelo usuário:**

- Mesmo nome e mesmo tamanho no mesmo pipeline/usuário não pode gerar histórico duplicado.
- Mantemos apenas o batch mais novo.
- Cards já existentes não são duplicados; rows do novo batch registram `duplicate_in_pipeline` quando aplicável.

**Testes:**

- CSV com headers variados.
- CSV sem header.
- metadata JSON.
- upload multipart router.
- hash/batch/rows persistidos.
- reimport com mesmo nome/tamanho remove batch anterior.
- payload > 2MB e > 5000 linhas.

**Commit:**

```bash
git commit -m "feat(pipeline): import CSV multipart com auditoria por linha"
```

---

## Task 4: Backend card service/router display_name

**Files:**

- Modify:
  - `api/modules/pipeline/cards/service.py`
  - `api/modules/pipeline/cards/router.py`
  - `api/tests/test_pipeline_cards_service.py`
  - `api/tests/test_pipeline_cards_router.py`

**Implementar:**

- criação manual com `display_name`;
- update com `display_name`;
- listagem já retorna `display_name`;
- fallback visual fica no frontend, não no backend.

**Commit:**

```bash
git commit -m "feat(pipeline): display name por card"
```

---

## Task 5: Frontend dependency e API client da feature pipeline

**Files:**

- Modify: `frontend/package.json`, lockfile
- Create:
  - `frontend/src/features/pipeline/api.ts`
  - `frontend/src/features/pipeline/schemas.ts`
  - `frontend/src/features/pipeline/hooks.ts`
  - `frontend/src/features/pipeline/index.ts`
  - tests correspondentes

**Instalar:**

```bash
corepack pnpm add @atlaskit/pragmatic-drag-and-drop \
  @atlaskit/pragmatic-drag-and-drop-auto-scroll \
  @atlaskit/pragmatic-drag-and-drop-hitbox \
  @atlaskit/pragmatic-drag-and-drop-react-drop-indicator
```

Se o projeto usa npm na prática, usar `npm install` em vez de pnpm e respeitar lockfile existente.

**Implementar API client:**

- pipelines CRUD básico;
- stages list/create/update/reorder/delete;
- cards list/create/update/move/delete/import;
- activities list/create/update/delete;
- tasks list/create/update/delete/list mine.

**Testes:**

- endpoints e payloads corretos.

**Commit:**

```bash
git commit -m "feat(pipeline): frontend API client e hooks"
```

---

## Task 6: Frontend board model e optimistic updates

**Files:**

- Create:
  - `frontend/src/features/pipeline/model/board.ts`
  - `frontend/src/features/pipeline/model/drag.ts`
  - tests

**Implementar:**

- `groupCardsByStage(stages, cards)`
- `moveCardOptimistically(board, cardId, targetStageId, targetIndex)`
- `reorderStagesOptimistically(...)`
- fallback de label do card:
  - `display_name`
  - `company.razao_social`
  - `cnpj_basico`

**Testes:**

- move dentro da coluna.
- move entre colunas.
- reorder stage.
- cards desconhecidos não quebram.

**Commit:**

```bash
git commit -m "feat(pipeline): modelo de board e optimistic updates"
```

---

## Task 7: Frontend Kanban UI com Pragmatic Drag and Drop

**Files:**

- Create:
  - `PipelineBoard.tsx`
  - `PipelineStageColumn.tsx`
  - `PipelineCard.tsx`
  - `PipelineToolbar.tsx`
  - CSS/Tailwind classes localizadas nos componentes
  - tests

**Implementar:**

- board full-width operacional;
- scroll horizontal de colunas;
- scroll vertical por coluna;
- drag handle explícito;
- drop indicator;
- auto-scroll;
- reorder card dentro da coluna;
- mover card entre colunas;
- reorder stages;
- virtualização por coluna quando `cards.length > 80`.

**Acessibilidade:**

- card focável;
- Enter abre detalhe;
- handle com `aria-label`.

**Commit:**

```bash
git commit -m "feat(pipeline): kanban com drag and drop completo"
```

---

## Task 8: Frontend dialogs de pipeline/card/import

**Files:**

- Create:
  - `CreatePipelineDialog.tsx`
  - `CreateCardDialog.tsx`
  - `ImportCsvDialog.tsx`
  - tests

**Implementar:**

- criar pipeline;
- criar card com `cnpj_basico` + `display_name` opcional;
- importar CSV via arquivo ou textarea;
- mostrar resumo de import:
  - batch id;
  - total;
  - criados;
  - ignorados por reason.

**Commit:**

```bash
git commit -m "feat(pipeline): dialogs de criação e import CSV"
```

---

## Task 9: Frontend card detail com activities/tasks

**Files:**

- Create:
  - `CardDetailDialog.tsx`
  - components auxiliares se necessário
  - tests

**Implementar:**

- editar `display_name`, valor estimado e notes;
- mostrar todos os dados extras vindos do CSV (`metadata`) em seção própria;
- listar/criar activities;
- listar/criar tasks;
- marcar task concluída;
- mover card sem drag via select “Mover para”.

**Commit:**

```bash
git commit -m "feat(pipeline): detalhe de card com atividades e tasks"
```

---

## Task 10: Página `/app/pipeline` completa

**Files:**

- Modify:
  - `frontend/src/pages/pipeline/ui/PipelinePage.tsx`
  - `frontend/src/pages/pipeline/index.ts`
- Add tests.

**Implementar:**

- loading state;
- empty state sem pipeline;
- seletor de pipeline ativo;
- estado de erro;
- composição de toolbar, board e dialogs.

**Commit:**

```bash
git commit -m "feat(pipeline): página operacional do pipeline"
```

---

## Task 11: Validação frontend visual e responsiva

**Executar:**

- `npm run lint`
- `npm run build`
- `npm run test`
- iniciar dev server ou usar Docker frontend;
- screenshot desktop e tablet via Playwright se disponível.

**Validar manualmente:**

- textos não sobrepõem;
- board ocupa a tela operacional, sem aparência de landing;
- drag funciona;
- dialogs cabem em viewport menor;
- import mostra resultado.
- detalhe do card mostra metadata do CSV.

**Commit se houver ajuste:**

```bash
git commit -m "test(pipeline): validação visual e responsiva do kanban"
```

---

## Task 12: Validação Docker full-stack

**Executar:**

```bash
docker compose build api frontend
docker compose up -d api frontend nginx
docker compose exec -T api sh -lc 'python -m pip install -r requirements-dev.txt && pytest --cov-fail-under=100 -q && lint-imports'
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npm run test
```

**Smoke:**

- `/app/pipeline` renderiza.
- API lista OpenAPI com novos campos.
- CSV import não quebra.

**Commit final marker:**

```bash
git commit --allow-empty -m "feat(pipeline): sub-projeto #5 completo (kanban frontend pronto)"
```

---

## Riscos e mitigação

- **CSV vira fonte de dados sensível:** salvar CNPJ, display_name e metadata do CSV; expor metadata somente no detalhe do card do usuário dono.
- **Board pesado:** virtualização por coluna e lazy load de detalhe.
- **DnD complexo:** usar Pragmatic DnD para eventos/auto-scroll/hitbox e manter nosso estado em funções puras testadas.
- **Backend import atual inadequado para upload:** corrigir antes da UI pública.
- **Reorder com muitos cards:** apenas enviar mutation do card movido para o backend; evitar batch reorder global de todos os cards.

## Decisões finais do usuário

- Mostrar no detalhe do card tudo que vier de colunas extras do CSV.
- Se o usuário importar arquivo com mesmo nome e mesmo tamanho, checar e não duplicar; manter apenas o import mais novo.
