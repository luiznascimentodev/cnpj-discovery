from schemas.base import TableSchema

CNAES = TableSchema(
    table="cnaes",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

MUNICIPIOS = TableSchema(
    table="municipios",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

PAISES = TableSchema(
    table="paises",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

NATUREZAS = TableSchema(
    table="naturezas",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

QUALIFICACOES = TableSchema(
    table="qualificacoes",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

MOTIVOS = TableSchema(
    table="motivos",
    columns=["codigo", "descricao"],
    pk_columns=["codigo"],
    conflict_columns=["codigo"],
)

# Mapeamento nome do arquivo (prefix) → schema
FILE_PREFIX_MAP = {
    "CNAE": CNAES,
    "Municipios": MUNICIPIOS,
    "Paises": PAISES,
    "Naturezas": NATUREZAS,
    "Qualificacoes": QUALIFICACOES,
    "Motivos": MOTIVOS,
}
