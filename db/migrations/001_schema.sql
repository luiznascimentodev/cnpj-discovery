-- CNPJ Discovery - Schema Principal
-- Dados base da empresa (arquivo Empresas*.zip da RF)
CREATE TABLE empresas (
    cnpj_basico       CHAR(8)       PRIMARY KEY,
    razao_social      TEXT          NOT NULL,
    natureza_juridica SMALLINT,
    qualificacao_resp SMALLINT,
    capital_social    NUMERIC(18,2),
    porte             SMALLINT,     -- 1=MEI, 2=ME, 3=EPP, 5=Demais
    ente_federativo   TEXT
);

-- Dados do estabelecimento (arquivo Estabelecimentos*.zip)
-- CNPJ completo = cnpj_basico + cnpj_ordem + cnpj_dv
CREATE TABLE estabelecimentos (
    cnpj_basico         CHAR(8)      NOT NULL,
    cnpj_ordem          CHAR(4)      NOT NULL,
    cnpj_dv             CHAR(2)      NOT NULL,
    matriz_filial       SMALLINT,    -- 1=Matriz, 2=Filial
    nome_fantasia       TEXT,
    situacao_cadastral  SMALLINT,    -- 2=Ativa, 3=Suspensa, 4=Inapta, 8=Baixada
    data_situacao       DATE,
    motivo_situacao     SMALLINT,
    cidade_exterior     TEXT,
    pais                SMALLINT,
    data_inicio         DATE,
    cnae_principal      INT,
    cnae_secundarios    TEXT,
    tipo_logradouro     TEXT,
    logradouro          TEXT,
    numero              TEXT,
    complemento         TEXT,
    bairro              TEXT,
    cep                 CHAR(8),
    uf                  CHAR(2),
    municipio           INT,
    ddd1                CHAR(4),
    telefone1           TEXT,
    ddd2                CHAR(4),
    telefone2           TEXT,
    ddd_fax             CHAR(4),
    fax                 TEXT,
    email               TEXT,
    situacao_especial   TEXT,
    data_situacao_esp   DATE,
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

-- Simples Nacional (arquivo Simples.zip)
CREATE TABLE simples (
    cnpj_basico         CHAR(8)      PRIMARY KEY,
    opcao_simples       CHAR(1),
    data_opcao_simples  DATE,
    data_exc_simples    DATE,
    opcao_mei           CHAR(1),
    data_opcao_mei      DATE,
    data_exc_mei        DATE
);
