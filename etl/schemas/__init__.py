from schemas.empresas import SCHEMA as EMPRESAS
from schemas.estabelecimentos import SCHEMA as ESTABELECIMENTOS
from schemas.socios import SCHEMA as SOCIOS
from schemas.simples import SCHEMA as SIMPLES
from schemas.dominios import CNAES, MUNICIPIOS, PAISES, NATUREZAS, QUALIFICACOES, MOTIVOS, FILE_PREFIX_MAP

# Mapeamento principal: prefixo do arquivo RF → schema
MAIN_FILE_SCHEMAS = {
    "Empresas": EMPRESAS,
    "Estabelecimentos": ESTABELECIMENTOS,
    "Socios": SOCIOS,
    "Simples": SIMPLES,
}

__all__ = [
    "EMPRESAS", "ESTABELECIMENTOS", "SOCIOS", "SIMPLES",
    "CNAES", "MUNICIPIOS", "PAISES", "NATUREZAS", "QUALIFICACOES", "MOTIVOS",
    "FILE_PREFIX_MAP", "MAIN_FILE_SCHEMAS",
]
