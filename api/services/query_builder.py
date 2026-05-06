from models.filters import ProspectingFilters

_BASE_SQL = """
    SELECT
        e.cnpj_basico,
        est.cnpj_ordem,
        est.cnpj_dv,
        e.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
        e.razao_social,
        est.nome_fantasia,
        est.situacao_cadastral,
        est.cnae_principal,
        c.descricao AS cnae_descricao,
        est.uf,
        est.municipio,
        m.descricao AS municipio_descricao,
        est.email,
        NULLIF(TRIM(COALESCE(est.ddd1, '') || COALESCE(est.telefone1, '')), '') AS telefone1,
        e.porte,
        e.capital_social,
        est.data_inicio
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    LEFT JOIN municipios m ON m.codigo = est.municipio
"""


def build_prospecting_query(f: ProspectingFilters) -> tuple[str, list]:
    """
    Constrói SQL dinâmico com parâmetros posicionais ($1, $2, …) para asyncpg.
    Keyset pagination via (cnpj_basico, cnpj_ordem) > cursor evita OFFSET lento.
    Retorna (sql, params).
    """
    conditions: list[str] = []
    params: list = []
    p = 1

    if f.situacao_cadastral is not None:
        conditions.append(f"est.situacao_cadastral = ${p}")
        params.append(f.situacao_cadastral)
        p += 1

    if f.uf:
        conditions.append(f"est.uf = ${p}")
        params.append(f.uf.upper())
        p += 1

    if f.municipio is not None:
        conditions.append(f"est.municipio = ${p}")
        params.append(f.municipio)
        p += 1

    if f.cnae_principal is not None:
        conditions.append(f"est.cnae_principal = ${p}")
        params.append(f.cnae_principal)
        p += 1

    if f.porte is not None:
        conditions.append(f"e.porte = ${p}")
        params.append(f.porte)
        p += 1

    if f.excluir_mei:
        conditions.append("(e.porte IS NULL OR e.porte != 1)")

    if f.capital_social_min is not None:
        conditions.append(f"e.capital_social >= ${p}")
        params.append(f.capital_social_min)
        p += 1

    if f.capital_social_max is not None:
        conditions.append(f"e.capital_social <= ${p}")
        params.append(f.capital_social_max)
        p += 1

    if f.busca_razao:
        # ${p} referenciado duas vezes no mesmo fragmento SQL — asyncpg reutiliza o mesmo
        # parâmetro posicional, portanto apenas um valor é adicionado a params.
        conditions.append(
            f"(to_tsvector('portuguese', e.razao_social) @@ plainto_tsquery('portuguese', ${p})"
            f" OR to_tsvector('portuguese', COALESCE(est.nome_fantasia, '')) @@ plainto_tsquery('portuguese', ${p}))"
        )
        params.append(f.busca_razao)
        p += 1

    if f.cursor_cnpj_basico and f.cursor_cnpj_ordem:
        conditions.append(f"(est.cnpj_basico, est.cnpj_ordem) > (${p}, ${p + 1})")
        params.extend([f.cursor_cnpj_basico, f.cursor_cnpj_ordem])
        p += 2

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"{_BASE_SQL} {where} ORDER BY est.cnpj_basico, est.cnpj_ordem LIMIT {f.limit}"
    return sql, params
