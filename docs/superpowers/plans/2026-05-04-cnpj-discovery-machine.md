# Máquina de Prospecção B2B (CNPJ Discovery) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir uma máquina de prospecção B2B independente que ingere, processa e expõe ~50 milhões de registros de CNPJs da Receita Federal através de uma interface de busca com filtros avançados e exportação de leads.

**Architecture:** Pipeline ETL em Python processa arquivos ZIP da Receita Federal via streaming, carrega no PostgreSQL com COPY bulk insert, e expõe os dados via API FastAPI com paginação por cursor. O ambiente é 100% containerizado com Docker Compose para garantir paridade entre local e VPS.

**Tech Stack:**
- **ETL:** Python 3.12, Polars (parsing CSV ultrarrápido), httpx (download async), psycopg2 (COPY bulk insert)
- **Banco:** PostgreSQL 16 (índices B-Tree compostos, GIN full-text search)
- **API:** FastAPI + asyncpg (connection pool async)
- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui
- **Infra:** Docker Compose (local e prod), Nginx (reverse proxy), Redis + Celery (fila de download)
- **Scheduler:** APScheduler (cron interno) ou cron do sistema operacional
- **Notifications:** httpx → Discord/Slack Webhook

---

## Visão Geral da Arquitetura

```
┌──────────────────────────────────────────────────────────┐
│                    Docker Compose                         │
│                                                           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  Nginx   │──▶│ Frontend │   │   ETL    │             │
│  │  :80/443 │   │  :3000   │   │ Worker   │             │
│  └────┬─────┘   └──────────┘   └────┬─────┘             │
│       │                              │                    │
│       ▼                              ▼                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  FastAPI │──▶│PostgreSQL│◀──│  Redis   │             │
│  │  :8000   │   │  :5432   │   │  :6379   │             │
│  └──────────┘   └──────────┘   └──────────┘             │
└──────────────────────────────────────────────────────────┘
```

---

## Estrutura de Arquivos do Projeto

```
cnpj-discovery/
├── docker-compose.yml               # Stack local completa
├── docker-compose.prod.yml          # Overrides para VPS
├── .env.example                     # Template de variáveis
├── .env                             # Variáveis locais (gitignored)
├── .gitignore
│
├── etl/                             # Motor de ingestão
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                      # CLI entrypoint (full-load / update / status)
│   ├── config.py                    # Settings via pydantic-settings
│   ├── downloader.py                # WebDAV listing + download com retry
│   ├── extractor.py                 # Streaming ZIP → CSV em memória
│   ├── transformer.py               # Parse, limpeza, normalização de tipos
│   ├── loader.py                    # COPY FROM STDIN bulk insert
│   ├── indexer.py                   # DROP/CREATE índices pós-carga
│   ├── updater.py                   # UPSERT incremental (ON CONFLICT)
│   ├── scheduler.py                 # APScheduler cron mensal
│   ├── notifier.py                  # Webhook Discord/Slack
│   ├── state.py                     # Tabela etl_state para checksum/modified_date
│   └── schemas/
│       ├── empresas.py              # Mapeamento de colunas CSV → DB
│       ├── estabelecimentos.py
│       ├── socios.py
│       └── dominios.py              # CNAE, municípios, naturezas, etc.
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                      # FastAPI app factory
│   ├── config.py
│   ├── database.py                  # asyncpg connection pool
│   ├── routers/
│   │   ├── prospecting.py           # GET /prospecting (busca com filtros)
│   │   ├── export.py                # GET /export/csv, /export/xlsx
│   │   └── status.py                # GET /status (ETL health)
│   ├── models/
│   │   ├── filters.py               # Pydantic: FilterParams
│   │   └── empresa.py               # Pydantic: EmpresaOut
│   └── services/
│       ├── query_builder.py         # SQL dinâmico seguro com keyset pagination
│       └── exporter.py              # Stream CSV/Excel sem carregar tudo na RAM
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/client.ts            # axios/fetch wrapper tipado
│       ├── components/
│       │   ├── FilterPanel.tsx      # Painel de filtros lateral
│       │   ├── ResultsTable.tsx     # Tabela virtual com infinite scroll
│       │   ├── ExportButton.tsx     # Botão exportar CSV
│       │   └── StatusBadge.tsx      # Status da última atualização ETL
│       └── pages/
│           ├── Prospecting.tsx      # Página principal
│           └── Dashboard.tsx        # Stats do banco (total registros, etc.)
│
├── db/
│   ├── migrations/
│   │   ├── 001_schema.sql           # Tabelas principais
│   │   ├── 002_domain_tables.sql    # Tabelas de domínio
│   │   └── 003_etl_state.sql        # Controle de estado ETL
│   └── seeds/
│       └── (vazio — dados vêm do ETL)
│
└── nginx/
    └── nginx.conf                   # Proxy: / → frontend, /api → fastapi
```

---

## Schema do Banco de Dados

### Tabelas Principais

```sql
-- Dados base da empresa (arquivo Empresas*.zip)
CREATE TABLE empresas (
    cnpj_basico       CHAR(8)      PRIMARY KEY,
    razao_social      TEXT         NOT NULL,
    natureza_juridica SMALLINT,
    qualificacao_resp SMALLINT,
    capital_social    NUMERIC(18,2),
    porte             SMALLINT,     -- 1=MEI, 2=ME, 3=EPP, 5=Demais
    ente_federativo   TEXT
);

-- Dados do estabelecimento (arquivo Estabelecimentos*.zip)
-- É aqui que ficam: CNPJ completo, contatos, endereço, situação
CREATE TABLE estabelecimentos (
    cnpj_basico         CHAR(8)      NOT NULL REFERENCES empresas(cnpj_basico),
    cnpj_ordem          CHAR(4)      NOT NULL,
    cnpj_dv             CHAR(2)      NOT NULL,
    matriz_filial        SMALLINT,    -- 1=Matriz, 2=Filial
    nome_fantasia        TEXT,
    situacao_cadastral   SMALLINT,    -- 2=Ativa, 3=Suspensa, 4=Inapta, 8=Baixada
    data_situacao        DATE,
    motivo_situacao      SMALLINT,
    cidade_exterior      TEXT,
    pais                 SMALLINT,
    data_inicio          DATE,
    cnae_principal       INT,
    cnae_secundarios     TEXT,        -- lista separada por vírgula, parseada após load
    tipo_logradouro      TEXT,
    logradouro           TEXT,
    numero               TEXT,
    complemento          TEXT,
    bairro               TEXT,
    cep                  CHAR(8),
    uf                   CHAR(2),
    municipio            INT,
    ddd1                 CHAR(4),
    telefone1            TEXT,
    ddd2                 CHAR(4),
    telefone2            TEXT,
    ddd_fax              CHAR(4),
    fax                  TEXT,
    email                TEXT,
    situacao_especial    TEXT,
    data_situacao_esp    DATE,
    PRIMARY KEY (cnpj_basico, cnpj_ordem, cnpj_dv)
);

-- Sócios (arquivo Socios*.zip)
CREATE TABLE socios (
    id                  BIGSERIAL    PRIMARY KEY,
    cnpj_basico         CHAR(8)      NOT NULL,
    identificador       SMALLINT,
    nome_socio          TEXT,
    cpf_cnpj_socio      TEXT,
    qualificacao        SMALLINT,
    data_entrada        DATE,
    pais                SMALLINT,
    repr_legal          TEXT,
    nome_repr           TEXT,
    qualificacao_repr   SMALLINT,
    faixa_etaria        SMALLINT
);

-- Simples Nacional
CREATE TABLE simples (
    cnpj_basico         CHAR(8)      PRIMARY KEY,
    opcao_simples       CHAR(1),
    data_opcao_simples  DATE,
    data_exc_simples    DATE,
    opcao_mei           CHAR(1),
    data_opcao_mei      DATE,
    data_exc_mei        DATE
);

-- Tabelas de domínio (lookup tables)
CREATE TABLE cnaes      (codigo INT PRIMARY KEY, descricao TEXT);
CREATE TABLE municipios (codigo INT PRIMARY KEY, descricao TEXT);
CREATE TABLE paises     (codigo INT PRIMARY KEY, descricao TEXT);
CREATE TABLE naturezas  (codigo INT PRIMARY KEY, descricao TEXT);
CREATE TABLE qualificacoes (codigo INT PRIMARY KEY, descricao TEXT);
CREATE TABLE motivos    (codigo INT PRIMARY KEY, descricao TEXT);

-- Controle de estado ETL
CREATE TABLE etl_state (
    arquivo         TEXT         PRIMARY KEY,
    last_modified   TIMESTAMPTZ,
    checksum_etag   TEXT,
    loaded_at       TIMESTAMPTZ,
    status          TEXT         -- 'pending', 'downloading', 'loading', 'done', 'error'
);
```

### Índices (criados APÓS a carga inicial)

```sql
-- Índices compostos para os filtros mais comuns
CREATE INDEX idx_estab_uf_cnae_sit      ON estabelecimentos (uf, cnae_principal, situacao_cadastral);
CREATE INDEX idx_estab_municipio_sit    ON estabelecimentos (municipio, situacao_cadastral);
CREATE INDEX idx_estab_cnae_porte       ON estabelecimentos (cnae_principal, situacao_cadastral);
CREATE INDEX idx_empresas_porte         ON empresas (porte);
CREATE INDEX idx_socios_cnpj            ON socios (cnpj_basico);

-- Full-Text Search para razão social e nome fantasia
CREATE INDEX idx_estab_fts_fantasia     ON estabelecimentos USING GIN (to_tsvector('portuguese', coalesce(nome_fantasia, '')));
CREATE INDEX idx_empresas_fts_razao     ON empresas USING GIN (to_tsvector('portuguese', razao_social));

-- Para keyset pagination
CREATE INDEX idx_estab_cursor           ON estabelecimentos (cnpj_basico, cnpj_ordem);
```

---

## Sobre os Dados da Receita Federal

### Problema do Certificado SSL

A URL `https://arquivos.receitafederal.gov.br/` usa certificados ICP-Brasil que não estão no bundle padrão do Python (`certifi`). A solução adotada é usar a **API WebDAV** do Nextcloud (a plataforma que hospeda os dados):

```
# Listagem via WebDAV PROPFIND (sem autenticação, share público)
WebDAV URL: https://arquivos.receitafederal.gov.br/public.php/webdav/
Username: gn672Ad4CF8N6TK   (o token do share)
Password: (vazio)
verify=False                 (certificado ICP-Brasil não reconhecido por certifi)
```

Isso permite:
1. Listar todos os arquivos ZIP com `PROPFIND` (retorna nome + `Last-Modified` + tamanho)
2. Fazer download direto de cada arquivo via `GET` na mesma URL + nome do arquivo
3. Detectar atualizações comparando `Last-Modified` com `etl_state`

> **Nota:** Se o token do share mudar, o script de scraping lê a URL principal para extrair o novo token do HTML. O token está no `href` dos links da página.

### Arquivos Disponíveis e Volume

| Arquivo                     | Registros aprox. | Tamanho ZIP |
|-----------------------------|-----------------|-------------|
| Empresas0..9.zip (10 files) | 60M registros   | ~3 GB total |
| Estabelecimentos0..9.zip    | 60M registros   | ~8 GB total |
| Socios0..9.zip              | 30M registros   | ~2 GB total |
| Simples.zip                 | 40M registros   | ~1 GB total |
| CNAE.zip                    | 1.3K registros  | < 1 MB      |
| Municipios.zip              | 5.6K registros  | < 1 MB      |
| Naturezas.zip, etc.         | < 100 registros | < 1 MB      |

> **Total de disco estimado:** ~35 GB no PostgreSQL após load completo

### Encoding e Formato

- **Encoding:** ISO-8859-1 (Latin-1) — Python abre com `encoding='latin-1'`
- **Delimitador:** ponto e vírgula `;`
- **Sem aspas** (exceto quando o campo contém `;`)
- **Sem header** nos arquivos — o schema é fixo e documentado pela RF

---

## FASE 1 — Fundação e Setup Local

### Task 1: Repositório e .gitignore

**Files:**
- Create: `/home/luife/projetos/cnpj-discovery/.gitignore`
- Create: `/home/luife/projetos/cnpj-discovery/.env.example`

- [ ] **Step 1: Inicializar git**

```bash
cd /home/luife/projetos/cnpj-discovery
git init
git branch -m main
```

- [ ] **Step 2: Criar .gitignore**

```gitignore
.env
__pycache__/
*.pyc
*.pyo
.venv/
node_modules/
dist/
*.zip
*.csv
data/
.DS_Store
```

- [ ] **Step 3: Criar .env.example**

```env
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=cnpj
POSTGRES_USER=cnpj_user
POSTGRES_PASSWORD=changeme

# Redis
REDIS_URL=redis://localhost:6379/0

# ETL
ETL_DATA_DIR=/tmp/cnpj_data
ETL_BATCH_SIZE=10000
ETL_WORKERS=4

# Notificações
DISCORD_WEBHOOK_URL=

# Receita Federal
RF_SHARE_TOKEN=gn672Ad4CF8N6TK
RF_WEBDAV_BASE=https://arquivos.receitafederal.gov.br/public.php/webdav/
```

- [ ] **Step 4: Commit inicial**

```bash
git add .gitignore .env.example
git commit -m "chore: project scaffold with gitignore and env template"
```

---

### Task 2: Docker Compose — Infraestrutura Base

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.prod.yml`

- [ ] **Step 1: Criar docker-compose.yml**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/migrations:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    shm_size: "512mb"        # evita OOM em sort operations grandes
    command: >
      postgres
        -c max_connections=200
        -c shared_buffers=2GB
        -c effective_cache_size=6GB
        -c maintenance_work_mem=512MB
        -c checkpoint_completion_target=0.9
        -c wal_buffers=64MB
        -c default_statistics_target=100
        -c random_page_cost=1.1
        -c effective_io_concurrency=200
        -c work_mem=64MB
        -c min_wal_size=1GB
        -c max_wal_size=4GB
        -c max_worker_processes=12
        -c max_parallel_workers_per_gather=6
        -c max_parallel_workers=12

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"

  api:
    build: ./api
    restart: unless-stopped
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "3000:3000"

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - api
      - frontend

volumes:
  pgdata:
```

- [ ] **Step 2: Criar docker-compose.prod.yml (overrides para VPS)**

```yaml
version: "3.9"

services:
  postgres:
    volumes:
      - /data/pgdata:/var/lib/postgresql/data
    # sem expose de porta em produção
    ports: []

  api:
    restart: always

  frontend:
    restart: always

  nginx:
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

- [ ] **Step 3: Criar nginx/nginx.conf**

```nginx
server {
    listen 80;

    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;    # exports podem demorar
    }

    location / {
        proxy_pass http://frontend:3000/;
        proxy_set_header Host $host;
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml nginx/
git commit -m "infra: add docker-compose stack with postgres, redis, api, frontend, nginx"
```

---

### Task 3: Migrations do Banco de Dados

**Files:**
- Create: `db/migrations/001_schema.sql`
- Create: `db/migrations/002_domain_tables.sql`
- Create: `db/migrations/003_etl_state.sql`

- [ ] **Step 1: Criar 001_schema.sql** (colar o schema definido na seção "Schema do Banco de Dados" acima, sem os índices)

- [ ] **Step 2: Criar 002_domain_tables.sql**

```sql
-- Executado após load dos arquivos de domínio pelo ETL
-- Tabelas já criadas no 001; este arquivo só adiciona constraints pós-load

ALTER TABLE estabelecimentos
    ADD CONSTRAINT fk_cnae
    FOREIGN KEY (cnae_principal) REFERENCES cnaes(codigo)
    NOT VALID;  -- NOT VALID = não valida registros existentes, só novos

ALTER TABLE estabelecimentos
    ADD CONSTRAINT fk_municipio
    FOREIGN KEY (municipio) REFERENCES municipios(codigo)
    NOT VALID;
```

- [ ] **Step 3: Criar 003_etl_state.sql** (colar a CREATE TABLE etl_state do schema)

- [ ] **Step 4: Subir PostgreSQL e testar migrations**

```bash
cp .env.example .env
# editar .env com senha local
docker compose up postgres -d
docker compose exec postgres psql -U cnpj_user -d cnpj -c "\dt"
```

Expected: lista com empresas, estabelecimentos, socios, simples, cnaes, municipios, paises, naturezas, qualificacoes, motivos, etl_state

- [ ] **Step 5: Commit**

```bash
git add db/
git commit -m "db: add initial schema migrations for cnpj dataset"
```

---

## FASE 2 — Motor de Ingestão ETL

### Task 4: Setup do Ambiente Python ETL

**Files:**
- Create: `etl/requirements.txt`
- Create: `etl/Dockerfile`
- Create: `etl/config.py`

- [ ] **Step 1: Criar etl/requirements.txt**

```txt
polars==0.20.31
psycopg2-binary==2.9.9
httpx==0.27.0
pydantic-settings==2.2.1
tqdm==4.66.4
loguru==0.7.2
apscheduler==3.10.4
celery==5.4.0
redis==5.0.4
requests==2.32.3
webdavclient3==3.14.6
tenacity==8.3.0
python-dotenv==1.0.1
```

- [ ] **Step 2: Criar etl/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cnpj"
    postgres_user: str = "cnpj_user"
    postgres_password: str

    redis_url: str = "redis://localhost:6379/0"
    etl_data_dir: str = "/tmp/cnpj_data"
    etl_batch_size: int = 10_000
    etl_workers: int = 4

    discord_webhook_url: str = ""
    rf_share_token: str = "gn672Ad4CF8N6TK"
    rf_webdav_base: str = "https://arquivos.receitafederal.gov.br/public.php/webdav/"

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Criar etl/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py", "--help"]
```

- [ ] **Step 4: Commit**

```bash
git add etl/
git commit -m "etl: python environment setup with polars, psycopg2, httpx"
```

---

### Task 5: Downloader — Listagem WebDAV e Download com Retry

**Files:**
- Create: `etl/downloader.py`

- [ ] **Step 1: Escrever teste para listagem WebDAV**

```python
# etl/test_downloader.py
import pytest
from unittest.mock import patch, MagicMock
from downloader import list_rf_files, RFFile

def test_list_rf_files_returns_rf_files():
    mock_response = MagicMock()
    mock_response.status_code = 207
    mock_response.text = """<?xml version="1.0"?>
    <d:multistatus xmlns:d="DAV:">
      <d:response>
        <d:href>/public.php/webdav/Empresas0.zip</d:href>
        <d:propstat>
          <d:prop>
            <d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>
            <d:getcontentlength>123456789</d:getcontentlength>
          </d:prop>
        </d:propstat>
      </d:response>
    </d:multistatus>"""

    with patch("httpx.Client.request", return_value=mock_response):
        files = list_rf_files()

    assert len(files) == 1
    assert files[0].name == "Empresas0.zip"
    assert files[0].size == 123456789
```

- [ ] **Step 2: Rodar teste para verificar que falha**

```bash
cd etl && python -m pytest test_downloader.py -v
```

Expected: FAIL — `ImportError: cannot import name 'list_rf_files'`

- [ ] **Step 3: Implementar etl/downloader.py**

```python
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

DAV_NS = "DAV:"

@dataclass
class RFFile:
    name: str
    last_modified: datetime
    size: int
    href: str

def list_rf_files() -> list[RFFile]:
    """Lista arquivos disponíveis via WebDAV PROPFIND."""
    with httpx.Client(verify=False, timeout=30) as client:
        resp = client.request(
            "PROPFIND",
            settings.rf_webdav_base,
            auth=(settings.rf_share_token, ""),
            headers={"Depth": "1"},
        )
    resp.raise_for_status()
    return _parse_propfind(resp.text)

def _parse_propfind(xml_text: str) -> list[RFFile]:
    root = ET.fromstring(xml_text)
    files = []
    for response in root.findall(f"{{{DAV_NS}}}response"):
        href = response.findtext(f"{{{DAV_NS}}}href", "")
        name = href.rstrip("/").split("/")[-1]
        if not name.endswith(".zip"):
            continue
        props = response.find(f".//{{{DAV_NS}}}prop")
        lm_str = props.findtext(f"{{{DAV_NS}}}getlastmodified", "")
        size_str = props.findtext(f"{{{DAV_NS}}}getcontentlength", "0")
        files.append(RFFile(
            name=name,
            last_modified=parsedate_to_datetime(lm_str),
            size=int(size_str),
            href=href,
        ))
    return files

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=60))
def download_file(rf_file: RFFile, dest_dir: str) -> Path:
    """Download de um arquivo ZIP com retry exponencial."""
    dest = Path(dest_dir) / rf_file.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = settings.rf_webdav_base + rf_file.name

    logger.info(f"Downloading {rf_file.name} ({rf_file.size / 1e9:.2f} GB)...")
    with httpx.stream("GET", url, auth=(settings.rf_share_token, ""), verify=False, timeout=None) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):  # 1 MB chunks
                f.write(chunk)
    logger.success(f"Downloaded {rf_file.name} → {dest}")
    return dest
```

- [ ] **Step 4: Rodar teste**

```bash
python -m pytest test_downloader.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add etl/downloader.py etl/test_downloader.py
git commit -m "etl: add WebDAV file listing and streaming downloader with retry"
```

---

### Task 6: Schemas — Mapeamento CSV → Colunas do Banco

**Files:**
- Create: `etl/schemas/empresas.py`
- Create: `etl/schemas/estabelecimentos.py`
- Create: `etl/schemas/socios.py`
- Create: `etl/schemas/dominios.py`

- [ ] **Step 1: Criar etl/schemas/empresas.py**

```python
from dataclasses import dataclass

TABLE = "empresas"
COLUMNS = [
    "cnpj_basico",
    "razao_social",
    "natureza_juridica",
    "qualificacao_resp",
    "capital_social",
    "porte",
    "ente_federativo",
]

# Polars dtype para parsing inicial (tudo str, depois cast)
POLARS_SCHEMA = {
    "cnpj_basico":       "Utf8",
    "razao_social":      "Utf8",
    "natureza_juridica": "Utf8",
    "qualificacao_resp": "Utf8",
    "capital_social":    "Utf8",
    "porte":             "Utf8",
    "ente_federativo":   "Utf8",
}
```

- [ ] **Step 2: Criar etl/schemas/estabelecimentos.py** — mesma estrutura com as 29 colunas do layout RF

```python
TABLE = "estabelecimentos"
COLUMNS = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial",
    "nome_fantasia", "situacao_cadastral", "data_situacao",
    "motivo_situacao", "cidade_exterior", "pais", "data_inicio",
    "cnae_principal", "cnae_secundarios", "tipo_logradouro",
    "logradouro", "numero", "complemento", "bairro", "cep",
    "uf", "municipio", "ddd1", "telefone1", "ddd2", "telefone2",
    "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_esp",
]
POLARS_SCHEMA = {col: "Utf8" for col in COLUMNS}
```

- [ ] **Step 3: Criar etl/schemas/socios.py e dominios.py** com a mesma estrutura

- [ ] **Step 4: Commit**

```bash
git add etl/schemas/
git commit -m "etl: add CSV column schemas for all RF file types"
```

---

### Task 7: Transformer — Parse, Limpeza e Normalização

**Files:**
- Create: `etl/transformer.py`

- [ ] **Step 1: Escrever teste**

```python
# etl/test_transformer.py
import polars as pl
from transformer import clean_cnpj, parse_capital_social, parse_date_rf

def test_clean_cnpj_pads_with_zeros():
    assert clean_cnpj("1234567") == "01234567"

def test_parse_capital_social_replaces_comma():
    assert parse_capital_social("1.234,56") == 1234.56

def test_parse_date_rf_valid():
    assert str(parse_date_rf("20230115")) == "2023-01-15"

def test_parse_date_rf_zeroed_returns_none():
    assert parse_date_rf("00000000") is None
```

- [ ] **Step 2: Rodar para verificar falha**

```bash
python -m pytest test_transformer.py -v
```

- [ ] **Step 3: Implementar etl/transformer.py**

```python
from datetime import date
from typing import Optional
import polars as pl
from loguru import logger


def clean_cnpj(value: str) -> str:
    return value.strip().zfill(8)


def parse_capital_social(value: str) -> Optional[float]:
    if not value or value.strip() == "":
        return None
    try:
        return float(value.strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_date_rf(value: str) -> Optional[date]:
    v = value.strip() if value else ""
    if not v or v == "00000000":
        return None
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    except (ValueError, IndexError):
        return None


def transform_empresas_df(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df
        .with_columns([
            pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
            pl.col("razao_social").str.strip_chars(),
            pl.col("natureza_juridica").str.strip_chars().cast(pl.Int16, strict=False),
            pl.col("qualificacao_resp").str.strip_chars().cast(pl.Int16, strict=False),
            pl.col("capital_social")
              .str.strip_chars()
              .str.replace_all(r"\.", "")
              .str.replace(",", ".")
              .cast(pl.Float64, strict=False),
            pl.col("porte").str.strip_chars().cast(pl.Int16, strict=False),
            pl.col("ente_federativo").str.strip_chars(),
        ])
    )


def transform_estabelecimentos_df(df: pl.DataFrame) -> pl.DataFrame:
    date_cols = ["data_situacao", "data_inicio", "data_situacao_esp"]
    int16_cols = ["matriz_filial", "situacao_cadastral", "motivo_situacao",
                  "pais", "cnae_principal", "municipio"]
    result = df.with_columns([
        pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
        pl.col("cnpj_ordem").str.strip_chars(),
        pl.col("cnpj_dv").str.strip_chars(),
        pl.col("nome_fantasia").str.strip_chars(),
        pl.col("email").str.strip_chars().str.to_lowercase(),
        pl.col("cep").str.strip_chars().str.replace_all(r"\D", ""),
        *[pl.col(c).str.strip_chars().cast(pl.Int16, strict=False) for c in int16_cols],
    ])
    for col in date_cols:
        result = result.with_columns(
            pl.col(col).str.strip_chars()
              .str.replace("00000000", "")
              .str.strptime(pl.Date, "%Y%m%d", strict=False)
        )
    return result
```

- [ ] **Step 4: Rodar testes**

```bash
python -m pytest test_transformer.py -v
```

Expected: 4 PASSes

- [ ] **Step 5: Commit**

```bash
git add etl/transformer.py etl/test_transformer.py
git commit -m "etl: add data transformer with cleaning and type normalization"
```

---

### Task 8: Extractor — Streaming ZIP → Polars DataFrame

**Files:**
- Create: `etl/extractor.py`

- [ ] **Step 1: Implementar etl/extractor.py**

```python
import io
import zipfile
from pathlib import Path
from typing import Generator

import polars as pl
from loguru import logger


def stream_csv_from_zip(
    zip_path: Path,
    schema: dict[str, str],
    batch_size: int = 50_000,
) -> Generator[pl.DataFrame, None, None]:
    """
    Abre o ZIP e lê o CSV interno linha por linha em batches.
    Nunca carrega o CSV inteiro na memória.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv") or "." not in n]
        if not csv_names:
            raise ValueError(f"Nenhum CSV encontrado em {zip_path}")
        csv_name = csv_names[0]
        logger.info(f"Extraindo {csv_name} de {zip_path.name}")

        with zf.open(csv_name) as raw:
            buffer: list[bytes] = []
            header = ";".join(schema.keys()).encode("latin-1") + b"\n"

            for line in raw:
                buffer.append(line)
                if len(buffer) >= batch_size:
                    yield _parse_batch(header, buffer, schema)
                    buffer.clear()

            if buffer:
                yield _parse_batch(header, buffer, schema)


def _parse_batch(header: bytes, lines: list[bytes], schema: dict[str, str]) -> pl.DataFrame:
    raw = header + b"".join(lines)
    return pl.read_csv(
        io.BytesIO(raw),
        separator=";",
        encoding="latin-1",
        infer_schema_length=0,   # tudo como Utf8 inicialmente
        ignore_errors=True,
        truncate_ragged_lines=True,
        new_columns=list(schema.keys()),
        has_header=True,
    )
```

- [ ] **Step 2: Testar manualmente com um ZIP pequeno (dominios)**

```bash
# Baixar CNAE.zip para teste
python -c "
from downloader import list_rf_files, download_file
files = [f for f in list_rf_files() if 'CNAE' in f.name]
if files: download_file(files[0], '/tmp/cnpj_data')
"
```

- [ ] **Step 3: Commit**

```bash
git add etl/extractor.py
git commit -m "etl: add streaming ZIP extractor with batched Polars reads"
```

---

### Task 9: Loader — Bulk Insert via PostgreSQL COPY

**Files:**
- Create: `etl/loader.py`

> A técnica de `COPY FROM STDIN` é 10-50x mais rápida que `INSERT` em lote para volumes acima de 1M registros.

- [ ] **Step 1: Implementar etl/loader.py**

```python
import io
import psycopg2
import psycopg2.extras
import polars as pl
from loguru import logger
from config import settings


def get_conn():
    return psycopg2.connect(settings.dsn)


def disable_indexes_and_triggers(conn, table: str):
    """Desativa triggers e índices durante carga inicial para máxima velocidade."""
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER ALL;")
    conn.commit()


def enable_indexes_and_triggers(conn, table: str):
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER ALL;")
    conn.commit()


def copy_df_to_table(conn, df: pl.DataFrame, table: str, columns: list[str]) -> int:
    """
    Usa COPY FROM STDIN para inserir um DataFrame Polars no PostgreSQL.
    Retorna número de linhas inseridas.
    """
    buf = io.StringIO()
    # Seleciona e ordena colunas conforme o schema da tabela
    subset = [c for c in columns if c in df.columns]
    df.select(subset).write_csv(buf, separator="\t", null_value="\\N", include_header=False)
    buf.seek(0)

    with conn.cursor() as cur:
        cur.copy_from(buf, table, columns=subset, sep="\t", null="\\N")
    conn.commit()
    return len(df)


def upsert_df_to_table(
    conn,
    df: pl.DataFrame,
    table: str,
    columns: list[str],
    conflict_columns: list[str],
) -> int:
    """
    INSERT ... ON CONFLICT DO UPDATE para carga incremental.
    Usa execute_values para batch insert com upsert.
    """
    update_cols = [c for c in columns if c not in conflict_columns]
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    conflict_clause = ", ".join(conflict_columns)

    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT ({conflict_clause}) DO UPDATE SET {update_clause}"
    )

    rows = [tuple(row) for row in df.select(columns).iter_rows()]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=5000)
    conn.commit()
    return len(rows)
```

- [ ] **Step 2: Testar loader com dados de domínio reais**

```bash
python -c "
import psycopg2
from config import settings
conn = psycopg2.connect(settings.dsn)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM cnaes')
print(cur.fetchone())
"
```

- [ ] **Step 3: Commit**

```bash
git add etl/loader.py
git commit -m "etl: add COPY bulk loader and upsert loader for incremental updates"
```

---

### Task 10: Indexer — Criação de Índices Pós-Carga

**Files:**
- Create: `etl/indexer.py`

- [ ] **Step 1: Implementar etl/indexer.py**

```python
import psycopg2
from loguru import logger
from loader import get_conn

INDEXES = [
    ("idx_estab_uf_cnae_sit",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_uf_cnae_sit "
     "ON estabelecimentos (uf, cnae_principal, situacao_cadastral)"),

    ("idx_estab_municipio_sit",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_municipio_sit "
     "ON estabelecimentos (municipio, situacao_cadastral)"),

    ("idx_estab_cnae_sit",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_cnae_sit "
     "ON estabelecimentos (cnae_principal, situacao_cadastral)"),

    ("idx_empresas_porte",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_porte "
     "ON empresas (porte)"),

    ("idx_socios_cnpj",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_socios_cnpj "
     "ON socios (cnpj_basico)"),

    ("idx_estab_cursor",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_cursor "
     "ON estabelecimentos (cnpj_basico, cnpj_ordem)"),

    ("idx_estab_fts_fantasia",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_fts_fantasia "
     "ON estabelecimentos USING GIN (to_tsvector('portuguese', coalesce(nome_fantasia, '')))"),

    ("idx_empresas_fts_razao",
     "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_fts_razao "
     "ON empresas USING GIN (to_tsvector('portuguese', razao_social))"),
]


def drop_all_indexes(conn):
    """Dropa índices (exceto PKs) antes da carga inicial para velocidade máxima."""
    idx_names = [name for name, _ in INDEXES]
    with conn.cursor() as cur:
        for name in idx_names:
            cur.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()
    logger.info("Índices removidos para carga")


def create_all_indexes(conn):
    """Recria todos os índices após a carga completa. CONCURRENTLY não bloqueia leitura."""
    with conn.cursor() as cur:
        for name, sql in INDEXES:
            logger.info(f"Criando índice {name}...")
            cur.execute(sql)
            conn.commit()  # CONCURRENTLY exige autocommit ou commit por índice
    logger.success("Todos os índices criados")
```

- [ ] **Step 2: Commit**

```bash
git add etl/indexer.py
git commit -m "etl: add post-load index builder with CONCURRENTLY strategy"
```

---

### Task 11: State Manager e Orquestrador Principal

**Files:**
- Create: `etl/state.py`
- Create: `etl/main.py`

- [ ] **Step 1: Implementar etl/state.py**

```python
from datetime import datetime, timezone
import psycopg2
from loader import get_conn


def get_file_state(conn, filename: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_modified, checksum_etag, loaded_at, status "
            "FROM etl_state WHERE arquivo = %s",
            (filename,)
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"last_modified": row[0], "etag": row[1], "loaded_at": row[2], "status": row[3]}


def set_file_state(conn, filename: str, last_modified: datetime, status: str, etag: str = ""):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO etl_state (arquivo, last_modified, checksum_etag, loaded_at, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (arquivo) DO UPDATE SET
                last_modified = EXCLUDED.last_modified,
                checksum_etag = EXCLUDED.checksum_etag,
                loaded_at = EXCLUDED.loaded_at,
                status = EXCLUDED.status
        """, (filename, last_modified, etag, datetime.now(timezone.utc), status))
    conn.commit()


def needs_update(conn, rf_file) -> bool:
    state = get_file_state(conn, rf_file.name)
    if not state or state["status"] != "done":
        return True
    return rf_file.last_modified > state["last_modified"]
```

- [ ] **Step 2: Implementar etl/main.py (CLI com typer ou argparse)**

```python
import argparse
import os
from pathlib import Path

from loguru import logger
from config import settings
from downloader import list_rf_files, download_file
from extractor import stream_csv_from_zip
from loader import get_conn, copy_df_to_table, disable_indexes_and_triggers, enable_indexes_and_triggers
from indexer import drop_all_indexes, create_all_indexes
from state import needs_update, set_file_state
from transformer import transform_empresas_df, transform_estabelecimentos_df
from schemas.empresas import TABLE as EMP_TABLE, COLUMNS as EMP_COLS
from schemas.estabelecimentos import TABLE as EST_TABLE, COLUMNS as EST_COLS

SCHEMA_MAP = {
    "Empresas": (EMP_TABLE, EMP_COLS, transform_empresas_df),
    "Estabelecimentos": (EST_TABLE, EST_COLS, transform_estabelecimentos_df),
}


def full_load():
    conn = get_conn()
    files = list_rf_files()
    drop_all_indexes(conn)

    for rf_file in files:
        if not needs_update(conn, rf_file):
            logger.info(f"Pulando {rf_file.name} — já processado")
            continue

        set_file_state(conn, rf_file.name, rf_file.last_modified, "downloading")
        zip_path = download_file(rf_file, settings.etl_data_dir)
        set_file_state(conn, rf_file.name, rf_file.last_modified, "loading")

        for prefix, (table, columns, transform_fn) in SCHEMA_MAP.items():
            if rf_file.name.startswith(prefix):
                from schemas.empresas import POLARS_SCHEMA
                disable_indexes_and_triggers(conn, table)
                total = 0
                for batch_df in stream_csv_from_zip(zip_path, POLARS_SCHEMA):
                    clean_df = transform_fn(batch_df)
                    total += copy_df_to_table(conn, clean_df, table, columns)
                enable_indexes_and_triggers(conn, table)
                logger.success(f"{rf_file.name}: {total} registros carregados em {table}")

        zip_path.unlink()  # apaga ZIP após processar
        set_file_state(conn, rf_file.name, rf_file.last_modified, "done")

    create_all_indexes(conn)
    conn.close()
    logger.success("Full load concluído!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["full-load", "update", "status"])
    args = parser.parse_args()

    if args.command == "full-load":
        full_load()
```

- [ ] **Step 3: Testar com arquivos de domínio (menores, para validar o pipeline)**

```bash
cd etl && python main.py full-load 2>&1 | head -50
```

- [ ] **Step 4: Commit**

```bash
git add etl/state.py etl/main.py
git commit -m "etl: add ETL orchestrator with state management and full-load pipeline"
```

---

## FASE 3 — API FastAPI

### Task 12: Setup FastAPI com asyncpg

**Files:**
- Create: `api/requirements.txt`
- Create: `api/main.py`
- Create: `api/database.py`
- Create: `api/config.py`
- Create: `api/Dockerfile`

- [ ] **Step 1: Criar api/requirements.txt**

```txt
fastapi==0.111.0
uvicorn[standard]==0.30.1
asyncpg==0.29.0
pydantic==2.7.1
pydantic-settings==2.2.1
python-multipart==0.0.9
openpyxl==3.1.2
```

- [ ] **Step 2: Criar api/database.py**

```python
import asyncpg
from config import settings

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.dsn,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
```

- [ ] **Step 3: Criar api/main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import get_pool, close_pool
from routers import prospecting, export, status

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()

app = FastAPI(title="CNPJ Discovery API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prospecting.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(status.router, prefix="/api")
```

- [ ] **Step 4: Commit**

```bash
git add api/
git commit -m "api: fastapi skeleton with asyncpg pool and CORS"
```

---

### Task 13: Query Builder com Keyset Pagination e Filtros Dinâmicos

**Files:**
- Create: `api/models/filters.py`
- Create: `api/models/empresa.py`
- Create: `api/services/query_builder.py`

- [ ] **Step 1: Criar api/models/filters.py**

```python
from pydantic import BaseModel
from typing import Optional

class ProspectingFilters(BaseModel):
    uf: Optional[str] = None
    municipio: Optional[int] = None
    cnae_principal: Optional[int] = None
    situacao_cadastral: Optional[int] = 2        # default: ativas
    porte: Optional[int] = None                  # 1=MEI, 2=ME, 3=EPP, 5=Demais
    excluir_mei: bool = False
    capital_social_min: Optional[float] = None
    capital_social_max: Optional[float] = None
    busca_razao: Optional[str] = None            # full-text search
    # Keyset pagination
    cursor_cnpj_basico: Optional[str] = None
    cursor_cnpj_ordem: Optional[str] = None
    limit: int = 50
```

- [ ] **Step 2: Criar api/models/empresa.py**

```python
from pydantic import BaseModel
from typing import Optional
from datetime import date

class EmpresaOut(BaseModel):
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    cnpj_completo: str
    razao_social: str
    nome_fantasia: Optional[str]
    situacao_cadastral: Optional[int]
    cnae_principal: Optional[int]
    cnae_descricao: Optional[str]
    uf: Optional[str]
    municipio: Optional[int]
    municipio_descricao: Optional[str]
    email: Optional[str]
    telefone1: Optional[str]
    porte: Optional[int]
    capital_social: Optional[float]
    data_inicio: Optional[date]
```

- [ ] **Step 3: Criar api/services/query_builder.py**

```python
from models.filters import ProspectingFilters

def build_prospecting_query(f: ProspectingFilters) -> tuple[str, list]:
    """
    Constrói SQL dinâmico com keyset pagination seguro (sem f-string com user input).
    Retorna (sql, params).
    """
    conditions = []
    params: list = []
    p = 1  # contador de placeholders $1, $2...

    base_sql = """
        SELECT
            e.cnpj_basico, est.cnpj_ordem, est.cnpj_dv,
            e.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
            e.razao_social, est.nome_fantasia,
            est.situacao_cadastral, est.cnae_principal,
            c.descricao AS cnae_descricao,
            est.uf, est.municipio, m.descricao AS municipio_descricao,
            est.email,
            est.ddd1 || est.telefone1 AS telefone1,
            e.porte, e.capital_social, est.data_inicio
        FROM estabelecimentos est
        JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
        LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
        LEFT JOIN municipios m ON m.codigo = est.municipio
    """

    if f.situacao_cadastral is not None:
        conditions.append(f"est.situacao_cadastral = ${p}")
        params.append(f.situacao_cadastral); p += 1

    if f.uf:
        conditions.append(f"est.uf = ${p}")
        params.append(f.uf.upper()); p += 1

    if f.municipio:
        conditions.append(f"est.municipio = ${p}")
        params.append(f.municipio); p += 1

    if f.cnae_principal:
        conditions.append(f"est.cnae_principal = ${p}")
        params.append(f.cnae_principal); p += 1

    if f.porte:
        conditions.append(f"e.porte = ${p}")
        params.append(f.porte); p += 1

    if f.excluir_mei:
        conditions.append("e.porte != 1")

    if f.capital_social_min is not None:
        conditions.append(f"e.capital_social >= ${p}")
        params.append(f.capital_social_min); p += 1

    if f.capital_social_max is not None:
        conditions.append(f"e.capital_social <= ${p}")
        params.append(f.capital_social_max); p += 1

    if f.busca_razao:
        conditions.append(
            f"(to_tsvector('portuguese', e.razao_social) @@ plainto_tsquery('portuguese', ${p}) "
            f"OR to_tsvector('portuguese', coalesce(est.nome_fantasia,'')) @@ plainto_tsquery('portuguese', ${p}))"
        )
        params.append(f.busca_razao); p += 1

    # Keyset pagination — evita OFFSET lento em páginas 500+
    if f.cursor_cnpj_basico and f.cursor_cnpj_ordem:
        conditions.append(f"(est.cnpj_basico, est.cnpj_ordem) > (${p}, ${p+1})")
        params.extend([f.cursor_cnpj_basico, f.cursor_cnpj_ordem]); p += 2

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"{base_sql} {where} ORDER BY est.cnpj_basico, est.cnpj_ordem LIMIT {f.limit}"
    return sql, params
```

- [ ] **Step 4: Commit**

```bash
git add api/models/ api/services/query_builder.py
git commit -m "api: add dynamic query builder with keyset pagination and full-text search"
```

---

### Task 14: Endpoints de Prospecção e Export

**Files:**
- Create: `api/routers/prospecting.py`
- Create: `api/routers/export.py`
- Create: `api/routers/status.py`
- Create: `api/services/exporter.py`

- [ ] **Step 1: Criar api/routers/prospecting.py**

```python
from fastapi import APIRouter, Depends
from database import get_pool
from models.filters import ProspectingFilters
from models.empresa import EmpresaOut
from services.query_builder import build_prospecting_query

router = APIRouter()

@router.get("/prospecting", response_model=list[EmpresaOut])
async def search_empresas(filters: ProspectingFilters = Depends()):
    pool = await get_pool()
    sql, params = build_prospecting_query(filters)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Criar api/routers/export.py**

```python
import csv
import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from database import get_pool
from models.filters import ProspectingFilters
from services.query_builder import build_prospecting_query

router = APIRouter()

@router.get("/export/csv")
async def export_csv(filters: ProspectingFilters = Depends()):
    filters.limit = 100_000  # limite export
    pool = await get_pool()
    sql, params = build_prospecting_query(filters)

    async def generate():
        async with pool.acquire() as conn:
            async with conn.transaction():
                cur = await conn.cursor(sql, *params)
                headers = None
                while True:
                    rows = await cur.fetch(1000)
                    if not rows:
                        break
                    if headers is None:
                        buf = io.StringIO()
                        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                        writer.writeheader()
                        headers = True
                    else:
                        buf = io.StringIO()
                        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                    for row in rows:
                        writer.writerow(dict(row))
                    yield buf.getvalue().encode("utf-8-sig")  # BOM para Excel

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
```

- [ ] **Step 3: Criar api/routers/status.py**

```python
from fastapi import APIRouter
from database import get_pool

router = APIRouter()

@router.get("/status")
async def get_status():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_empresas = await conn.fetchval("SELECT COUNT(*) FROM empresas")
        total_estabelecimentos = await conn.fetchval("SELECT COUNT(*) FROM estabelecimentos")
        etl_states = await conn.fetch(
            "SELECT arquivo, status, loaded_at FROM etl_state ORDER BY loaded_at DESC LIMIT 20"
        )
    return {
        "total_empresas": total_empresas,
        "total_estabelecimentos": total_estabelecimentos,
        "etl_files": [dict(r) for r in etl_states],
    }
```

- [ ] **Step 4: Testar API localmente**

```bash
cd api && uvicorn main:app --reload --port 8000
# Em outro terminal:
curl "http://localhost:8000/api/status"
curl "http://localhost:8000/api/prospecting?uf=SP&situacao_cadastral=2&limit=5"
```

- [ ] **Step 5: Commit**

```bash
git add api/routers/
git commit -m "api: add prospecting search, CSV streaming export, and status endpoints"
```

---

## FASE 4 — Frontend React

### Task 15: Setup Frontend React + Vite + TailwindCSS

**Files:**
- Create: `frontend/` (via npm create)

- [ ] **Step 1: Criar projeto React**

```bash
cd /home/luife/projetos/cnpj-discovery
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install @tanstack/react-table @tanstack/react-query axios
npm install @radix-ui/react-select @radix-ui/react-checkbox lucide-react
npm install clsx tailwind-merge
```

- [ ] **Step 2: Configurar tailwind.config.ts**

```typescript
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 3: Criar frontend/src/api/client.ts**

```typescript
import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

export interface EmpresaOut {
  cnpj_completo: string;
  razao_social: string;
  nome_fantasia: string | null;
  situacao_cadastral: number | null;
  cnae_principal: number | null;
  cnae_descricao: string | null;
  uf: string | null;
  municipio_descricao: string | null;
  email: string | null;
  telefone1: string | null;
  porte: number | null;
  capital_social: number | null;
}

export interface Filters {
  uf?: string;
  municipio?: number;
  cnae_principal?: number;
  situacao_cadastral?: number;
  porte?: number;
  excluir_mei?: boolean;
  capital_social_min?: number;
  capital_social_max?: number;
  busca_razao?: string;
  cursor_cnpj_basico?: string;
  cursor_cnpj_ordem?: string;
  limit?: number;
}

export const searchEmpresas = (filters: Filters) =>
  api.get<EmpresaOut[]>("/prospecting", { params: filters }).then(r => r.data);

export const getStatus = () =>
  api.get("/status").then(r => r.data);

export const exportCsvUrl = (filters: Filters) => {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)])
  );
  return `${api.defaults.baseURL}/export/csv?${params}`;
};
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "frontend: react+vite+typescript+tailwind scaffold with api client"
```

---

### Task 16: Componentes FilterPanel e ResultsTable

**Files:**
- Create: `frontend/src/components/FilterPanel.tsx`
- Create: `frontend/src/components/ResultsTable.tsx`
- Create: `frontend/src/pages/Prospecting.tsx`

- [ ] **Step 1: Criar FilterPanel.tsx**

```tsx
import { useState } from "react";
import { Filters } from "../api/client";

interface Props {
  onSearch: (f: Filters) => void;
  loading: boolean;
}

const PORTES = [
  { value: "", label: "Todos" },
  { value: "1", label: "MEI" },
  { value: "2", label: "ME" },
  { value: "3", label: "EPP" },
  { value: "5", label: "Demais" },
];

const UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG",
              "MS","MT","PA","PB","PE","PI","PR","RJ","RN","RO","RR",
              "RS","SC","SE","SP","TO"];

export function FilterPanel({ onSearch, loading }: Props) {
  const [filters, setFilters] = useState<Filters>({ situacao_cadastral: 2, limit: 50 });

  const set = (key: keyof Filters, value: unknown) =>
    setFilters(prev => ({ ...prev, [key]: value || undefined }));

  return (
    <aside className="w-72 shrink-0 bg-white border-r p-4 flex flex-col gap-4">
      <h2 className="font-semibold text-lg">Filtros</h2>

      <label className="flex flex-col gap-1 text-sm">
        Busca (Razão/Fantasia)
        <input className="border rounded px-2 py-1"
          onChange={e => set("busca_razao", e.target.value)} />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        UF
        <select className="border rounded px-2 py-1"
          onChange={e => set("uf", e.target.value)}>
          <option value="">Todos</option>
          {UFS.map(uf => <option key={uf} value={uf}>{uf}</option>)}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        CNAE Principal
        <input type="number" className="border rounded px-2 py-1"
          placeholder="ex: 6201500"
          onChange={e => set("cnae_principal", Number(e.target.value))} />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Porte
        <select className="border rounded px-2 py-1"
          onChange={e => set("porte", Number(e.target.value))}>
          {PORTES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </label>

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox"
          onChange={e => set("excluir_mei", e.target.checked)} />
        Excluir MEI
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Capital Social Mínimo (R$)
        <input type="number" className="border rounded px-2 py-1"
          onChange={e => set("capital_social_min", Number(e.target.value))} />
      </label>

      <button
        className="mt-auto bg-blue-600 text-white rounded px-4 py-2 hover:bg-blue-700 disabled:opacity-50"
        onClick={() => onSearch({ ...filters, cursor_cnpj_basico: undefined })}
        disabled={loading}
      >
        {loading ? "Buscando..." : "Buscar"}
      </button>
    </aside>
  );
}
```

- [ ] **Step 2: Criar ResultsTable.tsx**

```tsx
import { EmpresaOut } from "../api/client";

interface Props {
  data: EmpresaOut[];
  onLoadMore?: () => void;
  hasMore: boolean;
}

export function ResultsTable({ data, onLoadMore, hasMore }: Props) {
  if (!data.length) return <p className="p-8 text-gray-400">Nenhum resultado.</p>;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="overflow-auto flex-1">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {["CNPJ","Razão Social","Fantasia","UF","Município","CNAE","Telefone","E-mail","Porte","Capital Social"].map(h => (
                <th key={h} className="px-3 py-2 text-left font-medium text-gray-600 border-b whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map(e => (
              <tr key={e.cnpj_completo} className="hover:bg-gray-50 border-b">
                <td className="px-3 py-2 font-mono">{e.cnpj_completo}</td>
                <td className="px-3 py-2 max-w-xs truncate">{e.razao_social}</td>
                <td className="px-3 py-2 max-w-xs truncate">{e.nome_fantasia || "-"}</td>
                <td className="px-3 py-2">{e.uf}</td>
                <td className="px-3 py-2">{e.municipio_descricao || "-"}</td>
                <td className="px-3 py-2">{e.cnae_descricao || e.cnae_principal || "-"}</td>
                <td className="px-3 py-2">{e.telefone1 || "-"}</td>
                <td className="px-3 py-2 max-w-xs truncate">{e.email || "-"}</td>
                <td className="px-3 py-2">{e.porte}</td>
                <td className="px-3 py-2">{e.capital_social?.toLocaleString("pt-BR", {style:"currency",currency:"BRL"}) || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <div className="p-3 border-t flex justify-center">
          <button className="text-blue-600 hover:underline" onClick={onLoadMore}>
            Carregar mais →
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Criar Prospecting.tsx (página principal)**

```tsx
import { useState, useCallback } from "react";
import { FilterPanel } from "../components/FilterPanel";
import { ResultsTable } from "../components/ResultsTable";
import { EmpresaOut, Filters, searchEmpresas, exportCsvUrl } from "../api/client";

export function Prospecting() {
  const [results, setResults] = useState<EmpresaOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentFilters, setCurrentFilters] = useState<Filters>({});
  const [lastItem, setLastItem] = useState<EmpresaOut | null>(null);

  const search = useCallback(async (filters: Filters) => {
    setLoading(true);
    setCurrentFilters(filters);
    setLastItem(null);
    try {
      const data = await searchEmpresas(filters);
      setResults(data);
      setLastItem(data[data.length - 1] ?? null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = async () => {
    if (!lastItem) return;
    const [basico, ordem] = [
      lastItem.cnpj_completo.slice(0, 8),
      lastItem.cnpj_completo.slice(8, 12),
    ];
    const more = await searchEmpresas({
      ...currentFilters,
      cursor_cnpj_basico: basico,
      cursor_cnpj_ordem: ordem,
    });
    setResults(prev => [...prev, ...more]);
    setLastItem(more[more.length - 1] ?? null);
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <FilterPanel onSearch={search} loading={loading} />
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
          <span className="text-gray-600 text-sm">{results.length} resultados</span>
          {results.length > 0 && (
            <a
              href={exportCsvUrl(currentFilters)}
              className="text-sm bg-green-600 text-white px-3 py-1.5 rounded hover:bg-green-700"
            >
              Exportar CSV
            </a>
          )}
        </header>
        <div className="flex-1 overflow-hidden bg-white m-4 rounded shadow">
          <ResultsTable
            data={results}
            onLoadMore={loadMore}
            hasMore={results.length > 0 && results.length % (currentFilters.limit || 50) === 0}
          />
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Atualizar App.tsx**

```tsx
import { Prospecting } from "./pages/Prospecting";

export default function App() {
  return <Prospecting />;
}
```

- [ ] **Step 5: Testar frontend**

```bash
cd frontend && npm run dev
# Abrir http://localhost:5173
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "frontend: add filter panel, results table, and prospecting page with keyset pagination"
```

---

## FASE 5 — Cão de Guarda (Atualização Mensal Automática)

### Task 17: Scraper de Monitoramento e Fila de Atualização

**Files:**
- Create: `etl/scheduler.py`
- Create: `etl/notifier.py`
- Create: `etl/updater.py`

- [ ] **Step 1: Criar etl/notifier.py**

```python
import httpx
from loguru import logger
from config import settings

def notify_discord(message: str):
    if not settings.discord_webhook_url:
        return
    try:
        httpx.post(
            settings.discord_webhook_url,
            json={"content": message},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Notificação falhou: {e}")
```

- [ ] **Step 2: Criar etl/updater.py**

```python
from loguru import logger
from downloader import list_rf_files, download_file
from extractor import stream_csv_from_zip
from loader import get_conn, upsert_df_to_table
from state import needs_update, set_file_state
from transformer import transform_empresas_df, transform_estabelecimentos_df
from notifier import notify_discord
from config import settings
from schemas.empresas import TABLE as EMP_TABLE, COLUMNS as EMP_COLS, POLARS_SCHEMA as EMP_SCHEMA
from schemas.estabelecimentos import TABLE as EST_TABLE, COLUMNS as EST_COLS, POLARS_SCHEMA as EST_SCHEMA

SCHEMA_MAP = {
    "Empresas": (EMP_TABLE, EMP_COLS, EMP_SCHEMA, transform_empresas_df, ["cnpj_basico"]),
    "Estabelecimentos": (EST_TABLE, EST_COLS, EST_SCHEMA, transform_estabelecimentos_df,
                         ["cnpj_basico", "cnpj_ordem", "cnpj_dv"]),
}


def run_update():
    conn = get_conn()
    files = list_rf_files()
    new_count = 0
    updated_count = 0

    for rf_file in files:
        if not needs_update(conn, rf_file):
            continue

        logger.info(f"Novo arquivo detectado: {rf_file.name}")
        set_file_state(conn, rf_file.name, rf_file.last_modified, "downloading")
        zip_path = download_file(rf_file, settings.etl_data_dir)
        set_file_state(conn, rf_file.name, rf_file.last_modified, "loading")

        for prefix, (table, columns, schema, transform_fn, conflict_cols) in SCHEMA_MAP.items():
            if rf_file.name.startswith(prefix):
                for batch_df in stream_csv_from_zip(zip_path, schema):
                    clean_df = transform_fn(batch_df)
                    upsert_df_to_table(conn, clean_df, table, columns, conflict_cols)

        zip_path.unlink()
        set_file_state(conn, rf_file.name, rf_file.last_modified, "done")
        new_count += 1

    conn.close()
    msg = f"✅ Atualização CNPJ concluída: {new_count} arquivos processados."
    logger.success(msg)
    notify_discord(msg)
```

- [ ] **Step 3: Criar etl/scheduler.py**

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from updater import run_update

def main():
    scheduler = BlockingScheduler()
    # Rodar todo dia 1 do mês às 02:00
    scheduler.add_job(run_update, "cron", day=1, hour=2, minute=0)
    logger.info("Scheduler iniciado — verificação mensal às 02:00 todo dia 1")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler parado")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add etl/scheduler.py etl/notifier.py etl/updater.py
git commit -m "etl: add monthly update scheduler with upsert strategy and Discord notification"
```

---

## FASE 6 — Deploy na VPS

### Task 18: Preparação para Deploy

**Files:**
- Create: `Makefile`
- Create: `deploy.sh`

- [ ] **Step 1: Criar Makefile com comandos comuns**

```makefile
.PHONY: up down logs etl-load etl-update build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

etl-load:
	docker compose run --rm etl python main.py full-load

etl-update:
	docker compose run --rm etl python main.py update

prod-up:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

- [ ] **Step 2: Criar deploy.sh (script para execução na VPS)**

```bash
#!/bin/bash
set -e

echo "=== Deploy CNPJ Discovery ==="

# 1. Atualizar código
git pull origin main

# 2. Build dos containers
docker compose build

# 3. Subir infraestrutura (sem ETL worker — ele é manual na primeira vez)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis api frontend nginx

# 4. Aguardar PostgreSQL
until docker compose exec postgres pg_isready -U $POSTGRES_USER; do
  sleep 2
done

echo "=== Infraestrutura no ar. Para iniciar a carga: make etl-load ==="
```

- [ ] **Step 3: Tornar deploy.sh executável e commitar**

```bash
chmod +x deploy.sh
git add Makefile deploy.sh
git commit -m "ops: add Makefile shortcuts and VPS deploy script"
```

---

### Task 19: Instruções de Provisionamento da VPS

> Esta task é um guia operacional, executado manualmente na VPS (ex: Hetzner CPX41 — 8 vCPU, 16 GB RAM, NVMe 160 GB).

- [ ] **Step 1: Provisionar VPS com Ubuntu 22.04**

```bash
# Na VPS, como root:
apt update && apt upgrade -y
apt install -y git docker.io docker-compose-plugin curl ufw

# Firewall
ufw allow 22 && ufw allow 80 && ufw allow 443
ufw enable

# Criar usuário não-root
adduser deploy && usermod -aG docker deploy
```

- [ ] **Step 2: Clonar repositório**

```bash
su - deploy
git clone https://github.com/<seu-usuario>/cnpj-discovery.git
cd cnpj-discovery
cp .env.example .env
# Editar .env com senhas de produção
nano .env
```

- [ ] **Step 3: Rodar deploy e iniciar carga**

```bash
bash deploy.sh

# Iniciar o full-load (a VPS baixa diretamente da RF em minutos com link gigabit)
make etl-load

# Acompanhar logs
docker compose logs -f etl
```

- [ ] **Step 4: Configurar cron do sistema para atualização mensal**

```bash
# Como usuário deploy
crontab -e
# Adicionar:
0 2 1 * * cd /home/deploy/cnpj-discovery && docker compose run --rm etl python main.py update >> /var/log/cnpj-update.log 2>&1
```

- [ ] **Step 5: Commit de documentação**

```bash
git add -A
git commit -m "docs: add VPS provisioning instructions in plan"
```

---

## Diagrama de Fluxo do ETL

```
Receita Federal (WebDAV)
        │
        ▼ list_rf_files() — PROPFIND
┌───────────────────┐
│  Verificar estado │ ←──── etl_state (PostgreSQL)
│  needs_update()?  │
└────────┬──────────┘
         │ SIM
         ▼
   download_file()   ← streaming HTTP, chunks de 1 MB
         │
         ▼
   stream_csv_from_zip()  ← ZIP sem extrair para disco
         │ batches de 50.000 linhas (Polars)
         ▼
   transform_*_df()  ← limpeza, cast de tipos
         │
         ▼
   copy_df_to_table()    ← COPY FROM STDIN (carga inicial)
   upsert_df_to_table()  ← ON CONFLICT (atualização)
         │
         ▼
   zip_path.unlink()  ← apaga ZIP imediatamente
         │
         ▼
   set_file_state('done')
         │
         ▼ (após todos os arquivos)
   create_all_indexes()   ← CONCURRENTLY
         │
         ▼
   notify_discord()
```

---

## Estimativas de Performance (Hardware Local)

| Operação                          | Estimativa      |
|-----------------------------------|-----------------|
| Download 1 arquivo Empresas (~3GB) | 20-30 min (fibra 200 Mbps) |
| COPY bulk insert Empresas (7M rows) | 5-10 min        |
| Download total (15+ arquivos)      | 4-8 horas       |
| Full load ETL completo             | 6-12 horas      |
| Criação de todos os índices        | 30-60 min       |
| Query com filtro UF+CNAE (50M rows)| < 200 ms        |
| Export CSV 10.000 registros        | < 2 segundos    |

**Na VPS Hetzner (link gigabit):**
- Download total: 20-40 minutos
- ETL completo: 2-4 horas

---

## Checklist de Verificação Final

- [ ] Docker Compose sobe todos os serviços sem erro
- [ ] Migrations criam todas as tabelas corretamente
- [ ] Downloader lista arquivos RF via WebDAV sem erro de SSL
- [ ] Extractor processa um arquivo de domínio pequeno (CNAE.zip) corretamente
- [ ] Loader insere dados via COPY e os dados aparecem no banco
- [ ] API retorna resultados para `GET /api/prospecting?uf=SP`
- [ ] Paginação por cursor funciona (segunda página retorna registros diferentes)
- [ ] Export CSV faz download sem travar para 10.000 registros
- [ ] Frontend carrega, filtros funcionam, tabela exibe resultados
- [ ] Scheduler registra job mensal sem erro
- [ ] Notificação Discord dispara após update

---

**Plano salvo.** Duas opções de execução:

**1. Subagent-Driven (recomendado)** — despacho de um subagente por task, revisão entre cada task, iteração rápida

**2. Inline Execution** — execução na sessão atual com checkpoints de revisão

**Qual abordagem prefere?**
