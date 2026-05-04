from schemas.base import TableSchema

SCHEMA = TableSchema(
    table="empresas",
    columns=[
        "cnpj_basico",
        "razao_social",
        "natureza_juridica",
        "qualificacao_resp",
        "capital_social",
        "porte",
        "ente_federativo",
    ],
    pk_columns=["cnpj_basico"],
    conflict_columns=["cnpj_basico"],
)
