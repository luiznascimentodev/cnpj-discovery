# Advanced Filters + Company Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand prospecting filters (CNPJ search, multi-CNAE, multi-porte, bairro, matriz/filial, data de abertura, Simples Nacional, natureza jurídica), add `/cnaes` catalog endpoint, add `/empresa/{cnpj}` detail endpoint, and revamp the frontend.

**Architecture:** All business logic in the API; frontend is a dumb consumer. New endpoints follow the existing asyncpg pool + Redis cache pattern. DB gains 5 new indexes via migration 005.

**Tech Stack:** FastAPI, asyncpg, psycopg2, Redis, pydantic v2, React 19, TanStack Query v5, Tailwind v4, TypeScript.

---

## File Map

**Create:**
- `db/migrations/005_filters_indexes.sql`
- `api/models/detail.py`
- `api/services/cnae_segments.py`
- `api/routers/cnaes.py`
- `api/routers/empresa.py`
- `api/tests/test_cnae_segments.py`
- `frontend/src/hooks/useCnaes.ts`
- `frontend/src/components/CnaeSelector.tsx`
- `frontend/src/components/CompanyDetailModal.tsx`

**Modify:**
- `etl/indexer.py` — add 5 new indexes to MANAGED_INDEXES
- `etl/tests/test_indexer.py` — assert new indexes present
- `api/models/filters.py` — new fields, validators, limit 5000
- `api/services/query_builder.py` — new filter logic
- `api/routers/prospecting.py` — use updated filters
- `api/main.py` — register new routers
- `api/tests/conftest.py` — patch new routers
- `api/tests/test_query_builder.py` — update broken tests, add new
- `api/tests/test_routers.py` — add new endpoint tests
- `frontend/src/api/client.ts` — new types + functions
- `frontend/src/components/FilterPanel.tsx` — rewrite
- `frontend/src/components/ResultsTable.tsx` — clickable rows
- `frontend/src/pages/Prospecting.tsx` — modal state

---

## Task 1: DB Migration 005

**Files:**
- Create: `db/migrations/005_filters_indexes.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- db/migrations/005_filters_indexes.sql
-- Indexes for advanced filter support added in v2

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

- [ ] **Step 2: Apply to running postgres**

```bash
docker compose exec -T postgres psql -U cnpj_user -d cnpj \
  < db/migrations/005_filters_indexes.sql
```

Expected: no errors, `CREATE INDEX` printed for each.

- [ ] **Step 3: Verify indexes exist**

```bash
docker compose exec postgres psql -U cnpj_user -d cnpj \
  -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'idx_%' ORDER BY indexname;"
```

Expected: `idx_estab_bairro_trgm`, `idx_estab_data_inicio`, `idx_estab_matriz_filial`, `idx_empresas_natureza`, `idx_simples_opcao` in the list.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/005_filters_indexes.sql
git commit -m "feat(db): add indexes for advanced filters (pg_trgm, data_inicio, bairro, natureza, simples)"
```

---

## Task 2: ETL MANAGED_INDEXES

**Files:**
- Modify: `etl/indexer.py`
- Modify: `etl/tests/test_indexer.py`

- [ ] **Step 1: Write failing tests**

In `etl/tests/test_indexer.py`, add to `TestManagedIndexes`:

```python
def test_new_filter_indexes_present(self):
    names = {name for name, _ in MANAGED_INDEXES}
    assert "idx_estab_bairro_trgm" in names
    assert "idx_estab_data_inicio" in names
    assert "idx_estab_matriz_filial" in names
    assert "idx_empresas_natureza" in names
    assert "idx_simples_opcao" in names

def test_trgm_index_uses_gin(self):
    idx = {name: sql for name, sql in MANAGED_INDEXES}
    assert "gin_trgm_ops" in idx["idx_estab_bairro_trgm"].upper() or "GIN" in idx["idx_estab_bairro_trgm"].upper()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd etl && python -m pytest tests/test_indexer.py::TestManagedIndexes::test_new_filter_indexes_present -v
```

Expected: FAILED — `AssertionError`.

- [ ] **Step 3: Add indexes to MANAGED_INDEXES in `etl/indexer.py`**

After the last existing entry (`idx_estab_ativas_uf`), append:

```python
    (
        "idx_estab_bairro_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_bairro_trgm "
        "ON estabelecimentos USING GIN (bairro gin_trgm_ops)",
    ),
    (
        "idx_estab_data_inicio",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_data_inicio "
        "ON estabelecimentos (data_inicio)",
    ),
    (
        "idx_estab_matriz_filial",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_matriz_filial "
        "ON estabelecimentos (matriz_filial)",
    ),
    (
        "idx_empresas_natureza",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_natureza "
        "ON empresas (natureza_juridica)",
    ),
    (
        "idx_simples_opcao",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_simples_opcao "
        "ON simples (opcao_simples)",
    ),
```

- [ ] **Step 4: Run tests**

```bash
cd etl && python -m pytest tests/test_indexer.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add etl/indexer.py etl/tests/test_indexer.py
git commit -m "feat(etl): add 5 new filter indexes to MANAGED_INDEXES"
```

---

## Task 3: New Pydantic models (models/detail.py)

**Files:**
- Create: `api/models/detail.py`

- [ ] **Step 1: Create `api/models/detail.py`**

```python
from datetime import date
from typing import Optional
from pydantic import BaseModel


class CnaeItem(BaseModel):
    codigo: int
    descricao: Optional[str] = None


class SocioOut(BaseModel):
    nome_socio: Optional[str] = None
    cpf_cnpj_socio: Optional[str] = None
    qualificacao: Optional[int] = None
    qualificacao_descricao: Optional[str] = None
    data_entrada: Optional[date] = None
    faixa_etaria: Optional[int] = None


class SimplesOut(BaseModel):
    opcao_simples: Optional[str] = None
    data_opcao_simples: Optional[date] = None
    data_exc_simples: Optional[date] = None
    opcao_mei: Optional[str] = None
    data_opcao_mei: Optional[date] = None
    data_exc_mei: Optional[date] = None


class EmpresaDetail(BaseModel):
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    cnpj_completo: str
    razao_social: str
    nome_fantasia: Optional[str] = None
    situacao_cadastral: Optional[int] = None
    data_situacao: Optional[date] = None
    motivo_situacao: Optional[int] = None
    porte: Optional[int] = None
    natureza_juridica: Optional[int] = None
    ente_federativo: Optional[str] = None
    data_inicio: Optional[date] = None
    matriz_filial: Optional[int] = None
    tipo_logradouro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cep: Optional[str] = None
    uf: Optional[str] = None
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None
    capital_social: Optional[float] = None
    email: Optional[str] = None
    telefone1: Optional[str] = None
    telefone2: Optional[str] = None
    fax: Optional[str] = None
    cnae_principal: Optional[int] = None
    cnae_principal_descricao: Optional[str] = None
    cnae_secundarios: list[CnaeItem] = []
    socios: list[SocioOut] = []
    simples: Optional[SimplesOut] = None
```

- [ ] **Step 2: Write tests — add `TestDetailModels` to `api/tests/test_query_builder.py`**

```python
from models.detail import CnaeItem, SocioOut, SimplesOut, EmpresaDetail
from datetime import date


class TestDetailModels:
    def _empresa_required(self):
        return dict(
            cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
            cnpj_completo="12345678000190", razao_social="TESTE LTDA",
        )

    def test_empresa_detail_required_fields(self):
        e = EmpresaDetail(**self._empresa_required())
        assert e.cnpj_completo == "12345678000190"
        assert e.cnae_secundarios == []
        assert e.socios == []
        assert e.simples is None

    def test_empresa_detail_with_nested(self):
        e = EmpresaDetail(
            **self._empresa_required(),
            cnae_secundarios=[CnaeItem(codigo=6201500, descricao="Dev")],
            socios=[SocioOut(nome_socio="JOAO", qualificacao=49)],
            simples=SimplesOut(opcao_simples="S"),
        )
        assert e.cnae_secundarios[0].codigo == 6201500
        assert e.socios[0].nome_socio == "JOAO"
        assert e.simples.opcao_simples == "S"

    def test_cnae_item_descricao_optional(self):
        c = CnaeItem(codigo=6201500)
        assert c.descricao is None

    def test_socio_all_optional(self):
        s = SocioOut()
        assert s.nome_socio is None
        assert s.data_entrada is None

    def test_simples_all_optional(self):
        s = SimplesOut()
        assert s.opcao_simples is None
        assert s.opcao_mei is None
```

- [ ] **Step 3: Run tests**

```bash
cd api && python -m pytest tests/test_query_builder.py::TestDetailModels -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add api/models/detail.py api/tests/test_query_builder.py
git commit -m "feat(api): add EmpresaDetail, SocioOut, SimplesOut, CnaeItem models"
```

---

## Task 4: Update models/filters.py

**Files:**
- Modify: `api/models/filters.py`
- Modify: `api/tests/test_query_builder.py`

- [ ] **Step 1: Update tests that will break due to field renames**

In `api/tests/test_query_builder.py`, make these changes:

In `TestProspectingFilters.test_defaults`:
- Change `assert f.cnae_principal is None` → `assert f.cnaes is None`
- Change `assert f.porte is None` → `assert f.porte is None` (stays None, but porte is now list)

In `TestProspectingFilters.test_limit_above_max_raises`:
- Change `ProspectingFilters(limit=501)` → `ProspectingFilters(limit=5001)`

In `TestProspectingFilters.test_porte_mei_with_excluir_mei_raises`:
- Change `ProspectingFilters(porte=1, excluir_mei=True)` → `ProspectingFilters(porte=[1], excluir_mei=True)`

In `TestProspectingFilters.test_porte_non_mei_with_excluir_mei_ok`:
- Change `ProspectingFilters(porte=2, excluir_mei=True)` → `ProspectingFilters(porte=[2], excluir_mei=True)`
- Change `assert f.porte == 2` → `assert f.porte == [2]`

Rename class `TestBuildProspectingQueryCnaePrincipal` → `TestBuildProspectingQueryCnaes` and update its body:
```python
class TestBuildProspectingQueryCnaes:
    def test_single_cnae_uses_any(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=[6201500])
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = ANY($1::int[])" in sql
        assert params[0] == [6201500]

    def test_multiple_cnaes(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=[6201500, 6209100])
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = ANY($1::int[])" in sql
        assert params[0] == [6201500, 6209100]

    def test_cnaes_none_no_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=None)
        sql, params = build_prospecting_query(f)
        assert "cnae_principal" not in sql
        assert params == []
```

Update `TestBuildProspectingQueryPorte`:
```python
class TestBuildProspectingQueryPorte:
    def test_adds_porte_any_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, porte=[3])
        sql, params = build_prospecting_query(f)
        assert "e.porte = ANY($1::int[])" in sql
        assert params[0] == [3]

    def test_multiple_portes(self):
        f = ProspectingFilters(situacao_cadastral=None, porte=[2, 3])
        sql, params = build_prospecting_query(f)
        assert "e.porte = ANY($1::int[])" in sql
        assert params[0] == [2, 3]
```

Update `TestBuildProspectingQueryMultipleFilters.test_all_filters_combined_param_count`:
```python
def test_all_filters_combined_param_count(self):
    f = ProspectingFilters(
        situacao_cadastral=2,
        uf="MG",
        municipio=3106200,
        cnaes=[4711302],
        porte=[3],
        excluir_mei=True,
        capital_social_min=5000.0,
        capital_social_max=1000000.0,
        busca_razao="mercearia",
        cursor_cnpj_basico="11111111",
        cursor_cnpj_ordem="0001",
        limit=100,
    )
    sql, params = build_prospecting_query(f)
    assert len(params) == 10
    assert params[0] == 2
    assert params[1] == "MG"
    assert params[2] == 3106200
    assert params[3] == [4711302]
    assert params[4] == [3]
    assert params[5] == 5000.0
    assert params[6] == 1000000.0
    assert params[7] == "mercearia"
    assert params[8] == "11111111"
    assert params[9] == "0001"
```

Then add new filter tests at the end of `test_query_builder.py`:

```python
class TestProspectingFiltersCnpj:
    def test_cnpj_strips_punctuation(self):
        f = ProspectingFilters(cnpj="12.345.678/0001-90")
        assert f.cnpj == "12345678000190"

    def test_cnpj_without_punctuation_accepted(self):
        f = ProspectingFilters(cnpj="12345678000190")
        assert f.cnpj == "12345678000190"

    def test_cnpj_wrong_length_raises(self):
        with pytest.raises(ValidationError, match="14 dígitos"):
            ProspectingFilters(cnpj="123456")

    def test_cnpj_none_accepted(self):
        f = ProspectingFilters()
        assert f.cnpj is None


class TestProspectingFiltersDateRange:
    def test_valid_date_range(self):
        f = ProspectingFilters(
            data_inicio_min=date(2020, 1, 1),
            data_inicio_max=date(2023, 12, 31),
        )
        assert f.data_inicio_min == date(2020, 1, 1)

    def test_inverted_date_range_raises(self):
        with pytest.raises(ValidationError, match="data_inicio_min"):
            ProspectingFilters(
                data_inicio_min=date(2024, 1, 1),
                data_inicio_max=date(2020, 1, 1),
            )

    def test_only_min_accepted(self):
        f = ProspectingFilters(data_inicio_min=date(2020, 1, 1))
        assert f.data_inicio_max is None


class TestBuildProspectingQueryCnpjMode:
    def test_cnpj_mode_splits_into_pk(self):
        f = ProspectingFilters(cnpj="12345678000190", situacao_cadastral=2, uf="SP")
        sql, params = build_prospecting_query(f)
        assert params == ["12345678", "0001", "90"]
        assert "LIMIT 1" in sql

    def test_cnpj_mode_ignores_other_filters(self):
        f = ProspectingFilters(cnpj="12345678000190", situacao_cadastral=2, uf="SP")
        sql, params = build_prospecting_query(f)
        assert "est.uf" not in sql
        assert "situacao_cadastral" not in sql


class TestBuildProspectingQueryNewFilters:
    def test_bairro_uses_ilike(self):
        f = ProspectingFilters(situacao_cadastral=None, bairro="centro")
        sql, params = build_prospecting_query(f)
        assert "est.bairro ILIKE $1" in sql
        assert params[0] == "%centro%"

    def test_matriz_filial_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, matriz_filial=1)
        sql, params = build_prospecting_query(f)
        assert "est.matriz_filial = $1" in sql
        assert params[0] == 1

    def test_data_inicio_min_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, data_inicio_min=date(2020, 1, 1))
        sql, params = build_prospecting_query(f)
        assert "est.data_inicio >= $1" in sql
        assert params[0] == date(2020, 1, 1)

    def test_data_inicio_max_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, data_inicio_max=date(2023, 12, 31))
        sql, params = build_prospecting_query(f)
        assert "est.data_inicio <= $1" in sql
        assert params[0] == date(2023, 12, 31)

    def test_natureza_juridica_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, natureza_juridica=2062)
        sql, params = build_prospecting_query(f)
        assert "e.natureza_juridica = $1" in sql
        assert params[0] == 2062

    def test_opcao_simples_true_adds_join_and_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=True)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" in sql
        assert "s.opcao_simples = $1" in sql
        assert params[0] == "S"

    def test_opcao_simples_false_filters_non_simples(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=False)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" in sql
        assert params[0] == "N"

    def test_opcao_simples_none_no_join(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=None)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" not in sql

    def test_limit_5000_accepted(self):
        f = ProspectingFilters(limit=5000)
        assert f.limit == 5000

    def test_limit_5001_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=5001)
```

- [ ] **Step 2: Run failing tests to confirm they fail**

```bash
cd api && python -m pytest tests/test_query_builder.py -v 2>&1 | tail -20
```

Expected: multiple failures on renamed fields and new tests.

- [ ] **Step 3: Rewrite `api/models/filters.py`**

```python
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator

_CNPJ_RE = re.compile(r"[.\-/\s]")


def normalize_cnpj(raw: str) -> str:
    return _CNPJ_RE.sub("", raw)


class ProspectingFilters(BaseModel):
    cnpj: Optional[str] = Field(None, description="CNPJ com ou sem pontuação — ignora demais filtros")
    uf: Optional[str] = Field(None, max_length=2)
    municipio: Optional[int] = None
    bairro: Optional[str] = Field(None, min_length=2, max_length=100)
    cnaes: Optional[list[int]] = Field(None, description="Códigos CNAE (ANY match)")
    situacao_cadastral: Optional[int] = Field(2)
    porte: Optional[list[int]] = Field(None, description="1=MEI,2=ME,3=EPP,5=Demais (múltiplos)")
    excluir_mei: bool = Field(False)
    capital_social_min: Optional[float] = Field(None, ge=0)
    capital_social_max: Optional[float] = Field(None, ge=0)
    busca_razao: Optional[str] = Field(None, min_length=2, max_length=200)
    matriz_filial: Optional[int] = Field(None, description="1=Matriz, 2=Filial")
    data_inicio_min: Optional[date] = None
    data_inicio_max: Optional[date] = None
    opcao_simples: Optional[bool] = None
    natureza_juridica: Optional[int] = None
    cursor_cnpj_basico: Optional[str] = None
    cursor_cnpj_ordem: Optional[str] = None
    limit: int = Field(50, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_filters(self) -> "ProspectingFilters":
        if self.cnpj is not None:
            normalized = normalize_cnpj(self.cnpj)
            if len(normalized) != 14 or not normalized.isdigit():
                raise ValueError("CNPJ deve ter 14 dígitos numéricos")
            self.cnpj = normalized

        if self.porte and 1 in self.porte and self.excluir_mei:
            raise ValueError("Conflito: porte inclui MEI (1) e excluir_mei=True são mutuamente exclusivos")

        if (
            self.data_inicio_min is not None
            and self.data_inicio_max is not None
            and self.data_inicio_min > self.data_inicio_max
        ):
            raise ValueError("data_inicio_min não pode ser maior que data_inicio_max")

        return self
```

- [ ] **Step 4: Run tests**

```bash
cd api && python -m pytest tests/test_query_builder.py::TestProspectingFilters tests/test_query_builder.py::TestProspectingFiltersCnpj tests/test_query_builder.py::TestProspectingFiltersDateRange -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/models/filters.py api/tests/test_query_builder.py
git commit -m "feat(api): expand ProspectingFilters with CNPJ, multi-CNAE, multi-porte, bairro, and more"
```

---

## Task 5: cnae_segments.py

**Files:**
- Create: `api/services/cnae_segments.py`
- Create: `api/tests/test_cnae_segments.py`

- [ ] **Step 1: Create `api/tests/test_cnae_segments.py`**

```python
import pytest
from services.cnae_segments import classify_cnae, group_cnaes


class TestClassifyCnae:
    def test_tecnologia(self):
        assert classify_cnae(6201500) == "Tecnologia e TI"

    def test_tecnologia_63(self):
        assert classify_cnae(6311900) == "Tecnologia e TI"

    def test_alimentacao_56(self):
        assert classify_cnae(5611201) == "Alimentação e Bebidas"

    def test_alimentacao_10(self):
        assert classify_cnae(1091100) == "Alimentação e Bebidas"

    def test_comercio_varejista(self):
        assert classify_cnae(4711302) == "Comércio Varejista"

    def test_comercio_atacadista(self):
        assert classify_cnae(4611700) == "Comércio Atacadista"

    def test_construcao(self):
        assert classify_cnae(4120400) == "Construção Civil"

    def test_saude(self):
        assert classify_cnae(8630502) == "Saúde e Bem-estar"

    def test_educacao(self):
        assert classify_cnae(8511200) == "Educação"

    def test_financeiro(self):
        assert classify_cnae(6422100) == "Serviços Financeiros"

    def test_transporte(self):
        assert classify_cnae(4921301) == "Transporte e Logística"

    def test_industria(self):
        assert classify_cnae(2511000) == "Indústria"

    def test_agropecuaria(self):
        assert classify_cnae(115600) == "Agropecuária"

    def test_servicos_profissionais(self):
        assert classify_cnae(6911701) == "Serviços Profissionais"

    def test_imoveis(self):
        assert classify_cnae(6810201) == "Imóveis"

    def test_unknown_goes_to_outros(self):
        assert classify_cnae(9999999) == "Outros"

    def test_zero_goes_to_outros(self):
        assert classify_cnae(100) == "Outros"


class TestGroupCnaes:
    def _cnaes(self):
        return [
            {"codigo": 6201500, "descricao": "Dev de software"},
            {"codigo": 5611201, "descricao": "Restaurante"},
            {"codigo": 9999999, "descricao": "Desconhecido"},
        ]

    def test_returns_list(self):
        result = group_cnaes(self._cnaes())
        assert isinstance(result, list)

    def test_each_segment_has_label_and_cnaes(self):
        result = group_cnaes(self._cnaes())
        for seg in result:
            assert "label" in seg
            assert "cnaes" in seg
            assert isinstance(seg["cnaes"], list)

    def test_tecnologia_segment_present(self):
        result = group_cnaes(self._cnaes())
        labels = [s["label"] for s in result]
        assert "Tecnologia e TI" in labels

    def test_outros_segment_last(self):
        result = group_cnaes(self._cnaes())
        assert result[-1]["label"] == "Outros"

    def test_outros_contains_unknown_cnae(self):
        result = group_cnaes(self._cnaes())
        outros = next(s for s in result if s["label"] == "Outros")
        codes = [c["codigo"] for c in outros["cnaes"]]
        assert 9999999 in codes

    def test_empty_input(self):
        assert group_cnaes([]) == []

    def test_segments_without_matching_cnaes_omitted(self):
        result = group_cnaes([{"codigo": 6201500, "descricao": "Dev"}])
        labels = [s["label"] for s in result]
        assert "Alimentação e Bebidas" not in labels
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd api && python -m pytest tests/test_cnae_segments.py -v 2>&1 | tail -5
```

Expected: ImportError — `services.cnae_segments` not found.

- [ ] **Step 3: Create `api/services/cnae_segments.py`**

```python
_SEGMENT_DIVISIONS: list[tuple[str, set[int]]] = [
    ("Tecnologia e TI", {62, 63}),
    ("Alimentação e Bebidas", {10, 11, 56}),
    ("Comércio Varejista", {47}),
    ("Comércio Atacadista", {46}),
    ("Construção Civil", {41, 42, 43}),
    ("Saúde e Bem-estar", {75, 86, 87, 88, 96}),
    ("Educação", {85}),
    ("Serviços Financeiros", {64, 65, 66}),
    ("Transporte e Logística", {49, 50, 51, 52, 53}),
    ("Indústria", {13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33}),
    ("Agropecuária", {1, 2, 3}),
    ("Serviços Profissionais", {69, 70, 71, 72, 73, 74}),
    ("Imóveis", {68}),
]

_SEGMENT_ORDER = [label for label, _ in _SEGMENT_DIVISIONS] + ["Outros"]


def _division(code: int) -> int:
    return code // 100000


def classify_cnae(code: int) -> str:
    div = _division(code)
    for label, divisions in _SEGMENT_DIVISIONS:
        if div in divisions:
            return label
    return "Outros"


def group_cnaes(cnaes: list[dict]) -> list[dict]:
    if not cnaes:
        return []
    groups: dict[str, list] = {}
    for cnae in cnaes:
        label = classify_cnae(cnae["codigo"])
        groups.setdefault(label, []).append(cnae)
    return [
        {"label": label, "cnaes": groups[label]}
        for label in _SEGMENT_ORDER
        if label in groups
    ]
```

- [ ] **Step 4: Run tests**

```bash
cd api && python -m pytest tests/test_cnae_segments.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/services/cnae_segments.py api/tests/test_cnae_segments.py
git commit -m "feat(api): add CNAE segment grouping service"
```

---

## Task 6: Update query_builder.py

**Files:**
- Modify: `api/services/query_builder.py`

- [ ] **Step 1: Rewrite `api/services/query_builder.py`**

```python
from models.filters import ProspectingFilters

_BASE_SQL = """
    SELECT
        e.cnpj_basico,
        est.cnpj_ordem,
        est.cnpj_dv,
        e.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
        e.razao_social,
        est.nome_fantasia,
        est.situacao_cadastral,
        est.cnae_principal,
        c.descricao AS cnae_descricao,
        est.uf,
        est.municipio,
        m.descricao AS municipio_descricao,
        est.email,
        NULLIF(TRIM(COALESCE(est.ddd1, '') || COALESCE(est.telefone1, '')), '') AS telefone1,
        e.porte,
        e.capital_social,
        est.data_inicio
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    LEFT JOIN municipios m ON m.codigo = est.municipio
"""

_SIMPLES_JOIN = "LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico"


def build_prospecting_query(f: ProspectingFilters) -> tuple[str, list]:
    """
    Builds parameterized SQL ($1, $2, …) for asyncpg.
    When f.cnpj is set, returns a PK lookup ignoring all other filters.
    """
    if f.cnpj:
        sql = (
            f"{_BASE_SQL}"
            f" WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3"
            f" LIMIT 1"
        )
        return sql, [f.cnpj[:8], f.cnpj[8:12], f.cnpj[12:]]

    conditions: list[str] = []
    params: list = []
    p = 1
    needs_simples = False

    if f.situacao_cadastral is not None:
        conditions.append(f"est.situacao_cadastral = ${p}")
        params.append(f.situacao_cadastral)
        p += 1

    if f.uf:
        conditions.append(f"est.uf = ${p}")
        params.append(f.uf.upper())
        p += 1

    if f.municipio is not None:
        conditions.append(f"est.municipio = ${p}")
        params.append(f.municipio)
        p += 1

    if f.bairro:
        conditions.append(f"est.bairro ILIKE ${p}")
        params.append(f"%{f.bairro}%")
        p += 1

    if f.cnaes:
        conditions.append(f"est.cnae_principal = ANY(${p}::int[])")
        params.append(f.cnaes)
        p += 1

    if f.porte:
        conditions.append(f"e.porte = ANY(${p}::int[])")
        params.append(f.porte)
        p += 1

    if f.excluir_mei:
        conditions.append("(e.porte IS NULL OR e.porte != 1)")

    if f.capital_social_min is not None:
        conditions.append(f"e.capital_social >= ${p}")
        params.append(f.capital_social_min)
        p += 1

    if f.capital_social_max is not None:
        conditions.append(f"e.capital_social <= ${p}")
        params.append(f.capital_social_max)
        p += 1

    if f.matriz_filial is not None:
        conditions.append(f"est.matriz_filial = ${p}")
        params.append(f.matriz_filial)
        p += 1

    if f.data_inicio_min is not None:
        conditions.append(f"est.data_inicio >= ${p}")
        params.append(f.data_inicio_min)
        p += 1

    if f.data_inicio_max is not None:
        conditions.append(f"est.data_inicio <= ${p}")
        params.append(f.data_inicio_max)
        p += 1

    if f.natureza_juridica is not None:
        conditions.append(f"e.natureza_juridica = ${p}")
        params.append(f.natureza_juridica)
        p += 1

    if f.opcao_simples is not None:
        needs_simples = True
        conditions.append(f"s.opcao_simples = ${p}")
        params.append("S" if f.opcao_simples else "N")
        p += 1

    if f.busca_razao:
        conditions.append(
            f"(to_tsvector('portuguese', e.razao_social) @@ plainto_tsquery('portuguese', ${p})"
            f" OR to_tsvector('portuguese', COALESCE(est.nome_fantasia, '')) @@ plainto_tsquery('portuguese', ${p}))"
        )
        params.append(f.busca_razao)
        p += 1

    if f.cursor_cnpj_basico and f.cursor_cnpj_ordem:
        conditions.append(f"(est.cnpj_basico, est.cnpj_ordem) > (${p}, ${p + 1})")
        params.extend([f.cursor_cnpj_basico, f.cursor_cnpj_ordem])
        p += 2

    simples_join = f"\n    {_SIMPLES_JOIN}" if needs_simples else ""
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"{_BASE_SQL}{simples_join} {where} ORDER BY est.cnpj_basico, est.cnpj_ordem LIMIT {f.limit}"
    return sql, params
```

- [ ] **Step 2: Run all query builder tests**

```bash
cd api && python -m pytest tests/test_query_builder.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add api/services/query_builder.py
git commit -m "feat(api): update query builder for multi-CNAE, multi-porte, bairro, CNPJ mode, and new filters"
```

---

## Task 7: GET /v1/cnaes router

**Files:**
- Create: `api/routers/cnaes.py`
- Modify: `api/main.py`
- Modify: `api/tests/conftest.py`
- Modify: `api/tests/test_routers.py`

- [ ] **Step 1: Add tests for cnaes router in `api/tests/test_routers.py`**

```python
class TestCnaesRouter:
    async def test_cache_hit_returns_data(self, client):
        cached = {"segments": [{"label": "Tecnologia e TI", "cnaes": [{"codigo": 6201500, "descricao": "Dev"}]}]}
        with patch("routers.cnaes.cache_get", AsyncMock(return_value=cached)):
            response = await client.get("/v1/cnaes")
        assert response.status_code == 200
        assert response.json() == cached

    async def test_cache_miss_fetches_from_db_and_returns_segments(self, client, mock_pool):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"codigo": 6201500, "descricao": "Desenvolvimento de programas"},
            {"codigo": 5611201, "descricao": "Restaurantes"},
        ])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.cnaes.cache_get", AsyncMock(return_value=None)):
            with patch("routers.cnaes.cache_set", AsyncMock()) as mock_set:
                with patch("routers.cnaes.get_pool", AsyncMock(return_value=mock_pool)):
                    response = await client.get("/v1/cnaes")

        assert response.status_code == 200
        data = response.json()
        assert "segments" in data
        labels = [s["label"] for s in data["segments"]]
        assert "Tecnologia e TI" in labels
        assert "Alimentação e Bebidas" in labels
        mock_set.assert_called_once()

    async def test_cache_miss_result_has_correct_structure(self, client, mock_pool):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"codigo": 6201500, "descricao": "Dev"}])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.cnaes.cache_get", AsyncMock(return_value=None)):
            with patch("routers.cnaes.cache_set", AsyncMock()):
                with patch("routers.cnaes.get_pool", AsyncMock(return_value=mock_pool)):
                    response = await client.get("/v1/cnaes")

        seg = response.json()["segments"][0]
        assert "label" in seg
        assert "cnaes" in seg
        assert seg["cnaes"][0]["codigo"] == 6201500
```

- [ ] **Step 2: Create `api/routers/cnaes.py`**

```python
"""Router de catálogo de CNAEs agrupados por segmento."""
from fastapi import APIRouter

from cache import cache_get, cache_set
from database import get_pool
from services.cnae_segments import group_cnaes

router = APIRouter()

_CACHE_KEY = "cnpj:cnaes:all"
_CACHE_TTL = 86400  # 24h

_SQL = "SELECT codigo, descricao FROM cnaes ORDER BY codigo"


@router.get("/cnaes", tags=["cnaes"], summary="Lista todos os CNAEs agrupados por segmento")
async def list_cnaes():
    cached = await cache_get(_CACHE_KEY)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL)

    cnaes = [{"codigo": r["codigo"], "descricao": r["descricao"]} for r in rows]
    result = {"segments": group_cnaes(cnaes)}
    await cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
    return result
```

- [ ] **Step 3: Register in `api/main.py`**

In `create_app()`, after the existing `app.include_router(prospecting.router, ...)`, add:

```python
from routers import cnaes
app.include_router(cnaes.router, prefix="/v1")
```

- [ ] **Step 4: Update `api/tests/conftest.py` — add cnaes patches**

Inside the nested `with` blocks in the `client` fixture, add:

```python
with patch("routers.cnaes.get_pool", new_callable=AsyncMock, return_value=mock_pool):
    with patch("routers.cnaes.cache_get", new_callable=AsyncMock, return_value=None):
        with patch("routers.cnaes.cache_set", new_callable=AsyncMock):
```

- [ ] **Step 5: Run tests**

```bash
cd api && python -m pytest tests/test_routers.py::TestCnaesRouter -v
```

Expected: all 3 pass.

- [ ] **Step 6: Commit**

```bash
git add api/routers/cnaes.py api/main.py api/tests/conftest.py api/tests/test_routers.py
git commit -m "feat(api): add GET /v1/cnaes endpoint with Redis cache and segment grouping"
```

---

## Task 8: GET /v1/empresa/{cnpj} router

**Files:**
- Create: `api/routers/empresa.py`
- Modify: `api/main.py`
- Modify: `api/tests/conftest.py`
- Modify: `api/tests/test_routers.py`

- [ ] **Step 1: Write tests — add `TestEmpresaRouter` to `api/tests/test_routers.py`**

```python
class TestEmpresaRouter:
    def _main_row(self):
        return {
            "cnpj_basico": "12345678", "cnpj_ordem": "0001", "cnpj_dv": "90",
            "cnpj_completo": "12345678000190", "razao_social": "TESTE LTDA",
            "nome_fantasia": None, "situacao_cadastral": 2, "data_situacao": None,
            "motivo_situacao": None, "porte": 3, "natureza_juridica": 2062,
            "ente_federativo": None, "data_inicio": None, "matriz_filial": 1,
            "tipo_logradouro": "RUA", "logradouro": "TESTE", "numero": "100",
            "complemento": None, "bairro": "CENTRO", "cep": "01310100",
            "uf": "SP", "municipio": 3550308, "municipio_descricao": "São Paulo",
            "capital_social": 50000.0, "email": "teste@empresa.com",
            "telefone1": "1133334444", "telefone2": None, "fax": None,
            "cnae_principal": 6201500, "cnae_principal_descricao": "Dev de software",
            "cnae_secundarios": None,
        }

    def _mock_pool(self, fetchrow_results, fetch_results):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_results)
        mock_conn.fetch = AsyncMock(side_effect=fetch_results)
        mock_pool = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return mock_pool

    async def test_found_without_punctuation(self, client):
        pool = self._mock_pool([self._main_row(), None], [[], []])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        data = response.json()
        assert data["cnpj_completo"] == "12345678000190"
        assert data["razao_social"] == "TESTE LTDA"

    async def test_found_with_punctuation(self, client):
        pool = self._mock_pool([self._main_row(), None], [[], []])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12.345.678/0001-90")
        assert response.status_code == 200

    async def test_not_found_returns_404(self, client):
        pool = self._mock_pool([None], [[]])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/00000000000000")
        assert response.status_code == 404

    async def test_invalid_cnpj_returns_422(self, client):
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.get_pool", AsyncMock()):
                response = await client.get("/v1/empresa/123")
        assert response.status_code == 422

    async def test_cache_hit_skips_db(self, client):
        cached = {"cnpj_completo": "12345678000190", "razao_social": "CACHED"}
        with patch("routers.empresa.cache_get", AsyncMock(return_value=cached)):
            with patch("routers.empresa.get_pool") as mock_get_pool:
                response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        mock_get_pool.assert_not_called()

    async def test_socios_included(self, client):
        socio = {"nome_socio": "MARIA", "cpf_cnpj_socio": "***", "qualificacao": 49,
                  "qualificacao_descricao": "Sócio", "data_entrada": None, "faixa_etaria": None}
        pool = self._mock_pool([self._main_row(), None], [[socio], []])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        assert response.json()["socios"][0]["nome_socio"] == "MARIA"

    async def test_simples_nacional_included(self, client):
        simples = {"opcao_simples": "S", "data_opcao_simples": None, "data_exc_simples": None,
                   "opcao_mei": "N", "data_opcao_mei": None, "data_exc_mei": None}
        pool = self._mock_pool([self._main_row(), simples], [[], []])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.json()["simples"]["opcao_simples"] == "S"

    async def test_cnae_secundarios_parsed_and_resolved(self, client):
        row = {**self._main_row(), "cnae_secundarios": "6209100,4321500"}
        cnae_rows = [
            {"codigo": 6209100, "descricao": "Suporte TI"},
            {"codigo": 4321500, "descricao": "Instalações"},
        ]
        pool = self._mock_pool([row, None], [cnae_rows, []])
        with patch("routers.empresa.cache_get", AsyncMock(return_value=None)):
            with patch("routers.empresa.cache_set", AsyncMock()):
                with patch("routers.empresa.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        secundarios = response.json()["cnae_secundarios"]
        assert len(secundarios) == 2
        assert secundarios[0]["codigo"] == 6209100
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd api && python -m pytest tests/test_routers.py::TestEmpresaRouter -v 2>&1 | tail -5
```

Expected: ImportError or 404 (router not registered yet).

- [ ] **Step 3: Create `api/routers/empresa.py`**

```python
"""Router de detalhe de empresa — todos os dados de uma empresa pelo CNPJ."""
import re
from fastapi import APIRouter, HTTPException

from cache import cache_get, cache_set, make_cache_key
from database import get_pool
from models.detail import EmpresaDetail

router = APIRouter()

_CNPJ_STRIP = re.compile(r"[.\-/\s]")
_DETAIL_TTL = 3600

_SQL_DETAIL = """
    SELECT
        e.cnpj_basico, est.cnpj_ordem, est.cnpj_dv,
        e.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
        e.razao_social, est.nome_fantasia,
        est.situacao_cadastral, est.data_situacao, est.motivo_situacao,
        e.porte, e.natureza_juridica, e.ente_federativo,
        est.data_inicio, est.matriz_filial,
        est.tipo_logradouro, est.logradouro, est.numero, est.complemento,
        est.bairro, est.cep, est.uf, est.municipio,
        m.descricao AS municipio_descricao,
        e.capital_social, est.email,
        NULLIF(TRIM(COALESCE(est.ddd1,'') || COALESCE(est.telefone1,'')), '') AS telefone1,
        NULLIF(TRIM(COALESCE(est.ddd2,'') || COALESCE(est.telefone2,'')), '') AS telefone2,
        NULLIF(TRIM(COALESCE(est.ddd_fax,'') || COALESCE(est.fax,'')), '') AS fax,
        est.cnae_principal, c.descricao AS cnae_principal_descricao,
        est.cnae_secundarios
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN municipios m ON m.codigo = est.municipio
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3
"""

_SQL_SOCIOS = """
    SELECT s.nome_socio, s.cpf_cnpj_socio, s.qualificacao,
           q.descricao AS qualificacao_descricao, s.data_entrada, s.faixa_etaria
    FROM socios s
    LEFT JOIN qualificacoes q ON q.codigo = s.qualificacao
    WHERE s.cnpj_basico = $1
    ORDER BY s.nome_socio
"""

_SQL_SIMPLES = """
    SELECT opcao_simples, data_opcao_simples, data_exc_simples,
           opcao_mei, data_opcao_mei, data_exc_mei
    FROM simples WHERE cnpj_basico = $1
"""

_SQL_CNAE_SECONDARY = """
    SELECT codigo, descricao FROM cnaes WHERE codigo = ANY($1::int[]) ORDER BY codigo
"""


def _normalize(cnpj: str) -> str:
    return _CNPJ_STRIP.sub("", cnpj)


def _parse_secondary(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(p) for p in re.split(r"[\s,]+", raw.strip()) if p.strip().isdigit()]


@router.get("/empresa/{cnpj}", response_model=EmpresaDetail, tags=["empresa"],
            summary="Detalhes completos de uma empresa pelo CNPJ")
async def get_empresa(cnpj: str):
    normalized = _normalize(cnpj)
    if len(normalized) != 14 or not normalized.isdigit():
        raise HTTPException(status_code=422, detail="CNPJ deve ter 14 dígitos numéricos")

    cache_key = make_cache_key("detail", {"cnpj": normalized})
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    basico, ordem, dv = normalized[:8], normalized[8:12], normalized[12:]
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_DETAIL, basico, ordem, dv)
        if row is None:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        data = dict(row)
        secondary_codes = _parse_secondary(data.pop("cnae_secundarios", None))

        if secondary_codes:
            cnae_rows = await conn.fetch(_SQL_CNAE_SECONDARY, secondary_codes)
            data["cnae_secundarios"] = [dict(r) for r in cnae_rows]
        else:
            data["cnae_secundarios"] = []

        data["socios"] = [dict(r) for r in await conn.fetch(_SQL_SOCIOS, basico)]
        simples_row = await conn.fetchrow(_SQL_SIMPLES, basico)
        data["simples"] = dict(simples_row) if simples_row else None

    await cache_set(cache_key, data, ttl=_DETAIL_TTL)
    return data
```

- [ ] **Step 4: Register in `api/main.py`**

```python
from routers import empresa
app.include_router(empresa.router, prefix="/v1")
```

- [ ] **Step 5: Update `api/tests/conftest.py` — add empresa patches**

```python
with patch("routers.empresa.get_pool", new_callable=AsyncMock, return_value=mock_pool):
    with patch("routers.empresa.cache_get", new_callable=AsyncMock, return_value=None):
        with patch("routers.empresa.cache_set", new_callable=AsyncMock):
```

- [ ] **Step 6: Run tests**

```bash
cd api && python -m pytest tests/test_routers.py::TestEmpresaRouter -v
```

Expected: all 8 pass.

- [ ] **Step 7: Commit**

```bash
git add api/routers/empresa.py api/main.py api/tests/conftest.py api/tests/test_routers.py
git commit -m "feat(api): add GET /v1/empresa/{cnpj} with full detail, socios, simples, CNAE secundários"
```

---

## Task 9: Update GET /v1/prospecting

**Files:**
- Modify: `api/routers/prospecting.py`
- Modify: `api/tests/test_routers.py`

The prospecting router itself doesn't change — it already calls `build_prospecting_query(filters)` and the filter model now handles the new fields. But the existing test `TestProspectingRouter` uses `cnae_principal=6201500` in query params, which no longer exists. Update those tests.

- [ ] **Step 1: Update existing prospecting router tests**

In `api/tests/test_routers.py`, find any `TestProspectingRouter` test that sends `cnae_principal` as a query param and update to `cnaes=6201500`. Find any that sends `porte=3` and update to `porte=3` (single int in query string still works as a list of one from FastAPI's query param parsing — verify this works).

Add new test for CNPJ search mode:

```python
async def test_search_by_cnpj_returns_single_result(self, client, mock_pool):
    row = {
        "cnpj_basico": "12345678", "cnpj_ordem": "0001", "cnpj_dv": "90",
        "cnpj_completo": "12345678000190", "razao_social": "TESTE LTDA",
        "nome_fantasia": None, "situacao_cadastral": 2, "cnae_principal": None,
        "cnae_descricao": None, "uf": "SP", "municipio": None,
        "municipio_descricao": None, "email": None, "telefone1": None,
        "porte": 3, "capital_social": None, "data_inicio": None,
    }
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[row])
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    response = await client.get("/v1/prospecting?cnpj=12.345.678/0001-90")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cnpj_completo"] == "12345678000190"
```

- [ ] **Step 2: Run prospecting tests**

```bash
cd api && python -m pytest tests/test_routers.py -k "Prospecting" -v
```

Expected: all pass.

- [ ] **Step 3: Run full API test suite**

```bash
cd api && python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=100 2>&1 | tail -30
```

Fix any coverage gaps before continuing.

- [ ] **Step 4: Commit**

```bash
git add api/tests/test_routers.py
git commit -m "test(api): update prospecting tests for new filter fields, add CNPJ search test"
```

---

## Task 10: Frontend — api/client.ts

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Rewrite `frontend/src/api/client.ts`**

```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/v1',
})

export interface EmpresaOut {
  cnpj_basico: string
  cnpj_ordem: string
  cnpj_dv: string
  cnpj_completo: string
  razao_social: string
  nome_fantasia: string | null
  situacao_cadastral: number | null
  cnae_principal: number | null
  cnae_descricao: string | null
  uf: string | null
  municipio: number | null
  municipio_descricao: string | null
  email: string | null
  telefone1: string | null
  porte: number | null
  capital_social: number | null
  data_inicio: string | null
}

export interface CnaeItem {
  codigo: number
  descricao: string | null
}

export interface SocioOut {
  nome_socio: string | null
  cpf_cnpj_socio: string | null
  qualificacao: number | null
  qualificacao_descricao: string | null
  data_entrada: string | null
  faixa_etaria: number | null
}

export interface SimplesOut {
  opcao_simples: string | null
  data_opcao_simples: string | null
  data_exc_simples: string | null
  opcao_mei: string | null
  data_opcao_mei: string | null
  data_exc_mei: string | null
}

export interface EmpresaDetail extends EmpresaOut {
  data_situacao: string | null
  motivo_situacao: number | null
  natureza_juridica: number | null
  ente_federativo: string | null
  matriz_filial: number | null
  tipo_logradouro: string | null
  logradouro: string | null
  numero: string | null
  complemento: string | null
  bairro: string | null
  cep: string | null
  telefone2: string | null
  fax: string | null
  cnae_principal_descricao: string | null
  cnae_secundarios: CnaeItem[]
  socios: SocioOut[]
  simples: SimplesOut | null
}

export interface CnaeSegment {
  label: string
  cnaes: CnaeItem[]
}

export interface CnaesResponse {
  segments: CnaeSegment[]
}

export interface Filters {
  cnpj?: string
  uf?: string
  municipio?: number
  bairro?: string
  cnaes?: number[]
  situacao_cadastral?: number
  porte?: number[]
  excluir_mei?: boolean
  capital_social_min?: number
  capital_social_max?: number
  busca_razao?: string
  matriz_filial?: number
  data_inicio_min?: string
  data_inicio_max?: string
  opcao_simples?: boolean
  natureza_juridica?: number
  cursor_cnpj_basico?: string
  cursor_cnpj_ordem?: string
  limit?: number
}

export interface StatusResponse {
  total_empresas: number
  total_estabelecimentos: number
  etl_files: Array<{ arquivo: string; status: string; loaded_at: string | null }>
}

export const searchEmpresas = (filters: Filters): Promise<EmpresaOut[]> =>
  api.get<EmpresaOut[]>('/prospecting', { params: filters }).then(r => r.data)

export const getEmpresa = (cnpj: string): Promise<EmpresaDetail> =>
  api.get<EmpresaDetail>(`/empresa/${encodeURIComponent(cnpj)}`).then(r => r.data)

export const getCnaes = (): Promise<CnaesResponse> =>
  api.get<CnaesResponse>('/cnaes').then(r => r.data)

export const getStatus = (): Promise<StatusResponse> =>
  api.get<StatusResponse>('/status').then(r => r.data)

export const buildExportCsvUrl = (filters: Filters): string => {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) {
      for (const item of v) params.append(k, String(item))
    } else {
      params.set(k, String(v))
    }
  }
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/v1'
  return `${base}/export/csv?${params}`
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(frontend): update API client types for new filters and endpoints"
```

---

## Task 11: useCnaes hook + CnaeSelector component

**Files:**
- Create: `frontend/src/hooks/useCnaes.ts`
- Create: `frontend/src/components/CnaeSelector.tsx`

- [ ] **Step 1: Create `frontend/src/hooks/useCnaes.ts`**

```typescript
import { useQuery } from '@tanstack/react-query'
import { getCnaes, type CnaeSegment } from '../api/client'

export function useCnaes(): { segments: CnaeSegment[]; loading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ['cnaes'],
    queryFn: getCnaes,
    staleTime: Infinity,
  })
  return { segments: data?.segments ?? [], loading: isLoading }
}
```

- [ ] **Step 2: Create `frontend/src/components/CnaeSelector.tsx`**

```typescript
import { useState } from 'react'
import { ChevronDown, ChevronRight, X } from 'lucide-react'
import { useCnaes } from '../hooks/useCnaes'
import type { CnaeItem } from '../api/client'

interface Props {
  selected: number[]
  onChange: (codes: number[]) => void
}

export function CnaeSelector({ selected, onChange }: Props) {
  const { segments, loading } = useCnaes()
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const selectedSet = new Set(selected)

  const toggle = (code: number) => {
    const next = new Set(selectedSet)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    onChange([...next])
  }

  const toggleSegment = (label: string, cnaes: CnaeItem[]) => {
    const codes = cnaes.map(c => c.codigo)
    const allSelected = codes.every(c => selectedSet.has(c))
    const next = new Set(selectedSet)
    if (allSelected) codes.forEach(c => next.delete(c))
    else codes.forEach(c => next.add(c))
    onChange([...next])
  }

  const toggleExpanded = (label: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const q = search.toLowerCase()
  const filtered = segments
    .map(seg => ({
      ...seg,
      cnaes: seg.cnaes.filter(
        c => !q || c.codigo.toString().includes(q) || (c.descricao ?? '').toLowerCase().includes(q),
      ),
    }))
    .filter(seg => seg.cnaes.length > 0)

  if (loading) return <p className="text-xs text-gray-400">Carregando CNAEs…</p>

  return (
    <div className="flex flex-col gap-2">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map(code => {
            const desc = segments.flatMap(s => s.cnaes).find(c => c.codigo === code)?.descricao
            return (
              <span key={code} className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
                {code}
                <button type="button" onClick={() => toggle(code)}>
                  <X className="h-3 w-3" />
                </button>
              </span>
            )
          })}
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-xs text-gray-400 underline hover:text-gray-600"
          >
            limpar
          </button>
        </div>
      )}

      <input
        type="text"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Buscar CNAE…"
        className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />

      <div className="max-h-48 overflow-y-auto rounded-md border border-gray-200 bg-white">
        {filtered.map(seg => {
          const isOpen = expanded.has(seg.label) || !!q
          const segCodes = seg.cnaes.map(c => c.codigo)
          const allChecked = segCodes.every(c => selectedSet.has(c))
          const someChecked = segCodes.some(c => selectedSet.has(c))

          return (
            <div key={seg.label}>
              <div className="flex cursor-pointer items-center gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2">
                <input
                  type="checkbox"
                  checked={allChecked}
                  ref={el => { if (el) el.indeterminate = someChecked && !allChecked }}
                  onChange={() => toggleSegment(seg.label, seg.cnaes)}
                  className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600"
                  onClick={e => e.stopPropagation()}
                />
                <button
                  type="button"
                  className="flex flex-1 items-center gap-1 text-left text-xs font-semibold text-gray-700"
                  onClick={() => toggleExpanded(seg.label)}
                >
                  {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  {seg.label}
                  <span className="ml-auto font-normal text-gray-400">
                    {someChecked ? `${segCodes.filter(c => selectedSet.has(c)).length}/` : ''}{seg.cnaes.length}
                  </span>
                </button>
              </div>

              {isOpen && (
                <div>
                  {seg.cnaes.map(cnae => (
                    <label key={cnae.codigo} className="flex cursor-pointer items-start gap-2 px-4 py-1.5 hover:bg-blue-50">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(cnae.codigo)}
                        onChange={() => toggle(cnae.codigo)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-gray-300 text-blue-600"
                      />
                      <span className="text-xs text-gray-700">
                        <span className="font-mono text-gray-500">{cnae.codigo}</span>
                        {cnae.descricao && ` — ${cnae.descricao}`}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useCnaes.ts frontend/src/components/CnaeSelector.tsx
git commit -m "feat(frontend): add useCnaes hook and CnaeSelector with accordion segments"
```

---

## Task 12: FilterPanel rewrite

**Files:**
- Modify: `frontend/src/components/FilterPanel.tsx`

- [ ] **Step 1: Rewrite `frontend/src/components/FilterPanel.tsx`**

```typescript
import { useState, type FormEvent } from 'react'
import { Loader2, RotateCcw, Search } from 'lucide-react'
import type { Filters } from '../api/client'
import { CnaeSelector } from './CnaeSelector'

interface Props {
  onSearch: (filters: Filters) => void
  loading: boolean
}

const UFS = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']

const NATUREZAS = [
  { value: 2062, label: 'Sociedade Ltda' },
  { value: 2240, label: 'S.A. Aberta' },
  { value: 2232, label: 'S.A. Fechada' },
  { value: 2135, label: 'EIRELI' },
  { value: 5010, label: 'Empresário Individual (MEI)' },
  { value: 2011, label: 'Empresa Individual' },
  { value: 3999, label: 'Associação' },
]

const PORTES = [
  { value: 1, label: 'MEI' },
  { value: 2, label: 'ME' },
  { value: 3, label: 'EPP' },
  { value: 5, label: 'Demais' },
]

const LIMITS = [50, 100, 500, 1000, 5000]

const inputClass =
  'rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100'

const labelClass = 'flex flex-col gap-1.5 text-sm font-medium text-gray-700'

const DEFAULT_FILTERS: Filters = { situacao_cadastral: 2 }

export function FilterPanel({ onSearch, loading }: Props) {
  const [cnpj, setCnpj] = useState('')
  const [buscaRazao, setBuscaRazao] = useState('')
  const [uf, setUf] = useState('')
  const [bairro, setBairro] = useState('')
  const [selectedCnaes, setSelectedCnaes] = useState<number[]>([])
  const [portes, setPortes] = useState<number[]>([])
  const [excluirMei, setExcluirMei] = useState(false)
  const [capitalMin, setCapitalMin] = useState('')
  const [capitalMax, setCapitalMax] = useState('')
  const [matrizFilial, setMatrizFilial] = useState('')
  const [dataMin, setDataMin] = useState('')
  const [dataMax, setDataMax] = useState('')
  const [opcaoSimples, setOpcaoSimples] = useState(false)
  const [naturezaJuridica, setNaturezaJuridica] = useState('')
  const [limit, setLimit] = useState(50)

  const cnpjMode = cnpj.trim().length > 0
  const meiInPortes = portes.includes(1)

  const togglePorte = (v: number) =>
    setPortes(prev => (prev.includes(v) ? prev.filter(p => p !== v) : [...prev, v]))

  const buildFilters = (): Filters => {
    if (cnpjMode) return { cnpj: cnpj.trim(), limit }
    return {
      ...DEFAULT_FILTERS,
      ...(buscaRazao.trim() && { busca_razao: buscaRazao.trim() }),
      ...(uf && { uf }),
      ...(bairro.trim() && { bairro: bairro.trim() }),
      ...(selectedCnaes.length > 0 && { cnaes: selectedCnaes }),
      ...(portes.length > 0 && { porte: portes }),
      ...(!meiInPortes && excluirMei && { excluir_mei: true }),
      ...(capitalMin && { capital_social_min: Number(capitalMin) }),
      ...(capitalMax && { capital_social_max: Number(capitalMax) }),
      ...(matrizFilial && { matriz_filial: Number(matrizFilial) }),
      ...(dataMin && { data_inicio_min: dataMin }),
      ...(dataMax && { data_inicio_max: dataMax }),
      ...(opcaoSimples && { opcao_simples: true }),
      ...(naturezaJuridica && { natureza_juridica: Number(naturezaJuridica) }),
      limit,
    }
  }

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSearch(buildFilters())
  }

  const handleClear = () => {
    setCnpj(''); setBuscaRazao(''); setUf(''); setBairro(''); setSelectedCnaes([])
    setPortes([]); setExcluirMei(false); setCapitalMin(''); setCapitalMax('')
    setMatrizFilial(''); setDataMin(''); setDataMax(''); setOpcaoSimples(false)
    setNaturezaJuridica(''); setLimit(50)
    onSearch(DEFAULT_FILTERS)
  }

  const disabledClass = cnpjMode ? 'pointer-events-none opacity-40' : ''

  return (
    <aside className="h-full w-full overflow-y-auto border-r border-gray-200 bg-gray-50 p-5 lg:w-80">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">CNPJ Discovery</h1>
          <p className="mt-1 text-sm text-gray-500">Prospecção de empresas</p>
        </div>

        <label className={labelClass}>
          Buscar por CNPJ
          <input type="text" value={cnpj} onChange={e => setCnpj(e.target.value)}
            className={inputClass} placeholder="00.000.000/0001-00" />
          {cnpjMode && (
            <span className="rounded bg-yellow-50 px-2 py-1 text-xs text-yellow-700">
              Demais filtros ignorados
            </span>
          )}
        </label>

        <div className={`flex flex-col gap-4 ${disabledClass}`}>
          <label className={labelClass}>
            Razão social ou fantasia
            <input type="text" value={buscaRazao} onChange={e => setBuscaRazao(e.target.value)}
              className={inputClass} placeholder="Buscar empresa" />
          </label>

          <label className={labelClass}>
            UF
            <select value={uf} onChange={e => setUf(e.target.value)} className={inputClass}>
              <option value="">Todos</option>
              {UFS.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </label>

          <label className={labelClass}>
            Bairro
            <input type="text" value={bairro} onChange={e => setBairro(e.target.value)}
              className={inputClass} placeholder="Ex: Centro" />
          </label>

          <div className={labelClass}>
            CNAE
            <CnaeSelector selected={selectedCnaes} onChange={setSelectedCnaes} />
          </div>

          <fieldset>
            <legend className="mb-1.5 text-sm font-medium text-gray-700">Porte</legend>
            <div className="flex flex-wrap gap-3">
              {PORTES.map(p => (
                <label key={p.value} className="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" checked={portes.includes(p.value)}
                    onChange={() => togglePorte(p.value)}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600" />
                  {p.label}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="flex items-center gap-3 text-sm font-medium text-gray-700">
            <input type="checkbox" checked={!meiInPortes && excluirMei}
              disabled={meiInPortes}
              onChange={e => setExcluirMei(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 disabled:cursor-not-allowed disabled:opacity-50" />
            Excluir MEI
          </label>

          <div className={labelClass}>
            Capital Social (R$)
            <div className="flex gap-2">
              <input type="number" value={capitalMin} onChange={e => setCapitalMin(e.target.value)}
                className={inputClass} placeholder="Mínimo" min="0" step="0.01" />
              <input type="number" value={capitalMax} onChange={e => setCapitalMax(e.target.value)}
                className={inputClass} placeholder="Máximo" min="0" step="0.01" />
            </div>
          </div>

          <label className={labelClass}>
            Estabelecimento
            <select value={matrizFilial} onChange={e => setMatrizFilial(e.target.value)} className={inputClass}>
              <option value="">Todos</option>
              <option value="1">Somente Matriz</option>
              <option value="2">Somente Filial</option>
            </select>
          </label>

          <div className={labelClass}>
            Data de Abertura
            <div className="flex gap-2">
              <input type="date" value={dataMin} onChange={e => setDataMin(e.target.value)}
                className={inputClass} />
              <input type="date" value={dataMax} onChange={e => setDataMax(e.target.value)}
                className={inputClass} />
            </div>
          </div>

          <label className="flex items-center gap-3 text-sm font-medium text-gray-700">
            <input type="checkbox" checked={opcaoSimples} onChange={e => setOpcaoSimples(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600" />
            Somente Simples Nacional
          </label>

          <label className={labelClass}>
            Natureza Jurídica
            <select value={naturezaJuridica} onChange={e => setNaturezaJuridica(e.target.value)} className={inputClass}>
              <option value="">Todas</option>
              {NATUREZAS.map(n => <option key={n.value} value={n.value}>{n.label}</option>)}
            </select>
          </label>

          <label className={labelClass}>
            Resultados por página
            <select value={limit} onChange={e => setLimit(Number(e.target.value))} className={inputClass}>
              {LIMITS.map(l => <option key={l} value={l}>{l.toLocaleString('pt-BR')}</option>)}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button type="button" onClick={handleClear}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100">
            <RotateCcw className="h-4 w-4" /> Limpar
          </button>
          <button type="submit" disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Buscar
          </button>
        </div>
      </form>
    </aside>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FilterPanel.tsx
git commit -m "feat(frontend): rewrite FilterPanel with CNPJ search, multi-CNAE, bairro, and all new filters"
```

---

## Task 13: CompanyDetailModal

**Files:**
- Create: `frontend/src/components/CompanyDetailModal.tsx`

- [ ] **Step 1: Create `frontend/src/components/CompanyDetailModal.tsx`**

```typescript
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Building2, MapPin, Phone, Briefcase, Users, FileText } from 'lucide-react'
import { getEmpresa, type EmpresaDetail } from '../api/client'

interface Props {
  cnpj: string | null
  onClose: () => void
}

const porteLabels: Record<number, string> = { 1: 'MEI', 2: 'ME', 3: 'EPP', 5: 'Demais' }
const matrizLabel: Record<number, string> = { 1: 'Matriz', 2: 'Filial' }

const formatDate = (d: string | null) => d ? new Date(d + 'T00:00:00').toLocaleDateString('pt-BR') : '—'
const formatCurrency = (v: number | null) =>
  v === null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900 uppercase tracking-wide">
        {icon}{title}
      </h3>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs text-gray-900 break-words">{value || '—'}</span>
    </div>
  )
}

function DetailContent({ data }: { data: EmpresaDetail }) {
  const endereco = [
    data.tipo_logradouro, data.logradouro, data.numero, data.complemento,
  ].filter(Boolean).join(' ')

  return (
    <div className="space-y-6">
      <Section icon={<Building2 className="h-4 w-4" />} title="Identificação">
        <Row label="CNPJ" value={data.cnpj_completo} />
        <Row label="Razão Social" value={data.razao_social} />
        <Row label="Nome Fantasia" value={data.nome_fantasia} />
        <Row label="Porte" value={data.porte ? porteLabels[data.porte] ?? String(data.porte) : null} />
        <Row label="Tipo" value={data.matriz_filial ? matrizLabel[data.matriz_filial] : null} />
        <Row label="Capital Social" value={formatCurrency(data.capital_social)} />
        <Row label="Data de Abertura" value={formatDate(data.data_inicio)} />
        <Row label="Situação" value={data.situacao_cadastral === 2 ? 'Ativa' : String(data.situacao_cadastral ?? '—')} />
        {data.simples && (
          <Row label="Simples Nacional"
            value={
              <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${data.simples.opcao_simples === 'S' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                {data.simples.opcao_simples === 'S' ? 'Simples' : 'Não optante'}
                {data.simples.opcao_mei === 'S' && ' · MEI'}
              </span>
            }
          />
        )}
      </Section>

      <Section icon={<MapPin className="h-4 w-4" />} title="Endereço">
        <Row label="Logradouro" value={endereco} />
        <Row label="Bairro" value={data.bairro} />
        <Row label="CEP" value={data.cep} />
        <Row label="Município" value={data.municipio_descricao} />
        <Row label="UF" value={data.uf} />
      </Section>

      <Section icon={<Phone className="h-4 w-4" />} title="Contatos">
        <Row label="E-mail" value={data.email ? <a href={`mailto:${data.email}`} className="text-blue-600 underline">{data.email}</a> : null} />
        <Row label="Telefone 1" value={data.telefone1} />
        <Row label="Telefone 2" value={data.telefone2} />
        <Row label="Fax" value={data.fax} />
      </Section>

      <Section icon={<Briefcase className="h-4 w-4" />} title="CNAEs">
        <Row label="Principal" value={data.cnae_principal ? `${data.cnae_principal} — ${data.cnae_principal_descricao ?? ''}` : null} />
        {data.cnae_secundarios.length > 0 && (
          <div className="mt-2">
            <p className="mb-1 text-xs text-gray-500">Secundários:</p>
            <ul className="space-y-1">
              {data.cnae_secundarios.map(c => (
                <li key={c.codigo} className="text-xs text-gray-700">
                  <span className="font-mono text-gray-500">{c.codigo}</span>
                  {c.descricao && ` — ${c.descricao}`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      {data.socios.length > 0 && (
        <Section icon={<Users className="h-4 w-4" />} title="Sócios">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-1.5 pr-3 text-left font-medium">Nome</th>
                  <th className="py-1.5 pr-3 text-left font-medium">Qualificação</th>
                  <th className="py-1.5 text-left font-medium">Entrada</th>
                </tr>
              </thead>
              <tbody>
                {data.socios.map((s, i) => (
                  <tr key={i} className="border-b border-gray-100 last:border-0">
                    <td className="py-1.5 pr-3 text-gray-900">{s.nome_socio ?? '—'}</td>
                    <td className="py-1.5 pr-3 text-gray-600">{s.qualificacao_descricao ?? s.qualificacao ?? '—'}</td>
                    <td className="py-1.5 text-gray-600">{formatDate(s.data_entrada)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  )
}

export function CompanyDetailModal({ cnpj, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['empresa', cnpj],
    queryFn: () => getEmpresa(cnpj!),
    enabled: !!cnpj,
  })

  if (!cnpj) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">Detalhes da Empresa</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {isLoading && (
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-md bg-gray-100" />
              ))}
            </div>
          )}
          {isError && <p className="text-sm text-red-600">Erro ao carregar dados da empresa.</p>}
          {data && <DetailContent data={data} />}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CompanyDetailModal.tsx
git commit -m "feat(frontend): add CompanyDetailModal drawer with full company data"
```

---

## Task 14: ResultsTable + Prospecting.tsx

**Files:**
- Modify: `frontend/src/components/ResultsTable.tsx`
- Modify: `frontend/src/pages/Prospecting.tsx`

- [ ] **Step 1: Update `frontend/src/components/ResultsTable.tsx`**

Add `onSelectEmpresa` prop and make rows clickable. Change the `cnae_principal` column to show `cnae_descricao`:

```typescript
interface Props {
  data: EmpresaOut[]
  onLoadMore: () => void
  hasMore: boolean
  searched: boolean
  onSelectEmpresa: (cnpj: string) => void
}

export function ResultsTable({ data, onLoadMore, hasMore, searched, onSelectEmpresa }: Props) {
```

In the `<tr>` element, add:
```typescript
<tr
  key={row.cnpj_completo}
  className="cursor-pointer hover:bg-blue-50"
  onClick={() => onSelectEmpresa(row.cnpj_completo)}
>
```

Change CNAE cell from `{row.cnae_principal ?? '-'}` to `{row.cnae_descricao || row.cnae_principal || '-'}`.

- [ ] **Step 2: Update `frontend/src/pages/Prospecting.tsx`**

Add `selectedCnpj` state and wire up modal:

```typescript
import { CompanyDetailModal } from '../components/CompanyDetailModal'

// inside component:
const [selectedCnpj, setSelectedCnpj] = useState<string | null>(null)

// in JSX, after </main>:
<CompanyDetailModal cnpj={selectedCnpj} onClose={() => setSelectedCnpj(null)} />

// pass to ResultsTable:
<ResultsTable
  data={allResults}
  onLoadMore={handleLoadMore}
  hasMore={hasMore}
  searched={searched}
  onSelectEmpresa={setSelectedCnpj}
/>
```

Also update `withDefaultLimit` to preserve the user's limit choice rather than hardcoding 50:

```typescript
const DEFAULT_LIMIT = 50

// Remove the withDefaultLimit helper — the limit now comes from FilterPanel directly.
// runSearch receives filters that already include limit.
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Start dev server and smoke-test**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`. Verify:
- All filter fields appear
- CNPJ field disables other filters with warning
- CNAE accordion opens/closes, search filters CNAEs, tags appear for selected
- Clicking a company row opens the detail drawer
- Drawer closes with ESC or clicking overlay
- Export CSV button still works

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ResultsTable.tsx frontend/src/pages/Prospecting.tsx
git commit -m "feat(frontend): clickable table rows open company detail modal"
```

---

## Task 15: Final coverage check + rebuild

- [ ] **Step 1: Run full API test suite with coverage**

```bash
cd api && python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=100
```

Fix any gaps.

- [ ] **Step 2: Run full ETL test suite**

```bash
cd etl && python -m pytest --cov=. --cov-report=term-missing 2>&1 | tail -20
```

- [ ] **Step 3: Rebuild and restart API container**

```bash
docker compose build api && docker compose up -d api
```

- [ ] **Step 4: Smoke-test live endpoints**

```bash
curl -s http://localhost:8000/v1/cnaes | python3 -m json.tool | head -20
curl -s "http://localhost:8000/v1/prospecting?situacao_cadastral=2&limit=5" | python3 -m json.tool | head -20
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and container rebuild for advanced filters feature"
```
