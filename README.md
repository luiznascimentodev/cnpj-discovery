# CNPJ Discovery Machine

**Acesso ao vivo (Produção):** [http://2.24.97.83/](http://2.24.97.83/) (Frontend / API na VPS)

## O Projeto

**CNPJ Discovery** é uma plataforma completa de inteligência comercial e prospecção B2B. O sistema ingere, processa e expõe aproximadamente **50 milhões de registros de empresas (CNPJs)** da Receita Federal do Brasil, enriquecendo ativamente esses dados com informações de contato reais e atualizadas que muitas vezes não constam nas bases governamentais públicas.

O objetivo principal é transformar dados brutos em **leads qualificados e acionáveis** para equipes de vendas, growth e marketing, através de uma API REST de altíssima performance e uma interface frontend moderna.

## Principais Funcionalidades

- **Busca Avançada e Exploração:** Filtragem super rápida por CNPJ, Razão Social, Nome Fantasia, CNAE (Atividade Econômica), Município e Estado.
- **Enriquecimento Ativo (Discovery):** O sistema não é apenas um banco de dados estático. Ele possui um motor de inteligência que busca ativamente o **site real** e os **e-mails corporativos** da empresa na internet utilizando:
  - Heurísticas de "Brand Slugs" (ex: tenta adivinhar o domínio a partir do nome da empresa).
  - Consulta a APIs externas de busca (Brave Search) e registros nacionais (BrasilAPI).
  - Crawling assíncrono para validar a pertinência do site em relação à empresa.
- **Performance e Escala:** Paginação baseada em cursor que garante respostas em milissegundos mesmo consultando milhões de registros. Suportado por índices otimizados no PostgreSQL e camada de cache com Redis.
- **Exportação de Dados:** Geração de arquivos CSV sob demanda com os resultados filtrados para fácil importação em plataformas de CRM e Cold Email.

## Casos de Uso

1. **Geração de Leads B2B:** Encontrar facilmente todas as indústrias de um segmento específico em uma região, que possuam site e contatos ativos.
2. **Qualificação de Contatos Automática:** Dado um CNPJ, o motor de enriquecimento descobre o site oficial e o e-mail real da empresa, viabilizando campanhas de Outbound.
3. **Inteligência de Mercado:** Analisar a distribuição de empresas ativas, novas aberturas e mapeamento de nichos econômicos em todo o território nacional.

## Arquitetura do Sistema

O projeto é modular e desenhado para suportar grande volume de dados de forma resiliente:

### 1. ETL Pipeline (Extração, Transformação e Carga)
Responsável por baixar gigabytes de dados brutos mensais da Receita Federal, realizar o parsing ultra-rápido com **Polars**, validar a integridade estrutural e carregar no banco de dados principal.

### 2. Motor de Enriquecimento (Discovery)
Pipeline assíncrono que entra em ação para validar a presença digital das empresas. Faz chamadas de rede, avalia scores de confiabilidade de e-mails/domínios e consolida os dados na base de `paid_enrichment`.

### 3. API REST (FastAPI)
O coração da plataforma. Expõe a infraestrutura de dados de forma segura, com rate limiting, filtros granulares e rotas de status. 
- Swagger UI (Documentação interativa) disponível na rota `/docs`.

### 4. Interface Web (React 19)
Frontend construído em modo Single Page Application (SPA), desenhado com a arquitetura Feature-Sliced Design (FSD v2), garantindo uma experiência de usuário fluida e visualização intuitiva dos dados expostos pela API.

## Stack Tecnológica

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy (async), Polars.
- **Banco de Dados:** PostgreSQL 16 (Tabelas gigantes com índices seletivos).
- **Cache & Filas:** Redis 7.
- **Frontend Web:** React 19, TypeScript, Vite, TailwindCSS / Radix UI.
- **Enriquecimento / Crawling:** Playwright, HTTPX.
- **Infraestrutura:** Totalmente containerizado com Docker e orquestrado com Docker Compose e Nginx.

---

```text
┌─────────────────────────────────────────────────────────────┐
│                    CNPJ Discovery Machine                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐      ┌──────────────────────────────┐  │
│  │   ETL Pipeline   │      │    FastAPI REST Server       │  │
│  │  (Polars/Python) │  →   │       (Python 3.12)          │  │
│  └──────────────────┘      └──────────────┬───────────────┘  │
│                                           │                   │
│                                           ↓                   │
│  ┌──────────────────┐      ┌──────────────────────────────┐  │
│  │   PostgreSQL     │      │   Enrichment & Discovery     │  │
│  │   (50M+ CNPJs)   │  ←   │     (Crawlers, APIs)         │  │
│  └──────────────────┘      └──────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```
