-- CNPJ Discovery - Tabelas de Domínio (Lookups) e Constraints Pós-Load

-- Tabelas de domínio (dados de referência carregados pelo ETL)
CREATE TABLE IF NOT EXISTS cnaes (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS municipios (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paises (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS naturezas (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qualificacoes (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS motivos (
    codigo    INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);
