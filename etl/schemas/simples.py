from schemas.base import TableSchema

SCHEMA = TableSchema(
    table="simples",
    columns=[
        "cnpj_basico",
        "opcao_simples",
        "data_opcao_simples",
        "data_exc_simples",
        "opcao_mei",
        "data_opcao_mei",
        "data_exc_mei",
    ],
    pk_columns=["cnpj_basico"],
    conflict_columns=["cnpj_basico"],
)
