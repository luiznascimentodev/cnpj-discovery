from schemas.base import TableSchema

SCHEMA = TableSchema(
    table="socios",
    columns=[
        "cnpj_basico",
        "identificador",
        "nome_socio",
        "cpf_cnpj_socio",
        "qualificacao",
        "data_entrada",
        "pais",
        "repr_legal",
        "nome_repr",
        "qualificacao_repr",
        "faixa_etaria",
    ],
    pk_columns=[],          # PK é BIGSERIAL, não vem do CSV
    conflict_columns=[],    # socios não faz upsert por coluna — é append-only
)
