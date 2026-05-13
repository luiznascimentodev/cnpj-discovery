# CNPJ Discovery Machine

Uma máquina de prospecção B2B completa que ingere, processa e expõe ~50 milhões de registros de CNPJs da Receita Federal via API REST escalável.

## O Projeto

**CNPJ Discovery** é um sistema backend robusto que:
- Ingere dados de CNPJs da Receita Federal através de um pipeline ETL completo
- Armazena registros em PostgreSQL 16 com índices otimizados para busca complexa
- Expõe endpoints REST via FastAPI com filtros avançados, paginação por cursor e exportação CSV
- É 100% containerizado com Docker Compose para paridade perfeita entre desenvolvimento local e produção (VPS)
- Inclui testes automatizados com cobertura de 100%

**Nota:** Este repositório contém apenas o backend. O frontend será um projeto separado que consome esta API.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    CNPJ Discovery Machine                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐      ┌──────────────────────────────┐  │
│  │   ETL Pipeline   │      │    FastAPI REST Server       │  │
│  │                  │      │                              │  │
│  │ • Download RF    │      │ • GET /v1/prospecting        │  │
│  │ • Parse CSV      │  →   │ • GET /v1/export/csv         │  │
│  │ • Validate       │      │ • GET /v1/status             │  │
│  │ • Load PostgreSQL│      │ • GET /v1/health             │  │
│  │ • Build Indices  │      │ • GET /docs (Swagger UI)     │  │
│  └──────────────────┘      └──────────────────────────────┘  │
│           ↓                              ↓                    │
│  ┌──────────────────┐      ┌──────────────────────────────┐  │
│  │   PostgreSQL     │      │       Redis Cache             │  │
│  │   (50M+ CNPJs)   │      │   (Query Results)             │  │
│  └──────────────────┘      └──────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Camadas

- **ETL Pipeline**: Ingesta e processamento de dados da Receita Federal
  - Download via WebDAV
  - Parsing de CSVs com Polars
  - Validação de dados
  - Inserção em batch no PostgreSQL
  - Construção de índices otimizados

- **Banco de Dados**: PostgreSQL 16
  - Tabela principal: `companies` (~50M registros)
  - Índices em: CNPJ, razão social, município, atividade
  - Constraints de integridade

- **API REST**: FastAPI
  - Filtros avançados (CNPJ, nome, localização, atividade)
  - Paginação por cursor
  - Exportação CSV
  - Documentação interativa em `/docs`

- **Cache**: Redis 7
  - Armazenamento de resultados de busca
  - Sessões de processamento

## Pré-requisitos

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Python** 3.12+ (apenas para desenvolvimento local sem Docker)
- **Git** 2.0+

## Quickstart

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/cnpj-discovery.git
cd cnpj-discovery
git checkout develop
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env com suas credenciais (especialmente POSTGRES_PASSWORD, RF_SHARE_TOKEN)
```

### 3. Subir os containers

```bash
docker compose up -d
```

Verifique que PostgreSQL e Redis estão healthy:

```bash
docker compose ps
```

### 4. Carregar dados (ETL)

```bash
docker compose exec api python -m cnpj_discovery.etl.loader
```

Ou via makefile (quando implementado):

```bash
make etl-load
```

### 5. Verificar saúde da API

```bash
curl http://localhost:8000/v1/health
```

Acesse a documentação interativa em **http://localhost:8000/docs**

### 6. Rodar testes

```bash
docker compose exec api pytest --cov
```

## Estrutura de Diretórios

```
cnpj-discovery/
├── .gitignore                    # Configuração de arquivos ignorados
├── .env.example                  # Template de variáveis de ambiente
├── README.md                     # Este arquivo
├── docker-compose.yml            # Orquestração de containers (PostgreSQL, Redis, API)
├── Dockerfile                    # Imagem da API
├── Makefile                      # Automação de tarefas (up, down, etl, test)
├── pyproject.toml                # Configuração Python (dependências, pytest, mypy)
│
├── src/
│   └── cnpj_discovery/
│       ├── __init__.py
│       ├── main.py               # Entry point da API FastAPI
│       │
│       ├── api/                  # Endpoints REST
│       │   ├── __init__.py
│       │   ├── routes.py         # GET /v1/prospecting, /v1/export/csv, /v1/status, /v1/health
│       │   ├── schemas.py        # Pydantic models (request/response)
│       │   └── dependencies.py   # Injeção de dependências (DB, Redis)
│       │
│       ├── etl/                  # Pipeline ETL
│       │   ├── __init__.py
│       │   ├── loader.py         # Download e carregamento de dados
│       │   ├── parser.py         # Parsing de CSVs
│       │   └── validator.py      # Validação de dados
│       │
│       ├── db/                   # Camada de banco de dados
│       │   ├── __init__.py
│       │   ├── models.py         # SQLAlchemy/asyncpg models
│       │   ├── queries.py        # Queries otimizadas
│       │   └── migrations.py     # Alembic migrations (quando necessário)
│       │
│       ├── cache/                # Cache Redis
│       │   ├── __init__.py
│       │   └── client.py         # Cliente Redis
│       │
│       └── config.py             # Configuração centralizada (env vars)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Fixtures pytest
│   ├── unit/                     # Testes unitários
│   │   ├── test_parser.py
│   │   ├── test_validator.py
│   │   └── test_queries.py
│   ├── integration/              # Testes de integração
│   │   ├── test_etl.py
│   │   └── test_api.py
│   └── fixtures/                 # Dados de teste
│       └── sample_data.csv
│
├── docs/
│   ├── superpowers/              # Documentação interna (planos, análises)
│   │   └── plans/
│   │       └── 2026-05-04-cnpj-discovery-machine.md
│   └── ARCHITECTURE.md           # Documentação arquitetural detalhada
│
└── scripts/                      # Scripts utilitários
    ├── init_db.sh                # Inicializar banco de dados
    └── seed_test_data.sh         # Popular dados de teste
```

## API Endpoints

### Prospecção

| Método | Rota | Descrição | Parâmetros |
|--------|------|-----------|-----------|
| `GET` | `/v1/prospecting` | Buscar CNPJs com filtros avançados | `cnpj`, `name`, `municipality`, `activity`, `limit`, `cursor` |
| `GET` | `/v1/export/csv` | Exportar resultados em CSV | `cnpj`, `name`, `municipality`, `activity`, `format` |

### Status e Health

| Método | Rota | Descrição | Parâmetros |
|--------|------|-----------|-----------|
| `GET` | `/v1/status` | Status do processamento ETL | - |
| `GET` | `/v1/health` | Health check da API | - |

### Documentação

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/docs` | Swagger UI (documentação interativa) |
| `GET` | `/redoc` | ReDoc (documentação alternativa) |
| `GET` | `/openapi.json` | Schema OpenAPI em JSON |

## Rodar Testes

```bash
# Todos os testes com cobertura
docker compose exec api pytest --cov

# Testes específicos
docker compose exec api pytest tests/unit/test_parser.py

# Modo verbose
docker compose exec api pytest -vv --cov

# Com coverage HTML report
docker compose exec api pytest --cov --cov-report=html
```

## Variáveis de Ambiente

| Nome | Descrição | Obrigatório | Padrão |
|------|-----------|-------------|--------|
| `POSTGRES_HOST` | Host do PostgreSQL | Sim | `localhost` |
| `POSTGRES_PORT` | Porta do PostgreSQL | Sim | `5432` |
| `POSTGRES_DB` | Nome do banco de dados | Sim | `cnpj` |
| `POSTGRES_USER` | Usuário PostgreSQL | Sim | `cnpj_user` |
| `POSTGRES_PASSWORD` | Senha PostgreSQL | Sim | - |
| `REDIS_URL` | URL de conexão Redis | Sim | `redis://localhost:6379/0` |
| `ETL_DATA_DIR` | Diretório para dados ETL | Sim | `/tmp/cnpj_data` |
| `ETL_BATCH_SIZE` | Tamanho do batch no ETL | Não | `500000` |
| `ETL_WORKERS` | Número de workers ETL | Não | `4` |
| `ETL_DOWNLOAD_WORKERS` | Downloads paralelos da RF | Não | `2` |
| `ETL_PROCESS_WORKERS` | Workers de processamento/carga | Não | `6` |
| `ETL_INDEX_WORKERS` | Índices criados em paralelo | Não | `4` |
| `ETL_ACTIVE_ONLY` | Carrega somente CNPJs com estabelecimento ativo | Não | `true` |
| `DISCORD_WEBHOOK_URL` | Webhook Discord (notificações) | Não | - |
| `SLACK_WEBHOOK_URL` | Webhook Slack (notificações) | Não | - |
| `RF_SHARE_TOKEN` | Token WebDAV Receita Federal | Sim | - |
| `RF_WEBDAV_BASE` | URL base WebDAV RF | Sim | `https://arquivos.receitafederal.gov.br/public.php/webdav/` |
| `API_HOST` | Host da API | Não | `0.0.0.0` |
| `API_PORT` | Porta da API | Não | `8000` |
| `CORS_ORIGINS` | Origens CORS permitidas | Não | `http://localhost:3000,http://localhost:5173` |
| `ENVIRONMENT` | Ambiente (development/production) | Não | `development` |

## Deploy na VPS

### Preparação

1. Clonar repositório na VPS
2. Configurar `.env` com credenciais de produção
3. Certificar HTTPS está ativado (Let's Encrypt)

### Subir produção

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Monitoramento

- Logs: `docker compose logs -f api`
- Status: `curl https://seu-dominio.com/v1/health`
- Métricas: (implementado em Task futura)

## Desenvolvimento

### Setup local

```bash
# Criar venv
python3.12 -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -e ".[dev]"

# Rodar em modo debug
uvicorn cnpj_discovery.main:app --reload
```

### Lint e Formatação

```bash
# Ruff (lint)
ruff check src/ tests/

# Formatação
black src/ tests/

# Type checking
mypy src/
```

## Arquivos Importantes

- **`docker-compose.yml`**: Orquestração de containers em desenvolvimento
- **`Dockerfile`**: Imagem da API
- **`pyproject.toml`**: Configuração Python e dependências
- **`tests/`**: Suite de testes com 100% de cobertura
- **`docs/superpowers/plans/`**: Planos de desenvolvimento

## Suporte

Para dúvidas ou issues:
1. Verifique a documentação em `/docs` (Swagger UI)
2. Consulte `docs/ARCHITECTURE.md` para detalhes arquiteturais
3. Abra uma issue no GitHub

## Licença

MIT
