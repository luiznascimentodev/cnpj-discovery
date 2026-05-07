# Design: Advanced Filters + Company Detail

**Date:** 2026-05-07  
**Status:** Approved  
**Scope:** API filter expansion, CNAE catalog endpoint, company detail endpoint, frontend revamp

---

## Context

The current prospecting system supports basic filters (single CNAE, single porte, capital social min only, no CNPJ search, no company detail view). This spec covers the full upgrade needed for production-grade B2B prospecting.

**Core principle:** Zero business logic in the frontend. The frontend is a dumb consumer — all filtering, grouping, validation, and normalization happens in the API.

---

## 1. Database Migration (`005_filters_indexes.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_bairro_trgm
    ON estabelecimentos USING GIN (bairro gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_data_inicio
    ON estabelecimentos (data_inicio);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_matriz_filial
    ON estabelecimentos (matriz_filial);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_natureza
    ON empresas (natureza_juridica);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_simples_opcao
    ON simples (opcao_simples);
```

These indexes are added to `MANAGED_INDEXES` in `etl/indexer.py` so the ETL manages their lifecycle.

---

## 2. API

### 2.1 Updated: `GET /v1/prospecting`

**Filter model (`models/filters.py`):**

| Field | Type | Change | Notes |
|---|---|---|---|
| `cnpj` | `str \| None` | NEW | 14 digits, strips punctuation. When present, all other filters are ignored. |
| `cnaes` | `list[int] \| None` | replaces `cnae_principal` | `ANY($n::int[])` — uses existing index |
| `porte` | `list[int] \| None` | was `int` | Multiple porte selection |
| `bairro` | `str \| None` | NEW | `bairro ILIKE $n` with pg_trgm GIN index |
| `matriz_filial` | `int \| None` | NEW | 1=Matriz, 2=Filial |
| `data_inicio_min` | `date \| None` | NEW | `est.data_inicio >= $n` |
| `data_inicio_max` | `date \| None` | NEW | `est.data_inicio <= $n` |
| `opcao_simples` | `bool \| None` | NEW | `JOIN simples` only when set; filters `opcao_simples = 'S'` |
| `natureza_juridica` | `int \| None` | NEW | `e.natureza_juridica = $n` |
| `capital_social_min` | `float \| None` | unchanged | |
| `capital_social_max` | `float \| None` | unchanged | |
| `busca_razao` | `str \| None` | unchanged | FTS on razao_social + nome_fantasia |
| `excluir_mei` | `bool` | unchanged | |
| `limit` | `int` | teto sobe 500→5000 | ge=1, le=5000 |
| `cursor_cnpj_basico` | `str \| None` | unchanged | keyset pagination |
| `cursor_cnpj_ordem` | `str \| None` | unchanged | keyset pagination |

**Validation rules:**
- `cnpj` normalizado (strip `./- `) deve ter exatamente 14 dígitos; se não, retorna 422
- `porte == [1]` + `excluir_mei == True` → 422 (conflito existente, mantido)
- `data_inicio_min > data_inicio_max` → 422

**Query builder (`services/query_builder.py`):**
- Quando `cnpj` presente: query simplificada direto por PK `(cnpj_basico, cnpj_ordem, cnpj_dv)`, ignora demais filtros, sem pagination, `LIMIT 1`
- `cnaes`: `est.cnae_principal = ANY($n::int[])`
- `porte`: `e.porte = ANY($n::int[])`
- `opcao_simples`: adiciona `LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico` + `s.opcao_simples = 'S'`
- `bairro`: `est.bairro ILIKE $n` (valor com `%` no backend: `f"%{bairro}%"`)

---

### 2.2 New: `GET /v1/empresa/{cnpj}`

**Path:** `/v1/empresa/{cnpj}` — cnpj pode ter ou não pontuação (normalizado no router)

**Response model (`models/empresa.py` — novo `EmpresaDetail`):**

```
EmpresaDetail:
  # Identificação
  cnpj_basico, cnpj_ordem, cnpj_dv, cnpj_completo
  razao_social, nome_fantasia
  situacao_cadastral, data_situacao, motivo_situacao
  porte, natureza_juridica, ente_federativo
  data_inicio, matriz_filial

  # Endereço
  tipo_logradouro, logradouro, numero, complemento
  bairro, cep, uf, municipio, municipio_descricao

  # Capital
  capital_social

  # Contatos
  email
  telefone1 (ddd1 + telefone1)
  telefone2 (ddd2 + telefone2)
  fax (ddd_fax + fax)

  # CNAEs
  cnae_principal, cnae_principal_descricao
  cnae_secundarios: list[CnaeItem]  # parseado de TEXT para lista

  # Sócios
  socios: list[SocioOut]

  # Simples Nacional
  simples: SimplesOut | None
```

**Modelos:**
```
CnaeItem: { codigo: int, descricao: str | None }
SocioOut: { nome_socio, cpf_cnpj_socio, qualificacao, qualificacao_descricao, data_entrada, faixa_etaria }
SimplesOut: { opcao_simples, data_opcao_simples, data_exc_simples, opcao_mei, data_opcao_mei, data_exc_mei }
```

**Query:** JOIN empresas + estabelecimentos + LEFT JOIN socios + LEFT JOIN simples + LEFT JOIN municipios + LEFT JOIN cnaes. Todos os joins usam `cnpj_basico` (indexado). Performance: O(1).

**Cache:** Redis com key `cnpj:detail:{cnpj14}`, TTL 1h.

**Error:** 404 se CNPJ não encontrado; 422 se CNPJ inválido (≠ 14 dígitos após normalização).

---

### 2.3 New: `GET /v1/cnaes`

**Response:**
```json
{
  "segments": [
    {
      "label": "Tecnologia e TI",
      "cnaes": [{ "codigo": 6201500, "descricao": "Desenvolvimento de programas..." }]
    }
  ]
}
```

**Segmentos definidos no backend** (`services/cnae_segments.py`):

| Segmento | Divisões CNAE 2.0 |
|---|---|
| Tecnologia e TI | 62, 63 |
| Alimentação e Bebidas | 10, 11, 56 |
| Comércio Varejista | 47 |
| Comércio Atacadista | 46 |
| Construção Civil | 41, 42, 43 |
| Saúde e Bem-estar | 86, 87, 88, 75, 96 |
| Educação | 85 |
| Serviços Financeiros | 64, 65, 66 |
| Transporte e Logística | 49, 50, 51, 52, 53 |
| Indústria | 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 |
| Agropecuária | 01, 02, 03 |
| Serviços Profissionais | 69, 70, 71, 72, 73, 74 |
| Imóveis | 68 |
| Outros | todos os demais |

**Performance:** Query simples `SELECT codigo, descricao FROM cnaes ORDER BY codigo`. Redis cache TTL 24h com key `cnpj:cnaes:all`. Payload ~150KB — aceitável para uma chamada única no boot do frontend.

---

## 3. Frontend

### 3.1 Estrutura de arquivos

```
src/
├── api/
│   └── client.ts                  — tipos e funções atualizados
├── components/
│   ├── FilterPanel.tsx             — reescrito
│   ├── ResultsTable.tsx            — linhas clicáveis
│   ├── CompanyDetailModal.tsx      — novo
│   └── CnaeSelector.tsx            — novo
├── hooks/
│   └── useCnaes.ts                 — novo, carrega /cnaes uma vez
└── pages/
    └── Prospecting.tsx             — gerencia selectedCnpj para o modal
```

### 3.2 FilterPanel

Campos em ordem vertical:

1. **CNPJ** — input texto. Quando preenchido, os demais filtros ficam com `opacity-50 pointer-events-none` e aparece badge "Busca por CNPJ — demais filtros ignorados"
2. **Razão Social / Fantasia** — igual ao atual
3. **UF** — select igual ao atual
4. **Município** — input numérico (código IBGE), igual ao atual
5. **Bairro** — input texto, novo
6. **CNAE** — `CnaeSelector` (ver abaixo)
7. **Porte** — grupo de checkboxes: MEI / ME / EPP / Demais
8. **Excluir MEI** — checkbox, disabled quando MEI está checado
9. **Capital Social** — dois inputs numéricos lado a lado: Mínimo / Máximo
10. **Matriz / Filial** — select: Todos / Somente Matriz / Somente Filial
11. **Abertura** — dois date inputs: De / Até
12. **Simples Nacional** — checkbox "Somente Simples Nacional"
13. **Natureza Jurídica** — select com opções fixas mais comuns
14. **Limite de resultados** — select: 50 / 100 / 500 / 1000 / 5000

### 3.3 CnaeSelector

- Carregado via `useCnaes()` que chama `GET /v1/cnaes` com `staleTime: Infinity`
- Campo de busca textual no topo — filtra CNAEs por código ou descrição across todos os segmentos
- Acordeão por segmento — cada segmento expansível com contagem de selecionados
- Checkbox por CNAE
- Selecionados exibidos como tags removíveis acima do acordeão
- "Selecionar segmento inteiro" checkbox no header de cada segmento

### 3.4 ResultsTable

- `onClick` em cada linha → chama `onSelectEmpresa(cnpj_completo)`
- `cursor-pointer hover:bg-blue-50` nas linhas (já existe o hover)
- Coluna CNAE mostra `cnae_descricao` em vez do código

### 3.5 CompanyDetailModal

- Drawer lateral (slide-in da direita, largura `max-w-2xl`)
- Fecha com ESC ou clique no overlay
- Loading skeleton de 3 seções enquanto busca
- Seções:
  - **Identificação:** CNPJ formatado, razão, fantasia, situação, porte, natureza jurídica, data abertura, matriz/filial
  - **Endereço:** logradouro completo, bairro, CEP, município, UF
  - **Contatos:** email (mailto link), telefone1, telefone2, fax
  - **CNAEs:** principal destacado + lista de secundários com descrição
  - **Sócios:** tabela com nome, CPF/CNPJ, qualificação, data entrada, faixa etária
  - **Simples Nacional:** badge verde "Simples" / "MEI" ou cinza "Fora do Simples", datas

### 3.6 api/client.ts — novos tipos e funções

```typescript
interface CnaeItem { codigo: number; descricao: string }
interface CnaeSegment { label: string; cnaes: CnaeItem[] }
interface CnaesResponse { segments: CnaeSegment[] }

interface SocioOut { nome_socio: string; cpf_cnpj_socio: string; qualificacao: number | null; qualificacao_descricao: string | null; data_entrada: string | null; faixa_etaria: number | null }
interface SimplesOut { opcao_simples: string | null; data_opcao_simples: string | null; data_exc_simples: string | null; opcao_mei: string | null; data_opcao_mei: string | null; data_exc_mei: string | null }
interface EmpresaDetail extends EmpresaOut {
  // + todos os campos de endereço, contatos, cnae_secundarios, socios, simples
}

getCnaes(): Promise<CnaesResponse>
getEmpresa(cnpj: string): Promise<EmpresaDetail>
```

Filters interface ganha: `cnpj?`, `cnaes?: number[]`, `bairro?`, `matriz_filial?`, `data_inicio_min?`, `data_inicio_max?`, `opcao_simples?`, `natureza_juridica?`. `porte` vira `number[]`.

---

## 4. Testes (100% de cobertura)

### API
- `test_query_builder.py`: cada novo filtro isolado + combinações; CNPJ mode ignora outros filtros; array ANY para cnaes e porte; opcao_simples adiciona JOIN
- `test_routers.py`: `/empresa/{cnpj}` com pontuação, sem pontuação, não encontrado, inválido; `/cnaes` cache hit e miss; prospecting com novos filtros
- `test_cnae_segments.py`: todos os CNAEs da tabela classificados em algum segmento; segmento "Outros" captura o restante

### ETL
- `test_indexer.py`: novos índices presentes em `MANAGED_INDEXES`

---

## 5. Ordem de implementação

1. Migration `005_filters_indexes.sql`
2. Atualizar `MANAGED_INDEXES` no ETL com novos índices
3. Novos modelos Pydantic (`EmpresaDetail`, `SocioOut`, `SimplesOut`, `CnaeItem`)
4. `services/cnae_segments.py`
5. Atualizar `models/filters.py` (novos campos, teto limit=5000)
6. Atualizar `services/query_builder.py`
7. Router `GET /v1/cnaes`
8. Router `GET /v1/empresa/{cnpj}`
9. Atualizar `GET /v1/prospecting`
10. Testes API completos
11. `api/client.ts` — tipos e funções
12. `useCnaes.ts` hook
13. `CnaeSelector.tsx`
14. `FilterPanel.tsx` reescrito
15. `CompanyDetailModal.tsx`
16. `ResultsTable.tsx` — linhas clicáveis
17. `Prospecting.tsx` — estado do modal
