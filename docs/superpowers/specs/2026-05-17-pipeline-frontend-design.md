# Pipeline Frontend — Design

**Data:** 2026-05-17
**Projeto:** CNPJ Discovery
**Sub-projeto #5 de 6** no plano de embelezamento
**Depende de:** #1 Design System Foundation + App Shell, #4 Pipeline backend
**Status:** Aprovado em escopo pelo usuário — pronto para plano de implementação

---

## 1. Objetivo

Implementar a experiência full-stack do **Pipeline de Vendas estilo Kanban** em `/app/pipeline`, evoluindo a API do sub-projeto #4 quando necessário:

- múltiplos pipelines por usuário;
- board Kanban com colunas customizáveis;
- drag-and-drop de cards entre stages e dentro da mesma stage;
- criação/edição básica de cards;
- detalhe de card com notas, atividades e tasks;
- importação em lote via CSV com persistência auditável do arquivo/linhas para o usuário e para inteligência/enriquecimento de CNPJs;
- feedback de erro/sucesso e estados loading/empty;
- aderência ao Design System Foundation e às regras FSD.

Este sub-projeto não altera a página de prospecção. A integração “Enviar para pipeline” fica no sub-projeto #6.

## 1.1 Decisões do usuário

- CSV import **não pode ser descartável**: tudo que o usuário subir deve ser salvo no banco, vinculado ao usuário/import e, quando possível, ao `cnpj_basico`.
- CSV deve ser analisado para extrair dados úteis para nossos dados/enriquecimento de CNPJ.
- Todas as colunas extras do CSV devem aparecer no detalhe do card quando houver linha de import associada.
- Se o usuário importar arquivo com mesmo nome e mesmo tamanho para o mesmo pipeline, o sistema não duplica nada e mantém apenas o import mais novo.
- Drag-and-drop deve ser completo já nesta fase: mover entre colunas e reordenar dentro da coluna.
- Card manual pode ser criado digitando somente `cnpj_basico`; não precisa busca/autocomplete.
- Card também pode ter um **nome livre do usuário**, visível apenas para ele naquele card.
- Responsável das tasks é sempre o usuário logado.
- Otimizar desde já para centenas de cards por pipeline.
- Incluir índices/migrations para evitar peso desnecessário no banco.

## 2. Decisão de biblioteca drag-and-drop

### 2.1 Recomendação

Usar **`@atlaskit/pragmatic-drag-and-drop`** como motor de drag-and-drop, com opcionais:

- `@atlaskit/pragmatic-drag-and-drop-auto-scroll`;
- `@atlaskit/pragmatic-drag-and-drop-hitbox`;
- `@atlaskit/pragmatic-drag-and-drop-react-drop-indicator`.

Renderizar o board com componentes próprios do CNPJ Discovery, em vez de usar um componente Kanban pronto.

### 2.2 Por quê

O usuário pediu para usar a melhor biblioteca gratuita e evitar reinventar o drag-and-drop. A análise atual:

| Opção | Status | Decisão |
|---|---|---|
| `@atlaskit/pragmatic-drag-and-drop` | Apache-2.0, Atlassian, pacote atual `1.8.1`, criado como sucessor do `react-beautiful-dnd` | **Escolhida** |
| `@dnd-kit/core` + `@dnd-kit/sortable` | MIT, madura, boa acessibilidade, mas hoje tem uma linha nova de docs/API e exige mais montagem manual | Alternativa segura |
| `react-beautiful-dnd` | Depreciado pela Atlassian e repo arquivado | Rejeitada |
| `react-trello` | Kanban pronto, mas dependências antigas como Redux 4/React Redux 5 e modelo visual próprio | Rejeitada |
| `react-kanban-kit` | Usa Pragmatic DnD e virtualização, mas npm atual está em `0.0.2-beta.7` | Rejeitada por maturidade |

Usar um Kanban pronto parece acelerar a primeira tela, mas cobra caro depois: modelo de dados próprio, tema fora do Design System, dificuldade para activities/tasks/import CSV e menor controle de optimistic updates. O melhor equilíbrio é **não escrever DnD do zero**, mas escrever nosso board por cima do motor Atlassian.

### 2.3 Fontes verificadas

- Atlassian Pragmatic Drag and Drop GitHub: https://github.com/atlassian/pragmatic-drag-and-drop
- NPM `@atlaskit/pragmatic-drag-and-drop`: https://www.npmjs.com/package/@atlaskit/pragmatic-drag-and-drop
- Atlassian sobre depreciação do `react-beautiful-dnd`: https://github.com/atlassian/react-beautiful-dnd/issues/2672
- dnd kit sortable docs: https://docs.dndkit.com/presets/sortable
- NPM `react-trello`: https://www.npmjs.com/package/react-trello
- NPM `react-kanban-kit`: https://www.npmjs.com/package/react-kanban-kit

## 3. Escopo funcional

### 3.1 Pipelines

- Listar pipelines do usuário.
- Criar pipeline.
- Selecionar pipeline ativo.
- Ver resumo por stage: quantidade de cards e valor total.
- Arquivar/desarquivar pode ficar em menu secundário se o backend já suporta.

### 3.2 Board Kanban

- Colunas = `pipeline_stages`.
- Cards = `pipeline_cards` com resumo de empresa (`razao_social`, `uf`) e dados comerciais (`display_name`, `estimated_value_cents`, `notes`).
- Cards devem ser agrupados por `stage_id` no frontend a partir da listagem denormalizada.
- Drag-and-drop:
  - mover card dentro da mesma coluna;
  - mover card para outra coluna;
  - chamada backend: `POST /pipelines/{pipeline_id}/cards/{card_id}/move`;
  - optimistic update com rollback em erro.
- Reordenar stages entra nesta fase, usando `POST /pipelines/{pipeline_id}/stages/reorder`.
- Para centenas de cards:
  - renderizar colunas com scroll interno;
  - usar memoização por stage;
  - preparar virtualização por coluna com `@tanstack/react-virtual` quando o card count por coluna passar do limite configurado.

### 3.3 Card detail

Ao abrir um card:

- mostrar empresa, CNPJ básico, stage atual, valor estimado e notas;
- editar nome livre do card, valor estimado e notas;
- listar activities;
- criar activity (`note`, `call`, `email`, `meeting`);
- listar tasks;
- criar task;
- marcar task como concluída.
- mostrar “Dados importados do CSV” com todas as colunas extras salvas em `metadata`.

### 3.4 Import CSV persistente

- Modal para upload de arquivo CSV e opção de colar CSV.
- Selecionar pipeline e stage destino.
- Backend salva um import batch e todas as linhas processadas.
- Mostrar preview com:
  - total de linhas;
  - cards criados;
  - linhas ignoradas por reason (`invalid_cnpj_format`, `cnpj_not_found`, `duplicate_in_pipeline`).

CSV deve aceitar no mínimo:

- coluna `cnpj`, `cnpj_basico`, `documento` ou primeira coluna com CNPJ;
- CNPJ completo formatado (`12.345.678/0001-00`) ou `cnpj_basico` cru com 8 dígitos;
- coluna opcional `nome`, `title`, `apelido`, `card_name` para preencher `display_name`;
- colunas extras preservadas como JSON metadata para inteligência futura.

Endpoint recomendado:

- `POST /pipelines/{pipeline_id}/cards/import`
- `multipart/form-data`
- fields:
  - `stage_id: UUID`
  - `file: UploadFile`
  - `default_display_name?: string`

O backend deve manter compatibilidade de teste/serviço para import via string internamente, mas a API pública deve usar upload real.

### 3.5 Persistência de import e inteligência de CNPJ

Adicionar tabelas:

```sql
CREATE TABLE pipeline_card_import_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stage_id UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
  filename TEXT,
  file_size_bytes BIGINT NOT NULL DEFAULT 0,
  content_sha256 TEXT NOT NULL,
  total_rows INTEGER NOT NULL DEFAULT 0,
  created_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX pipeline_card_import_batches_owner_created
  ON pipeline_card_import_batches (owner_user_id, created_at DESC);
CREATE INDEX pipeline_card_import_batches_pipeline_created
  ON pipeline_card_import_batches (pipeline_id, created_at DESC);
CREATE INDEX pipeline_card_import_batches_sha
  ON pipeline_card_import_batches (content_sha256);
CREATE UNIQUE INDEX pipeline_card_import_batches_latest_file
  ON pipeline_card_import_batches (owner_user_id, pipeline_id, filename, file_size_bytes);

CREATE TABLE pipeline_card_import_rows (
  id BIGSERIAL PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES pipeline_card_import_batches(id) ON DELETE CASCADE,
  line_number INTEGER NOT NULL,
  raw_cnpj TEXT NOT NULL,
  cnpj_basico CHAR(8),
  display_name TEXT,
  card_id UUID REFERENCES pipeline_cards(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('created','skipped')),
  reason TEXT CHECK (reason IN ('invalid_cnpj_format','cnpj_not_found','duplicate_in_pipeline')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX pipeline_card_import_rows_batch_line
  ON pipeline_card_import_rows (batch_id, line_number);
CREATE INDEX pipeline_card_import_rows_cnpj
  ON pipeline_card_import_rows (cnpj_basico) WHERE cnpj_basico IS NOT NULL;
CREATE INDEX pipeline_card_import_rows_card
  ON pipeline_card_import_rows (card_id) WHERE card_id IS NOT NULL;
CREATE INDEX pipeline_card_import_rows_metadata_gin
  ON pipeline_card_import_rows USING GIN (metadata);
```

Essas tabelas garantem:

- rastreabilidade do que cada usuário subiu;
- possibilidade de auditoria e reprocessamento;
- consulta futura por `cnpj_basico` para enriquecimento;
- armazenamento de colunas extras sem travar o schema.

Regra de reimport:

- `owner_user_id + pipeline_id + filename + file_size_bytes` identifica o arquivo operacional do usuário naquele pipeline.
- Ao receber novo import com a mesma chave, o backend remove o batch anterior e suas rows por cascade antes de salvar o batch mais novo.
- Cards já existentes no pipeline não são duplicados; as linhas novas entram como `duplicate_in_pipeline` quando o card já existe.
- `content_sha256` permanece salvo para auditoria e diagnóstico, mas a regra de substituição usa nome + tamanho como solicitado pelo usuário.

### 3.6 Evolução de `pipeline_cards`

Adicionar:

```sql
ALTER TABLE pipeline_cards
  ADD COLUMN display_name TEXT;

CREATE INDEX pipeline_cards_pipeline_stage_position
  ON pipeline_cards (pipeline_id, stage_id, position);
CREATE INDEX pipeline_cards_pipeline_updated
  ON pipeline_cards (pipeline_id, updated_at DESC);
```

`display_name` é um nome livre do usuário para aquele card. Não altera cadastro da empresa e não é compartilhado globalmente.

## 4. Arquitetura frontend

Seguir FSD existente.

```
frontend/src/
├── pages/pipeline/
│   ├── index.ts
│   └── ui/PipelinePage.tsx
│
├── features/pipeline/
│   ├── api.ts
│   ├── hooks.ts
  │   ├── schemas.ts
│   ├── model/
│   │   ├── board.ts
  │   │   ├── drag.ts
  │   │   └── csv.ts
│   ├── ui/
│   │   ├── PipelineToolbar.tsx
│   │   ├── PipelineBoard.tsx
│   │   ├── PipelineStageColumn.tsx
│   │   ├── PipelineCard.tsx
│   │   ├── CardDetailDialog.tsx
│   │   ├── CreatePipelineDialog.tsx
  │   │   ├── CreateCardDialog.tsx
  │   │   └── ImportCsvDialog.tsx
│   └── index.ts
```

`pages/pipeline` apenas compõe a feature. Regras de negócio ficam no backend; o frontend só transforma dados para exibição, organiza estado de UI e chama mutations.

## 5. API consumida

Endpoints principais:

- `GET /pipelines`
- `POST /pipelines`
- `GET /pipelines/{pipeline_id}`
- `GET /pipelines/{pipeline_id}/stages`
- `POST /pipelines/{pipeline_id}/stages`
- `POST /pipelines/{pipeline_id}/stages/reorder`
- `GET /pipelines/{pipeline_id}/cards`
- `POST /pipelines/{pipeline_id}/cards`
- `PATCH /pipelines/{pipeline_id}/cards/{card_id}`
- `POST /pipelines/{pipeline_id}/cards/{card_id}/move`
- `DELETE /pipelines/{pipeline_id}/cards/{card_id}`
- `POST /pipelines/{pipeline_id}/cards/import`
- `GET /pipelines/{pipeline_id}/cards/{card_id}/activities`
- `POST /pipelines/{pipeline_id}/cards/{card_id}/activities`
- `GET /pipelines/{pipeline_id}/cards/{card_id}/tasks`
- `POST /pipelines/{pipeline_id}/cards/{card_id}/tasks`
- `PATCH /pipelines/{pipeline_id}/cards/{card_id}/tasks/{task_id}`

Backend precisa evoluir os schemas para incluir:

- `CardCreate.display_name?: string`
- `CardPatch.display_name?: string`
- `CardRecord.display_name?: string`
- `CardWithCompany.card.display_name`
- `ImportResult.batch_id`
- endpoint para listar últimos imports opcional: `GET /pipelines/{pipeline_id}/cards/imports`
- endpoint para metadata de import associada ao card:
  - `GET /pipelines/{pipeline_id}/cards/{card_id}/import-metadata`
  - retorna colunas extras de rows de import mais recentes associadas ao card.

## 6. Estado e cache

Usar TanStack Query:

- `['pipelines']`
- `['pipeline-detail', pipelineId]`
- `['pipeline-stages', pipelineId]`
- `['pipeline-cards', pipelineId]`
- `['pipeline-card-activities', pipelineId, cardId]`
- `['pipeline-card-tasks', pipelineId, cardId]`

Mutations invalidam o menor conjunto possível:

- mover card: optimistic update em `pipeline-cards` e invalidate de `pipeline-detail`;
- criar card/import: invalidate `pipeline-cards` + `pipeline-detail`;
- editar card: update direto no cache do card/lista;
- activities/tasks: invalidate só a chave do card.

## 7. UX e layout

O pipeline é ferramenta operacional, não landing page. Design deve ser denso, claro e repetível:

- header compacto com seletor de pipeline, botão criar pipeline, importar CSV e criar card;
- board full-width, scroll horizontal quando houver muitas colunas;
- colunas com largura estável e altura calculada pelo viewport;
- cards compactos com razão social, UF, CNPJ, valor estimado e indicador de tasks abertas;
- dialogs para criação/import/detalhe, não páginas separadas;
- empty states por board e por coluna;
- todos os botões com ícone lucide + texto quando comando não for óbvio.

## 8. Acessibilidade

- Drag handle explícito no card.
- Cards focáveis com ação de abrir detalhe via Enter.
- Ações alternativas sem drag:
  - menu “Mover para...” dentro do detalhe do card;
  - campos stage/position na edição quando necessário.
- Labels reais em inputs.
- Feedback com `Alert`/toast para erros de API.

## 9. Performance e banco

- Otimizar para centenas de cards por pipeline já no MVP.
- Virtualizar cards por coluna quando uma coluna passar de ~80 cards.
- Preparar colunas com `contain: layout paint` e scroll interno.
- Evitar recalcular agrupamento sem `useMemo`.
- Manter queries do backend indexadas por `(pipeline_id, stage_id, position)` e imports por `(owner_user_id, created_at DESC)`/`cnpj_basico`.
- Evitar buscar activities/tasks de todos os cards no board; carregar sob demanda no detalhe.

## 10. Testes

Mínimo:

- API client: transforma payloads e chama endpoints corretos.
- Board model: agrupa cards por stage e aplica optimistic move.
- Pipeline page: loading, empty, board renderizado.
- Drag-drop: teste unitário do handler `onDrop`/adapter, não simular browser drag completo no Vitest.
- Dialog import CSV: envia content/stage e mostra resumo.
- Repository/migration tests para batches/rows/import metadata.
- Build/lint obrigatórios.

E2E Playwright opcional após backend/local auth pronto:

- login;
- cria pipeline;
- cria card;
- move card entre stages;
- importa CSV pequeno.

## 11. Perguntas remanescentes

As decisões principais já foram fechadas pelo usuário. Restam apenas detalhes de produto que não bloqueiam a implementação:

1. **Nome livre do card:** se `display_name` não for informado, o card mostra razão social da empresa; se não houver razão social, mostra `cnpj_basico`.

## 12. Critério de pronto

- `/app/pipeline` deixa de ser placeholder e vira experiência operacional.
- Usuário consegue criar pipeline/card, mover card no Kanban, abrir detalhe, registrar activity/task e importar CSV.
- CSV import salva batch/linhas no banco, inclusive linhas ignoradas.
- Card tem nome livre por usuário (`display_name`).
- Drag-and-drop usa biblioteca mantida e gratuita.
- Board suporta centenas de cards com virtualização por coluna quando necessário.
- UI segue Design System/FSD.
- `npm run lint`, `npm run build` e testes relevantes passam.
- Backend `pytest`, import-linter e migrations passam.
