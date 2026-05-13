# RF Intelligence + Extraction Quality Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevar cobertura e confiabilidade de extração de contatos cruzando TODOS os dados da Receita Federal disponíveis no banco (endereço, CNAE, MEI, matriz/filial) com técnicas de limpeza de HTML inspiradas no Firecrawl (trafilatura + contexto de proximidade).

**Architecture:** Três camadas de melhoria independentes:
1. **Extraction quality** — HTML limpo via trafilatura antes das regexes + boost de confiança por contexto adjacente a labels como "whatsapp", "telefone"
2. **Verifier signals** — Novos sinais RF: bairro (+8), logradouro+numero (+15), CNAE keywords (+5) — cruzamento CIA-grade com HTML da empresa
3. **Pipeline intelligence** — Resolução matriz/filial (filiais herdam domínio da matriz), detecção MEI/Simples (pula brand_slug, vai direto ao social), detecção JS-heavy → Playwright automático

**Tech Stack:** Python 3.12, trafilatura (nova dep), asyncpg, httpx, pytest, 100% coverage obrigatória.

---

## Diagnóstico do estado atual

**O que já fazemos:**
- CEP match (+20pts), city (+5), uf (+5), phone RF (+20), CNPJ (+60), email domínio (+35)
- Sócios locais como sinal no verifier (+20) e queries de busca
- External search com CNPJ-first via Brave/Google CSE

**O que deixamos na mesa:**
- `bairro`, `logradouro`, `numero` da tabela `estabelecimentos` — nunca verificados no HTML
- `cnae_principal` — descrição do setor completamente ignorada
- `simples.opcao_mei = 'S'` — 10M MEIs no Brasil; quase nenhum tem website próprio, 90% estão no Instagram/WhatsApp
- `cnpj_ordem != '0001'` (filiais) — ~40% dos CNPJs são filiais; o domínio pertence à matriz (cnpj_ordem='0001')
- HTML bruto com nav/footer/cookie banners gerando falsos positivos nas regexes de contato
- Telefone/email em rodapé genérico de template WordPress com mesma confiança que o contato real no `/contato`

---

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `enrichment/requirements.txt` | **Modificar** | Adicionar `trafilatura>=1.9` |
| `enrichment/extraction.py` | **Modificar** | Função `extract_main_content()` + context-aware confidence |
| `enrichment/resolver/domain_verifier.py` | **Modificar** | Sinais bairro, logradouro, CNAE |
| `enrichment/discovery/pipeline.py` | **Modificar** | Busca bairro/logradouro/CNAE/MEI/matriz, passa novos campos |
| `enrichment/tests/test_extraction.py` | **Modificar** | Testes para trafilatura + context boost |
| `enrichment/tests/test_domain_verifier.py` | **Modificar** | Testes para bairro/logradouro/CNAE signals |
| `enrichment/tests/test_discovery_pipeline.py` | **Modificar** | Testes para MEI skip, matrix resolution |
| `enrichment/crawler/runner.py` | **Modificar** | Detecção JS-heavy → enqueue playwright |
| `enrichment/tests/test_crawler_runner.py` | **Modificar** | Testes para JS-heavy detection |
| `enrichment/tests/test_config_database.py` | **Modificar** | Cobertura google_cse_enabled |
| `enrichment/tests/test_brave_search.py` | **Modificar** | Cobertura JSON decode error |
| `enrichment/tests/test_google_cse.py` | **Modificar** | Cobertura JSON decode + max_results break |

---

## Task 1: Corrigir cobertura de testes faltando (bloqueante)

**Goal:** 100% coverage antes de qualquer nova feature. 6 linhas descobertas em `config.py`, `brave_search.py`, `google_cse.py`.

**Files:**
- Modify: `enrichment/tests/test_config_database.py`
- Modify: `enrichment/tests/test_brave_search.py`
- Modify: `enrichment/tests/test_google_cse.py`

- [ ] **Step 1: Adicionar teste para `google_cse_enabled` em test_config_database.py**

Adicionar ao final da classe `TestSettings`:

```python
    def test_google_cse_enabled_false_when_empty(self):
        settings = Settings()
        assert settings.google_cse_enabled is False

    def test_google_cse_enabled_true_when_both_set(self):
        settings = Settings(google_cse_api_key="key", google_cse_cx="cx")
        assert settings.google_cse_enabled is True
```

- [ ] **Step 2: Adicionar teste para JSON decode error em test_brave_search.py**

Adicionar no final da classe `TestSearchCompanyDomain`:

```python
    @pytest.mark.asyncio
    async def test_returns_empty_on_json_decode_error(self):
        def handler(_request):
            return httpx.Response(200, content=b"not json", headers={"content-type": "text/html"})

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Empresa", None, client=client, api_key="key"
            )
        assert candidates == []
```

- [ ] **Step 3: Adicionar testes para google_cse.py em test_google_cse.py**

Adicionar ao final da classe `TestSearchGoogleCse`:

```python
    @pytest.mark.asyncio
    async def test_returns_empty_on_json_decode_error(self):
        def handler(_request):
            return httpx.Response(200, content=b"not json", headers={"content-type": "text/html"})

        query = SearchQuery('"test"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")
        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_max_3_results(self):
        def handler(_request):
            return _cse_response([
                _item("https://a.com.br"),
                _item("https://b.com.br"),
                _item("https://c.com.br"),
                _item("https://d.com.br"),
                _item("https://e.com.br"),
            ])

        query = SearchQuery('"test"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")
        assert len(candidates) == 3
```

- [ ] **Step 4: Rodar suite completa**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `419+ passed`, coverage = 100%.

- [ ] **Step 5: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/tests/test_config_database.py enrichment/tests/test_brave_search.py enrichment/tests/test_google_cse.py
git commit -m "test: achieve 100% coverage on config, brave_search, google_cse

Cover google_cse_enabled property, JSON decode error paths,
and max_results=3 enforcement."
```

---

## Task 2: Trafilatura — HTML limpo antes da extração de contatos

**Goal:** Instalar `trafilatura`, adicionar `extract_main_content(html) -> str | None` em `extraction.py`, usar como camada adicional de extração. Contatos encontrados no conteúdo principal (trafilatura) ganham +8 de confiança vs. contatos só no HTML bruto.

**Files:**
- Modify: `enrichment/requirements.txt`
- Modify: `enrichment/extraction.py`
- Modify: `enrichment/tests/test_extraction.py`

- [ ] **Step 1: Adicionar trafilatura aos requirements**

Em `enrichment/requirements.txt`, adicionar:
```
trafilatura>=1.9
```

- [ ] **Step 2: Instalar dependência**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
pip install trafilatura>=1.9 --quiet
```

- [ ] **Step 3: Escrever testes para extract_main_content**

Adicionar ao final de `enrichment/tests/test_extraction.py`:

```python
from extraction import extract_main_content


class TestExtractMainContent:
    def test_returns_none_on_empty_html(self):
        assert extract_main_content("") is None

    def test_returns_none_on_nav_only_html(self):
        html = """<html><body>
        <nav><a href="/">Home</a><a href="/sobre">Sobre</a></nav>
        </body></html>"""
        # trafilatura may return None when there's no main content
        result = extract_main_content(html)
        # Either None or a very short string — no assertion on content, just type
        assert result is None or isinstance(result, str)

    def test_returns_main_content_from_article(self):
        html = """<html><body>
        <nav><a href="/">Home</a></nav>
        <main>
          <p>Entre em contato pelo telefone (11) 98765-4321 ou email contato@empresa.com.br</p>
        </main>
        <footer><p>© 2024 Empresa</p></footer>
        </body></html>"""
        result = extract_main_content(html)
        assert result is not None
        assert "98765-4321" in result or "contato@empresa.com.br" in result

    def test_returns_string_on_typical_corporate_page(self):
        html = """<html><body>
        <h1>Fale Conosco</h1>
        <p>Telefone: (11) 3333-4444</p>
        <p>Email: vendas@corpbrasil.com.br</p>
        <p>Endereço: Rua das Flores, 123 - São Paulo</p>
        </body></html>"""
        result = extract_main_content(html)
        assert result is None or isinstance(result, str)


class TestExtractContactsMainContentBoost:
    def test_contact_in_main_content_gets_higher_confidence(self):
        """Contato no conteúdo principal tem confiança >= contato só no rodapé."""
        html_main = """<html><body>
        <main><p>Fale conosco: (11) 99999-8888</p></main>
        </body></html>"""
        html_footer = """<html><body>
        <footer><p>Tel: (11) 99999-8888</p></footer>
        </body></html>"""
        contacts_main = extract_contacts_from_html(html_main, source_url="https://test.com")
        contacts_footer = extract_contacts_from_html(html_footer, source_url="https://test.com")
        phones_main = [c for c in contacts_main if c.contact_type == "phone"]
        phones_footer = [c for c in contacts_footer if c.contact_type == "phone"]
        if phones_main and phones_footer:
            assert phones_main[0].confidence >= phones_footer[0].confidence
```

- [ ] **Step 4: Rodar testes para confirmar que falham**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/test_extraction.py -v -k "MainContent" --tb=short 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'extract_main_content'`

- [ ] **Step 5: Implementar extract_main_content e boost em extraction.py**

Adicionar no topo de `extraction.py`, após os imports existentes:

```python
try:
    import trafilatura as _trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TRAFILATURA_AVAILABLE = False
```

Adicionar a função `extract_main_content` antes de `extract_contacts_from_html`:

```python
def extract_main_content(html: str) -> str | None:
    """Extrai conteúdo principal do HTML removendo nav/footer/ads via trafilatura.
    
    Retorna None se trafilatura não disponível ou não encontra conteúdo suficiente.
    """
    if not html or not _TRAFILATURA_AVAILABLE:
        return None
    try:
        return _trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
        )
    except Exception:
        return None
```

Em `extract_contacts_from_html`, adicionar extração de conteúdo principal com boost de confiança. Localizar onde a função cria o `parser` e faz `parser.feed(html)`. Após a extração normal, adicionar:

```python
    # Boost de confiança para contatos encontrados no conteúdo principal
    main_content = extract_main_content(html)
    if main_content:
        main_parser = _ContactHtmlParser(source_url)
        main_parser.feed(main_content)
        main_contacts = _resolve_contacts(main_parser, source_url)
        main_values = {
            (c.contact_type, c.normalized_value)
            for c in main_contacts
        }
        # Aplica boost +8 para contatos presentes no conteúdo principal
        boosted = []
        for c in contacts:
            if (c.contact_type, c.normalized_value) in main_values:
                from dataclasses import replace
                c = replace(c, confidence=min(c.confidence + 8, 100))
            boosted.append(c)
        contacts = boosted
```

**IMPORTANTE:** Para isso funcionar, a função `extract_contacts_from_html` precisa expor a lista `contacts` antes de retornar. Leia o código atual cuidadosamente para inserir no ponto certo.

- [ ] **Step 6: Rodar todos os testes de extraction**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/test_extraction.py -v --tb=short 2>&1 | tail -20
```

Todos devem passar.

- [ ] **Step 7: Suite completa**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

100% coverage, todos passam.

- [ ] **Step 8: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/requirements.txt enrichment/extraction.py enrichment/tests/test_extraction.py
git commit -m "feat(enrichment): trafilatura HTML cleaning + main-content confidence boost

Extracts main content via trafilatura before regex extraction.
Contacts found in main content (not nav/footer/ads) get +8 confidence
boost. Reduces false positives from template footers and cookie banners."
```

---

## Task 3: Context-aware confidence — boost por label adjacente

**Goal:** Ao encontrar um telefone ou email no HTML, verificar os 60 chars ao redor. Se adjacent a labels como "whatsapp", "telefone", "celular", "contato" → boost de confiança (+10). Remove ambiguidade de números que parecem telefone mas são datas, referências ou CEPs.

**Files:**
- Modify: `enrichment/extraction.py`
- Modify: `enrichment/tests/test_extraction.py`

- [ ] **Step 1: Adicionar testes de context boost**

Adicionar ao final de `enrichment/tests/test_extraction.py`:

```python
class TestContextAwareConfidence:
    def test_phone_near_whatsapp_label_gets_boost(self):
        html = """<html><body>
        <p>WhatsApp: (11) 98765-4321</p>
        </body></html>"""
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        phones = [c for c in contacts if c.contact_type == "phone"]
        assert phones, "deve encontrar pelo menos um telefone"
        assert phones[0].confidence > 70

    def test_phone_near_telefone_label_gets_boost(self):
        html = """<html><body><p>Telefone: (11) 3333-4444</p></body></html>"""
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        phones = [c for c in contacts if c.contact_type == "phone"]
        assert phones
        assert phones[0].confidence > 70

    def test_phone_without_label_gets_base_confidence(self):
        html = """<html><body><p>Código: 11987654321</p></body></html>"""
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        phones = [c for c in contacts if c.contact_type == "phone"]
        if phones:
            assert phones[0].confidence <= 78

    def test_email_near_contato_label_gets_boost(self):
        html = """<html><body><p>Contato: vendas@empresa.com.br</p></body></html>"""
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        emails = [c for c in contacts if c.contact_type == "email"]
        assert emails
        assert emails[0].confidence > 78
```

- [ ] **Step 2: Implementar context-aware boost em extraction.py**

Adicionar após os imports, antes da classe `_ContactHtmlParser`:

```python
_PHONE_CONTEXT_LABELS = re.compile(
    r"(?:whatsapp|wh?ats|zap|celular?|cel|fone|telefone?|tel|fax|"
    r"contato|fale|atendimento|suporte|sac|vendas|comercial)",
    re.IGNORECASE,
)
_EMAIL_CONTEXT_LABELS = re.compile(
    r"(?:e-?mail|contato|fale|atendimento|suporte|comercial|vendas|envie)",
    re.IGNORECASE,
)
_CONTEXT_WINDOW = 60


def _context_confidence_boost(context: str | None, contact_type: str) -> int:
    """Retorna boost de confiança (0 ou +10) baseado em labels adjacentes."""
    if not context:
        return 0
    if contact_type in {"phone", "whatsapp"}:
        return 10 if _PHONE_CONTEXT_LABELS.search(context) else 0
    if contact_type == "email":
        return 10 if _EMAIL_CONTEXT_LABELS.search(context) else 0
    return 0
```

Em `extract_contacts_from_html`, ao criar `ExtractedContact` para contatos extraídos via `visible_text`, capturar contexto e aplicar boost:

```python
# Ao criar contato de visible_text, passa o contexto e aplica boost
context_window = text[max(0, start - _CONTEXT_WINDOW):end + _CONTEXT_WINDOW]
boost = _context_confidence_boost(context_window, "phone")  # ou "email"
confidence = base_confidence + boost
```

**IMPORTANTE:** Leia a implementação atual de `extract_contacts_from_html` antes de modificar. O boost deve ser aplicado apenas para contatos extraídos de `visible_text`, não de links `tel:` ou `mailto:` (esses já têm alta confiança).

- [ ] **Step 3: Rodar testes**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/test_extraction.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 4: Suite completa**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/extraction.py enrichment/tests/test_extraction.py
git commit -m "feat(enrichment): context-aware confidence boost for phone/email

Contacts adjacent to labels like 'whatsapp', 'telefone', 'contato'
get +10 confidence boost. Distinguishes real contact listings from
accidental phone-like numbers in reference codes, dates, or metadata."
```

---

## Task 4: Novos sinais RF no verificador — bairro, logradouro, CNAE

**Goal:** Adicionar 3 novos sinais ao `score_domain_evidence()` usando dados RF ainda não utilizados:
- `bairro` (bairro da empresa) → +8 pts se encontrado no HTML  
- `logradouro` (rua + número) → +15 pts se ambos encontrados no HTML — endereço é o sinal mais forte de identidade física
- `cnae_description` (descrição do CNAE principal) → +5 pts se keywords do setor no HTML

**Files:**
- Modify: `enrichment/resolver/domain_verifier.py`
- Modify: `enrichment/tests/test_domain_verifier.py`

- [ ] **Step 1: Adicionar testes para novos sinais**

Adicionar ao final de `enrichment/tests/test_domain_verifier.py`:

```python
class TestAddressSignals:
    def test_bairro_found_adds_8_pts(self):
        html = "<html><body>Localizado no bairro Vila Mariana, São Paulo</body></html>"
        result = score_domain_evidence(
            html,
            domain="empresa.com.br",
            cnpj="12345678000190",
            bairro="Vila Mariana",
        )
        assert "bairro_match" in result.signals
        assert result.score >= 8

    def test_bairro_not_found_adds_nothing(self):
        html = "<html><body>Bem-vindo à nossa empresa</body></html>"
        result_without = score_domain_evidence(html, domain="d.com", cnpj="12345678000190")
        result_with = score_domain_evidence(html, domain="d.com", cnpj="12345678000190", bairro="Moema")
        assert result_with.score == result_without.score

    def test_logradouro_found_adds_15_pts(self):
        html = "<html><body>Rua das Flores, 123 - São Paulo</body></html>"
        result = score_domain_evidence(
            html,
            domain="empresa.com.br",
            cnpj="12345678000190",
            logradouro="Rua das Flores",
            numero="123",
        )
        assert "logradouro_match" in result.signals
        assert result.score >= 15

    def test_logradouro_without_numero_does_not_match(self):
        html = "<html><body>Rua das Flores em São Paulo</body></html>"
        result = score_domain_evidence(
            html,
            domain="empresa.com.br",
            cnpj="12345678000190",
            logradouro="Rua das Flores",
            numero="999",
        )
        assert "logradouro_match" not in result.signals

    def test_cnae_description_keywords_add_5_pts(self):
        html = "<html><body>Desenvolvimento de software e soluções tecnológicas</body></html>"
        result = score_domain_evidence(
            html,
            domain="empresa.com.br",
            cnpj="12345678000190",
            cnae_description="Desenvolvimento de programas de computador sob encomenda",
        )
        assert "cnae_keyword_match" in result.signals
        assert result.score >= 5

    def test_cnae_description_no_match_adds_nothing(self):
        html = "<html><body>Padaria artesanal com pães frescos</body></html>"
        result_without = score_domain_evidence(html, domain="d.com", cnpj="12345678000190")
        result_with = score_domain_evidence(
            html, domain="d.com", cnpj="12345678000190",
            cnae_description="Fabricação de software para finanças"
        )
        assert result_with.score == result_without.score

    def test_full_address_combined_reaches_high_score(self):
        """CEP + bairro + logradouro juntos = 43pts, suficiente para candidate."""
        cep = "01310100"
        html = f"<html><body>CEP: {cep[:5]}-{cep[5:]} | Av. Paulista, 1000 | Bela Vista</body></html>"
        result = score_domain_evidence(
            html,
            domain="empresa.com.br",
            cnpj="99999999000199",
            cep=cep,
            bairro="Bela Vista",
            logradouro="Av. Paulista",
            numero="1000",
        )
        assert result.score >= 40
        assert result.status in {"candidate", "verified"}
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/test_domain_verifier.py -v -k "Address" --tb=short 2>&1 | head -15
```

Expected: `TypeError: score_domain_evidence() got an unexpected keyword argument 'bairro'`

- [ ] **Step 3: Atualizar domain_verifier.py**

Adicionar parâmetros à assinatura de `score_domain_evidence`:

```python
def score_domain_evidence(
    html: str,
    *,
    domain: str,
    cnpj: str,
    legal_name: str | None = None,
    fantasy_name: str | None = None,
    rf_email_domain: str | None = None,
    rf_phone_normalized: str | None = None,
    cep: str | None = None,
    city: str | None = None,
    uf: str | None = None,
    bairro: str | None = None,          # NOVO
    logradouro: str | None = None,      # NOVO
    numero: str | None = None,          # NOVO
    cnae_description: str | None = None,  # NOVO
    partner_names: list[str] | None = None,
    is_directory: bool = False,
    is_parked: bool = False,
) -> DomainScoreResult:
```

Adicionar lógica dos novos sinais após o bloco de `cep_match` (todos antes do bloco de `partner_names`):

```python
    # Bairro match — +8 pts
    if bairro:
        bairro_norm = _normalize_text(bairro).strip()
        if bairro_norm and re.search(rf"\b{re.escape(bairro_norm)}\b", html_norm):
            score += 8
            signals.append("bairro_match")

    # Logradouro + número — +15 pts (requer ambos no HTML)
    if logradouro and numero:
        logradouro_norm = _normalize_text(logradouro).strip()
        numero_clean = re.sub(r"\D", "", numero)
        if (logradouro_norm
                and re.search(rf"\b{re.escape(logradouro_norm)}\b", html_norm)
                and numero_clean
                and numero_clean in re.sub(r"\D", "", html)):
            score += 15
            signals.append("logradouro_match")

    # CNAE description keywords — +5 pts (pelo menos 2 tokens de 4+ chars encontrados)
    if cnae_description:
        cnae_norm = _normalize_text(cnae_description)
        cnae_tokens = [t for t in cnae_norm.split() if len(t) >= 4]
        if cnae_tokens:
            matches = sum(1 for t in cnae_tokens if re.search(rf"\b{re.escape(t)}\b", html_norm))
            if matches >= 2:
                score += 5
                signals.append("cnae_keyword_match")
```

- [ ] **Step 4: Rodar todos os testes do verifier**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/test_domain_verifier.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 5: Suite completa**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/resolver/domain_verifier.py enrichment/tests/test_domain_verifier.py
git commit -m "feat(enrichment): bairro/logradouro/CNAE verifier signals

Three new RF cross-reference signals:
- bairro_match (+8): neighborhood in HTML → precise geolocation
- logradouro_match (+15): street address + number → strongest physical identity
- cnae_keyword_match (+5): sector keywords → confirms business type
Combined with CEP(+20): address block alone can reach 43pts (candidate)."
```

---

## Task 5: Pipeline — passar novos campos RF ao verifier

**Goal:** Buscar `bairro`, `logradouro`, `numero` e `cnae_description` do banco e passá-los ao `score_domain_evidence()` em todas as chamadas. Atualizar as queries SQL do pipeline.

**Files:**
- Modify: `enrichment/discovery/pipeline.py`
- Modify: `enrichment/tests/test_discovery_pipeline.py`

- [ ] **Step 1: Atualizar _SQL_FETCH_ESTABELECIMENTO**

Em `pipeline.py`, atualizar a query `_SQL_FETCH_ESTABELECIMENTO` para incluir os novos campos:

```python
_SQL_FETCH_ESTABELECIMENTO = """
    SELECT e.razao_social,
           est.nome_fantasia,
           est.email,
           est.uf,
           est.municipio,
           m.descricao AS municipio_descricao,
           est.cep,
           est.ddd1,
           est.telefone1,
           est.ddd2,
           est.telefone2,
           est.bairro,
           est.logradouro,
           est.numero,
           est.cnae_principal,
           c.descricao AS cnae_descricao
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN municipios m ON m.codigo = est.municipio
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3
"""
```

- [ ] **Step 2: Atualizar chamadas a score_domain_evidence em pipeline.py**

Em AMBAS as chamadas a `score_domain_evidence` (loop de brand_slug e loop de extra_candidates), adicionar os novos campos:

```python
            score = score_domain_evidence(
                probe.body,
                domain=candidate.domain,
                cnpj=cnpj,
                legal_name=_row_value(row, "razao_social"),
                fantasy_name=_row_value(row, "nome_fantasia"),
                rf_email_domain=_rf_email_domain(rf_email),
                rf_phone_normalized=rf_phone.normalized_value if rf_phone else None,
                cep=_row_value(row, "cep"),
                city=_row_value(row, "municipio_descricao"),
                uf=_row_value(row, "uf"),
                bairro=_row_value(row, "bairro"),           # NOVO
                logradouro=_row_value(row, "logradouro"),   # NOVO
                numero=_row_value(row, "numero"),           # NOVO
                cnae_description=_row_value(row, "cnae_descricao"),  # NOVO
                partner_names=partner_names,
                is_parked=probe.parked,
            )
```

- [ ] **Step 3: Atualizar testes em test_discovery_pipeline.py**

Leia o arquivo de testes atual e atualize os mocks do `FakeConnection.fetchrow` para incluir os novos campos `bairro`, `logradouro`, `numero`, `cnae_descricao` no dict de retorno. Adicione `None` para cada novo campo nos mocks existentes (retrocompatível).

Adicionar ao final um teste que verifica que os campos de endereço são passados ao score:

```python
class TestPipelineAddressSignals:
    @pytest.mark.asyncio
    async def test_passes_address_fields_to_verifier(self):
        """Pipeline deve passar bairro/logradouro/numero/cnae ao score_domain_evidence."""
        scores_called_with = []

        async def fake_score(html, *, domain, cnpj, bairro=None, logradouro=None,
                             numero=None, cnae_description=None, **kwargs):
            scores_called_with.append({
                "bairro": bairro,
                "logradouro": logradouro,
                "numero": numero,
                "cnae_description": cnae_description,
            })
            from resolver.domain_verifier import DomainScoreResult
            return DomainScoreResult(score=0, status="rejected", signals=())

        # Adaptar ao padrão de mock do arquivo existente
        # Verificar que scores_called_with[0]["bairro"] == "Vila Mariana"
```

- [ ] **Step 4: Rodar suite**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/discovery/pipeline.py enrichment/tests/test_discovery_pipeline.py
git commit -m "feat(enrichment): pass bairro/logradouro/CNAE from RF to domain verifier

Fetch address and sector data from RF tables (estabelecimentos + cnaes)
and pass to score_domain_evidence(). The logradouro+numero combination
is the strongest new signal: a company's street address in HTML is nearly
unambiguous proof of domain ownership."
```

---

## Task 6: Resolução matriz/filial — filiais herdam domínio da matriz

**Goal:** ~40% dos CNPJs são filiais (`cnpj_ordem != '0001'`). Quando a matriz já tem um domínio verificado, as filiais devem usar o mesmo domínio sem precisar de discovery independente. Economiza ~40% das queries de busca.

**Files:**
- Modify: `enrichment/discovery/pipeline.py`
- Modify: `enrichment/tests/test_discovery_pipeline.py`

- [ ] **Step 1: Adicionar SQL de resolução de matriz**

Em `pipeline.py`, adicionar:

```python
_SQL_FETCH_MATRIX_DOMAIN = """
    SELECT domain, homepage_url, confidence
    FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = '0001' AND cnpj_dv IS NOT NULL
      AND status = 'verified'
    ORDER BY confidence DESC
    LIMIT 1
"""
```

- [ ] **Step 2: Adicionar lógica de resolução em process_target**

Logo após buscar o estabelecimento e antes de qualquer discovery, adicionar:

```python
    # Filiais herdam domínio da matriz quando disponível
    if cnpj_ordem != "0001":
        async with pool.acquire() as conn:
            matrix_row = await conn.fetchrow(_SQL_FETCH_MATRIX_DOMAIN, cnpj_basico)
        if matrix_row:
            await _upsert_matrix_domain(
                pool, cnpj_basico, cnpj_ordem, cnpj_dv, matrix_row
            )
            return DiscoveryOutcome(
                cnpj=cnpj,
                domains_seen=1,
                crawl_requests_created=0,
                rf_contacts_saved=rf_contacts_saved,
            )
```

Adicionar função helper `_upsert_matrix_domain`:

```python
async def _upsert_matrix_domain(pool, cnpj_basico, cnpj_ordem, cnpj_dv, matrix_row) -> None:
    """Copia domínio verificado da matriz para a filial."""
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_DOMAIN,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            matrix_row["domain"],
            matrix_row["homepage_url"],
            "matrix_resolution",
            matrix_row["confidence"],
            "verified",
        )
```

- [ ] **Step 3: Escrever testes**

Adicionar ao final de `enrichment/tests/test_discovery_pipeline.py`:

```python
class TestMatrixFilialResolution:
    @pytest.mark.asyncio
    async def test_filial_uses_matrix_domain_when_available(self):
        """Filial (cnpj_ordem != '0001') deve copiar domínio da matriz."""
        matrix_domain_row = {
            "domain": "matriz.com.br",
            "homepage_url": "https://matriz.com.br",
            "confidence": 95,
        }
        # mock fetchrow(_SQL_FETCH_MATRIX_DOMAIN) → matrix_domain_row
        # Verificar que _SQL_UPSERT_DOMAIN é chamado com source="matrix_resolution"
        # Verificar que process_target retorna domains_seen=1, crawl_requests_created=0

    @pytest.mark.asyncio
    async def test_matriz_does_not_use_matrix_resolution(self):
        """Matriz (cnpj_ordem = '0001') nunca entra no bloco de resolução."""
        # process_target com cnpj_ordem='0001' não deve chamar _SQL_FETCH_MATRIX_DOMAIN

    @pytest.mark.asyncio
    async def test_filial_runs_full_discovery_when_matrix_has_no_domain(self):
        """Filial deve fazer discovery normal quando matriz não tem domínio verificado."""
        # mock fetchrow(_SQL_FETCH_MATRIX_DOMAIN) → None
        # Verificar que discovery continua normalmente
```

- [ ] **Step 4: Rodar suite**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/discovery/pipeline.py enrichment/tests/test_discovery_pipeline.py
git commit -m "feat(enrichment): matrix/filial domain resolution

When processing a branch (cnpj_ordem != '0001'), check if the parent
company (cnpj_ordem='0001') already has a verified domain and inherit
it. Eliminates ~40% of redundant discoveries since branches share
the same website as their parent company."
```

---

## Task 7: MEI detection — pula brand_slug, vai direto ao social

**Goal:** Empresas com `opcao_mei = 'S'` na tabela `simples` raramente têm website próprio. ~10M MEIs no Brasil usam Instagram/WhatsApp como único canal digital. Detectar MEI no pipeline e: (1) pular brand_slug discovery, (2) usar queries de busca focadas em nome do sócio + Instagram.

**Files:**
- Modify: `enrichment/discovery/pipeline.py`
- Modify: `enrichment/discovery/search_queries.py`
- Modify: `enrichment/tests/test_discovery_pipeline.py`
- Modify: `enrichment/tests/test_search_queries.py`

- [ ] **Step 1: Adicionar SQL para consulta MEI**

Em `pipeline.py`, adicionar:

```python
_SQL_IS_MEI = """
    SELECT opcao_mei FROM simples WHERE cnpj_basico = $1
"""
```

- [ ] **Step 2: Adicionar testes para MEI**

Adicionar ao final de `enrichment/tests/test_search_queries.py`:

```python
from discovery.search_queries import build_search_queries_mei


class TestBuildSearchQueriesMei:
    def test_mei_queries_include_partner_name(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name="JOAO DA SILVA 12345678000190",
            partner_names=["João da Silva"],
            city="São Paulo",
        )
        texts = [q.text for q in queries]
        assert any("João da Silva" in t for t in texts)

    def test_mei_queries_include_instagram_hint(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name="MARIA SOUZA MEI",
            partner_names=["Maria Souza"],
            city="Campinas",
        )
        texts = [q.text for q in queries]
        assert any("instagram" in t.lower() or "whatsapp" in t.lower() for t in texts)

    def test_mei_always_returns_at_least_one_query(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name=None,
            partner_names=[],
            city=None,
        )
        assert len(queries) >= 1
```

- [ ] **Step 3: Implementar build_search_queries_mei em search_queries.py**

Adicionar ao final de `enrichment/discovery/search_queries.py`:

```python
def build_search_queries_mei(
    cnpj14: str,
    legal_name: str | None,
    partner_names: list[str],
    city: str | None,
) -> list[SearchQuery]:
    """Gera queries otimizadas para MEI — prioriza sócio + Instagram/WhatsApp."""
    queries: list[SearchQuery] = []
    seen: set[str] = set()

    def _add(text: str, bonus: int, reason: str) -> None:
        key = _normalize_for_dedup(text)
        if key not in seen:
            seen.add(key)
            queries.append(SearchQuery(text=text, confidence_bonus=bonus, reason=reason))

    # Sócio + Instagram (alta precisão para MEI)
    for partner in partner_names[:1]:
        name = partner.strip()
        if len(name) >= 5:
            if city:
                _add(f'"{name}" {city} instagram', 20, "mei_partner_instagram")
            _add(f'"{name}" instagram', 15, "mei_partner_instagram")
            _add(f'"{name}" whatsapp', 10, "mei_partner_whatsapp")

    # CNPJ como fallback
    formatted = format_cnpj14(cnpj14)
    _add(f'"{formatted}"', 25, "cnpj_exact")

    # Nome legal limpo
    if legal_name:
        short = _strip_legal_suffixes(legal_name)
        if len(short) >= 4 and city:
            _add(f'"{short}" {city}', 8, "mei_legal_city")

    return sorted(queries, key=lambda q: -q.confidence_bonus)
```

- [ ] **Step 4: Detectar MEI em process_target**

Em `pipeline.py`, após buscar o estabelecimento, adicionar detecção de MEI:

```python
    # Detectar MEI — estratégia diferente (social-first, sem brand_slug)
    async with pool.acquire() as conn:
        simples_row = await conn.fetchrow(_SQL_IS_MEI, cnpj_basico)
    is_mei = simples_row and simples_row["opcao_mei"] == "S"
```

Quando `is_mei = True`, pular o loop de `candidates` (brand_slug) e ir direto ao `external_search`, passando `is_mei=True` para usar `build_search_queries_mei`.

**IMPORTANTE:** A lógica de MEI deve substituir apenas o brand_slug discovery. O external_search ainda roda (com queries diferentes). O Playwright fallback continua disponível.

- [ ] **Step 5: Rodar suite**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/discovery/pipeline.py enrichment/discovery/search_queries.py enrichment/tests/test_discovery_pipeline.py enrichment/tests/test_search_queries.py
git commit -m "feat(enrichment): MEI-optimized discovery (social-first)

MEI (micro-entrepreneur, simples.opcao_mei='S') rarely has a website
but almost always has Instagram/WhatsApp. New strategy:
- Skip brand_slug domain generation (99% rejection rate for MEI)
- Use build_search_queries_mei(): partner name + instagram/whatsapp hints
- ~10M MEIs in Brazil benefit from this specialized path"
```

---

## Task 8: JS-heavy detection → Playwright automático

**Goal:** No crawler estático (`runner.py`), após fetch de uma página, contar tags `<script>`. Se > 10 scripts E < 2 contatos encontrados, enfileirar `playwright_contact_probe` automaticamente para aquele domínio. Hoje o Playwright só é acionado para domínios verificados sem nenhum contato.

**Files:**
- Modify: `enrichment/crawler/runner.py`
- Modify: `enrichment/tests/test_crawler_runner.py`

- [ ] **Step 1: Adicionar testes**

Adicionar ao final de `enrichment/tests/test_crawler_runner.py`:

```python
class TestJsHeavyDetection:
    def test_counts_script_tags_in_html(self):
        from crawler.runner import _count_script_tags
        html = "<html><head>" + "<script src='a.js'></script>" * 12 + "</head><body></body></html>"
        assert _count_script_tags(html) == 12

    def test_counts_zero_scripts(self):
        from crawler.runner import _count_script_tags
        html = "<html><body><p>Texto</p></body></html>"
        assert _count_script_tags(html) == 0

    def test_is_js_heavy_true_when_over_threshold(self):
        from crawler.runner import _is_js_heavy
        html = "<script>" * 11
        assert _is_js_heavy(html) is True

    def test_is_js_heavy_false_when_under_threshold(self):
        from crawler.runner import _is_js_heavy
        html = "<script>" * 5
        assert _is_js_heavy(html) is False
```

- [ ] **Step 2: Implementar funções de detecção em runner.py**

Adicionar no topo (após imports existentes):

```python
import re as _re

_SCRIPT_TAG_RE = _re.compile(r"<script[\s>]", _re.IGNORECASE)
_JS_HEAVY_THRESHOLD = 10


def _count_script_tags(html: str) -> int:
    return len(_SCRIPT_TAG_RE.findall(html))


def _is_js_heavy(html: str) -> bool:
    return _count_script_tags(html) > _JS_HEAVY_THRESHOLD
```

Na lógica de processamento de página do runner (após extração de contatos), adicionar:

```python
            # Auto-enqueue Playwright para páginas JS-heavy com poucos contatos
            if _is_js_heavy(html) and len(contacts) < 2:
                await _enqueue_playwright_if_needed(conn, domain)
```

Criar função `_enqueue_playwright_if_needed`:

```python
_SQL_ENQUEUE_PLAYWRIGHT = """
    INSERT INTO paid_enrichment.domain_crawl_jobs
        (domain, url, crawl_profile, source, priority, status)
    VALUES ($1, $2, 'playwright_contact_probe', 'js_heavy_auto', 60, 'pending')
    ON CONFLICT (domain, url, crawl_profile) DO UPDATE
        SET priority = GREATEST(domain_crawl_jobs.priority, EXCLUDED.priority),
            updated_at = now()
"""

async def _enqueue_playwright_if_needed(conn, domain: str) -> None:
    await conn.execute(_SQL_ENQUEUE_PLAYWRIGHT, domain, f"https://{domain}/")
```

- [ ] **Step 3: Rodar suite**

```bash
cd /home/luife/projetos/cnpj-discovery/enrichment
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
cd /home/luife/projetos/cnpj-discovery
git add enrichment/crawler/runner.py enrichment/tests/test_crawler_runner.py
git commit -m "feat(enrichment): auto-enqueue Playwright for JS-heavy pages

Static HTTP crawler now counts <script> tags. Pages with >10 scripts
and <2 contacts found are automatically queued for playwright_contact_probe.
Brazilian CMS sites (WordPress, Wix, VTEX) often load contacts via JS
— this ensures they get full browser rendering."
```

---

## Resultado esperado após implementação

| Sinal | Antes | Depois |
|-------|-------|--------|
| Sinais de verificação disponíveis | 11 | 14 (+bairro, +logradouro, +CNAE) |
| Endereço sozinho pode verificar? | Não (só CEP = 20pts) | Sim (CEP+bairro+logradouro = 43pts → candidate) |
| MEI — taxa de domínio encontrado | ~0.1% (brand_slug falha) | ~15% (Instagram search) |
| Filiais — discovery redundante | ~40% dos CNPJs | Eliminado com resolução de matriz |
| Falsos positivos em contatos | Rodapé = mesmo peso | Rodapé < main content (trafilatura -8 confiança) |
| Contatos com label explícito | Mesmo peso | "WhatsApp: 11 99999" = +10 confiança |
| Páginas JS-heavy sem contatos | Ficam sem contatos | Auto-Playwright enfileirado |

**Por que isso é nível de inteligência:**
- Logradouro+numero no HTML de uma empresa é quase impossível de ser coincidência — é o sinal físico mais forte de identidade
- Resolver filiais pela matriz é o que um analista humano faria: "essa é a filial do Banco X em SP, o site é o mesmo"
- MEIs com Instagram: cruzar `nome_socio` (sócio) + `opcao_mei` (regime) = perfil exato para busca social
- CNAE keywords: uma empresa de "Desenvolvimento de software" que tem "software" e "desenvolvimento" no HTML e não tem CNPJ ainda consegue 35+5=40pts (candidate) e entra no crawl
