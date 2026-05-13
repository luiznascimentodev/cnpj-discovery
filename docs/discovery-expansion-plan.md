# Plano: Expansão da Discovery — TLDs, Email Direto, Busca Externa

**Objetivo:** Enriquecer empresas que hoje ficam sem domínio verificado por não terem email
corporativo na RF ou por terem domínio com nome diferente do slug gerado.

**Estratégias:**
- **A** — Mais TLDs no brand slug (`.net.br`, `.org.br`, `.ind.br`)
- **B** — Email genérico da RF salvo diretamente como contato (conf=40)
- **C** — Cadeia externa: BrasilAPI → Brave Search, acionada quando nenhum domínio é enfileirado

---

## Estado atual do pipeline

```
process_target(cnpj)
  └─ fetch estabelecimento (RF local)
  └─ normalize_rf_email → se corporativo: candidato conf=90
  └─ generate_brand_slugs → candidatos conf=45 (.com.br) / conf=35 (.com)
  └─ se candidates vazio → retorna (0, 0)         ← GAP: 14/20 empresas ficam aqui
  └─ para cada candidato: probe → score → upsert
  └─ se score ≥ 60 e sinal forte → enfileira crawl_requests
```

**Gap identificado:** Empresas com email `@gmail.com` ou sem email não geram candidatos
suficientes. O brand slug tenta `nomeempresa.com.br` mas sem sinal forte na página o score
não alcança 60 → não enfileira.

---

## Estratégia A — Mais TLDs no brand slug

### O que muda

**Arquivo:** `enrichment/domain_discovery.py` — função `domains_from_brand_slugs`

**Hoje:**
```python
for suffix, confidence in ((".com.br", 45), (".com", 35)):
```

**Depois:**
```python
for suffix, confidence in (
    (".com.br", 45),
    (".net.br", 42),
    (".org.br", 40),
    (".ind.br", 35),
    (".com",    33),
):
```

Não incluímos `.tur.br`, `.srv.br`, `.gov.br` porque são muito nichados e aumentam
requisições sem ganho relevante.

### Impacto

- Por empresa com 2 slugs (legal + fantasia): hoje 4 candidatos, depois 10.
- O probe HTTP é feito para todos; domínios 404/dead continuam com confidence ≤ 30
  (capped em `_initial_confidence`) e status `rejected`. Sem risco de falsos positivos.
- Ganho estimado: +10–15% de cobertura em empresas associativas, industriais, ONGs.

### Testes necessários

- `test_domain_discovery.py`: adicionar caso `domains_from_brand_slugs` retorna
  `.net.br` e `.org.br` para o mesmo slug.
- `test_domain_discovery.py`: verificar que `.com` ainda aparece e com conf < `.com.br`.

---

## Estratégia B — Email genérico da RF como contato direto

### Problema

Empresas com `email=joao@gmail.com` na RF não têm domínio para crawlar, mas têm
um contato real — o dono registrou esse email na Receita Federal. É evidência fraca
mas válida.

### O que muda

**Arquivo:** `enrichment/discovery/pipeline.py` — função `process_target`

Novo SQL (salvo no mesmo arquivo como constante):

```python
_SQL_UPSERT_RF_EMAIL_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'email', $4, $4, 'Email RF', 'rf_email_direct', 40, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET
        last_seen = now()
"""
```

Lógica inserida em `process_target`, logo após normalizar `rf_email`:

```python
# B: email genérico da RF → salvo como contato direto de baixa confiança
if rf_email and rf_email.classification == "public_provider":
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_RF_EMAIL_CONTACT,
            cnpj_basico, cnpj_ordem, cnpj_dv,
            rf_email.normalized_value,
        )
```

### Decisões de design

- **Confidence 40:** O email foi registrado na RF pelo responsável da empresa. É real,
  mas não prova que a empresa ainda usa esse email. Score baixo o suficiente para não
  poluir resultados primários, alto o suficiente para aparecer quando solicitado.
- **ON CONFLICT DO UPDATE SET last_seen:** Idempotente. Re-rodar não duplica.
- **Salvar antes do loop de candidatos:** Independe de a empresa ter ou não domínio.
  Uma empresa pode ter domínio verificado E email gmail — ambos devem ser salvos.
- **Não bloqueia o retorno early:** Se `not candidates`, ainda retornamos após salvar
  o email. O `DiscoveryOutcome.domains_seen` continua 0 (correto — não descobrimos domínio).

### DiscoveryOutcome

Adicionamos campo `rf_contacts_saved: int = 0` para rastreamento:

```python
@dataclass(frozen=True)
class DiscoveryOutcome:
    cnpj: str
    domains_seen: int
    crawl_requests_created: int
    rf_contacts_saved: int = 0   # novo
```

### Testes necessários

- `test_discovery_pipeline.py`: Quando email é `@gmail.com`, verifica que um
  `execute` para `enriched_contacts` é chamado com os parâmetros corretos.
- `test_discovery_pipeline.py`: Quando email é corporativo (`@acme.com.br`), verifica
  que NÃO há insert em `enriched_contacts` pela rota B (só pelo crawler domain).
- `test_discovery_pipeline.py`: Quando não há email, verifica que não há inserts B.
- Atualizar `test_returns_zero_when_no_candidates`: hoje não verifica `execute_calls`,
  mas após B haverá um execute — adicionar asserção explícita.

---

## Estratégia C — Cadeia de busca externa

### Visão geral

Quando `process_target` termina o loop de candidatos sem enfileirar nenhum crawl
(ou seja, nenhum domínio foi verificado), chamamos a cadeia externa:

```
company sem domínio enfileirado
  └─ [C1] BrasilAPI /api/cnpj/v1/{cnpj14}
      └─ se email retornado for corporativo e diferente do email local
          └─ adiciona candidato conf=90, retorna ao loop normal
      └─ se mesma situação → [C2]
  └─ [C2] Brave Search: "{razao_social} {municipio_descricao} site oficial"
      └─ extrai domínios dos top-3 resultados (filtra diretórios)
      └─ adiciona candidatos conf=55
      └─ retorna ao loop normal (probe → score → upsert)
```

### C1 — BrasilAPI

**Novo arquivo:** `enrichment/discovery/brasilapi.py`

```python
@dataclass(frozen=True)
class BrasilAPIResult:
    email: str | None
    ddd_telefone_1: str | None
    ddd_telefone_2: str | None

async def fetch_cnpj(cnpj14: str, *, client: httpx.AsyncClient) -> BrasilAPIResult | None:
    """Retorna None em qualquer erro (timeout, 404, rate-limit)."""
    ...
```

- URL: `{BRASILAPI_BASE_URL}/cnpj/v1/{cnpj14}` (cnpj14 = 14 dígitos sem máscara)
- Timeout: 8s (mais curto que o probe de site — é uma API JSON)
- HTTP 429 / 5xx → retorna None (graceful degradation)
- O campo `email` da BrasilAPI vem como string simples; normalizar com `normalize_rf_email`

**Integração em `pipeline.py`:**

Se BrasilAPI retorna email corporativo diferente do email local → gera novo candidato
via `domains_from_rf_email` e o adiciona à lista. Executa probe + score normalmente.

**Quando NÃO chamar BrasilAPI:**
- Empresa já tem `status='verified'` em `company_domains` → skip total (verificado via query antes do loop)
- BrasilAPI está desabilitado (`brasilapi_enabled=False` em Settings)

### C2 — Brave Search

**Novo arquivo:** `enrichment/discovery/brave_search.py`

```python
@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str

async def search_company_domain(
    company_name: str,
    city: str | None,
    *,
    client: httpx.AsyncClient,
    api_key: str,
) -> list[SearchResult]:
    """Retorna lista vazia em qualquer erro."""
    ...
```

- Endpoint: `GET https://api.search.brave.com/res/v1/web/search`
- Headers: `X-Subscription-Token: {api_key}`, `Accept: application/json`
- Params: `q="{company_name}" {city or ''} site oficial`, `count=5`, `country=BR`
- Timeout: 10s
- HTTP 4xx/5xx → retorna `[]`

**Extração de domínio dos resultados:**

```python
_DIRECTORY_DOMAINS = frozenset({
    "receita.fazenda.gov.br",
    "cnpj.info", "cnpj.biz", "qsa.net.br",
    "jusbrasil.com.br", "reclameaqui.com.br",
    "linkedin.com", "facebook.com", "instagram.com",
    "twitter.com", "youtube.com",
    "tiktok.com", "maps.google.com",
    "empresas.net.br", "infocnpj.com",
})

def extract_candidate_domains(results: list[SearchResult]) -> list[DomainCandidate]:
    ...
```

- Pega top-3 resultados
- Extrai domínio via `normalize_domain(url)`
- Descarta se domínio está em `_DIRECTORY_DOMAINS`
- Retorna como `DomainCandidate(source="brave_search", confidence=55)`
- Confidence 55: acima de 45 (slug) para dar preferência, mas abaixo de 90 (RF email).
  O `score_domain_evidence` decide se chega a `verified`.

**Quando NÃO chamar Brave:**
- `brave_search_api_key` está vazio → skip (feature flag implícita por ausência de key)
- BrasilAPI já resolveu (novo candidato foi enfileirado) → skip
- Empresa já tem domínio verificado → skip (mesma guarda de C1)

### ExternalSearchClient

Para facilitar mock nos testes, encapsulamos C1 + C2 em uma classe:

**Novo arquivo:** `enrichment/discovery/external_search.py`

```python
@dataclass
class ExternalSearchClient:
    brasilapi_enabled: bool
    brave_api_key: str        # string vazia = desabilitado
    brasilapi_base_url: str   # permite override nos testes
    brave_base_url: str       # permite override nos testes

    async def enrich_candidates(
        self,
        cnpj14: str,
        legal_name: str,
        city: str | None,
        client: httpx.AsyncClient,
    ) -> list[DomainCandidate]:
        """Retorna novos candidatos a partir de BrasilAPI e/ou Brave Search."""
        ...
```

**Factory function** criada em `config.py`:

```python
def make_external_search_client() -> ExternalSearchClient:
    return ExternalSearchClient(
        brasilapi_enabled=settings.brasilapi_enabled,
        brave_api_key=settings.brave_search_api_key,
        brasilapi_base_url=settings.brasilapi_base_url,
        brave_base_url=settings.brave_search_base_url,
    )
```

### Integração em `pipeline.py`

`process_target` recebe parâmetro opcional:

```python
async def process_target(
    pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    client: httpx.AsyncClient,
    external_search: ExternalSearchClient | None = None,   # novo
) -> DiscoveryOutcome:
```

Lógica inserida após o loop de candidatos, antes do `return`:

```python
# C: se nenhum domínio foi enfileirado e temos external_search configurado
if requests_created == 0 and external_search is not None:
    # verifica se já há domínio verificado antes de gastar quota
    already_verified = await _has_verified_domain(conn, cnpj_basico, cnpj_ordem, cnpj_dv)
    if not already_verified:
        extra_candidates = await external_search.enrich_candidates(
            cnpj14=cnpj,
            legal_name=_row_value(row, "razao_social"),
            city=_row_value(row, "municipio_descricao"),
            client=client,
        )
        async with pool.acquire() as conn:
            for candidate in extra_candidates:
                probe = await probe_domain(candidate.domain, client=client)
                score = score_domain_evidence(...)
                await conn.execute(_SQL_UPSERT_DOMAIN, ...)
                if probe.ok and not probe.parked and _should_enqueue_crawl(score):
                    for path in PRIORITY_PATHS:
                        await conn.execute(_SQL_INSERT_CRAWL_REQUEST, ...)
                        requests_created += 1
```

SQL auxiliar para verificação:

```python
_SQL_HAS_VERIFIED_DOMAIN = """
    SELECT 1 FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND status = 'verified'
    LIMIT 1
"""
```

### Configuração nova em `config.py`

```python
brasilapi_enabled: bool = True
brasilapi_base_url: str = "https://brasilapi.com.br/api"
brave_search_api_key: str = ""           # vazio = desabilitado
brave_search_base_url: str = "https://api.search.brave.com"
```

`.env.example` (a ser atualizado):
```
BRASILAPI_ENABLED=true
BRAVE_SEARCH_API_KEY=your_key_here
```

### Testes necessários para C

**`tests/test_brasilapi.py`** (novo):
- Retorna `BrasilAPIResult` quando BrasilAPI responde 200 com email corporativo
- Retorna `None` em HTTP 429 (rate limit)
- Retorna `None` em HTTP 404 (CNPJ não encontrado)
- Retorna `None` em timeout

**`tests/test_brave_search.py`** (novo):
- Retorna domínios válidos filtrados de `_DIRECTORY_DOMAINS`
- Retorna lista vazia em HTTP 4xx
- Exclui corretamente domínios de diretórios
- Lida com top-3 (ignora resultados além do 3°)

**`tests/test_external_search.py`** (novo):
- `enrich_candidates` chama BrasilAPI primeiro; se resolve, não chama Brave
- `enrich_candidates` chama Brave quando BrasilAPI não resolve
- Se `brasilapi_enabled=False`: pula BrasilAPI, vai direto para Brave
- Se `brave_api_key=""`: não chama Brave, retorna lista vazia
- Ambos desabilitados → retorna lista vazia

**`tests/test_discovery_pipeline.py`** (atualizar):
- `process_target` com `external_search=None` não muda comportamento existente (sem quebrar testes)
- `process_target` com `external_search` mockado: quando `requests_created=0` chama `enrich_candidates`
- `process_target` com `external_search` mockado: quando `requests_created>0` NÃO chama `enrich_candidates`
- `process_target` com `external_search` mockado: quando empresa já tem domínio verificado, não chama external search

---

## Ordem de implementação

1. **A** — Muda 1 linha em `domain_discovery.py` + 2 testes. Risco zero.
2. **B** — Nova SQL constant + 5 linhas em `pipeline.py` + 3 testes. Risco baixo.
3. **C1** — Novo `discovery/brasilapi.py` + testes unitários. Sem integração ainda.
4. **C2** — Novo `discovery/brave_search.py` + testes unitários. Sem integração ainda.
5. **C-glue** — Novo `discovery/external_search.py` + integração em `pipeline.py` + testes de integração.
6. **Config** — Adicionar campos em `config.py` + atualizar `docker-compose.yml`.

---

## Riscos e mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| BrasilAPI fora do ar | Média | `try/except` amplo → retorna None; cadeia continua para Brave |
| Brave quota esgotada (2000/mês) | Baixa no início | Só acionado quando candidatos = 0 E empresa sem domínio verificado — número muito menor que o total de targets |
| Brave retorna domínio errado com conf=55 | Média | `score_domain_evidence` ainda precisa de sinais (CNPJ/nome na página) para chegar a `verified`; falsos positivos ficam como `candidate` e não são crawlados |
| B aumenta volume de `enriched_contacts` com emails de baixa qualidade | Certa | Confidence=40 é visível para consumidores da API; podem filtrar por confidence mínima |
| Brand slug expandido aumenta probes de HTTP | Certa | +4 probes por empresa vs hoje. Discovery batch de 20 = +80 requests. Aceitável. |
| 100% coverage quebrar | Baixa | Cada módulo novo tem arquivo de teste dedicado; `ExternalSearchClient` é testado com mocks HTTP via `httpx.MockTransport` |

---

## Resumo dos arquivos afetados

| Arquivo | Mudança |
|---|---|
| `domain_discovery.py` | A: adiciona TLDs |
| `discovery/pipeline.py` | B: insert email genérico; C: integra ExternalSearchClient |
| `discovery/brasilapi.py` | **NOVO** — C1 |
| `discovery/brave_search.py` | **NOVO** — C2 |
| `discovery/external_search.py` | **NOVO** — orquestra C1+C2 |
| `config.py` | C: 4 novos campos |
| `tests/test_domain_discovery.py` | A: novos casos de TLD |
| `tests/test_discovery_pipeline.py` | B+C: novos cenários |
| `tests/test_brasilapi.py` | **NOVO** |
| `tests/test_brave_search.py` | **NOVO** |
| `tests/test_external_search.py` | **NOVO** |
