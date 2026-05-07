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

_SIMPLES_JOIN = "LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico"


def build_prospecting_query(f: ProspectingFilters) -> tuple[str, list]:
    """
    Builds parameterized SQL ($1, $2, …) for asyncpg.
    When f.cnpj is set, returns a PK lookup ignoring all other filters.
    """
    if f.cnpj:
        sql = (
            f"{_BASE_SQL}"
            f" WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3"
            f" LIMIT 1"
        )
        return sql, [f.cnpj[:8], f.cnpj[8:12], f.cnpj[12:]]

    conditions: list[str] = []
    params: list = []
    p = 1
    needs_simples = False

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

    if f.bairro:
        conditions.append(f"est.bairro ILIKE ${p}")
        params.append(f"%{f.bairro}%")
        p += 1

    if f.cnaes:
        conditions.append(f"est.cnae_principal = ANY(${p}::int[])")
        params.append(f.cnaes)
        p += 1

    if f.porte:
        conditions.append(f"e.porte = ANY(${p}::int[])")
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

    if f.matriz_filial is not None:
        conditions.append(f"est.matriz_filial = ${p}")
        params.append(f.matriz_filial)
        p += 1

    if f.data_inicio_min is not None:
        conditions.append(f"est.data_inicio >= ${p}")
        params.append(f.data_inicio_min)
        p += 1

    if f.data_inicio_max is not None:
        conditions.append(f"est.data_inicio <= ${p}")
        params.append(f.data_inicio_max)
        p += 1

    if f.natureza_juridica is not None:
        conditions.append(f"e.natureza_juridica = ${p}")
        params.append(f.natureza_juridica)
        p += 1

    if f.opcao_simples is not None:
        needs_simples = True
        conditions.append(f"s.opcao_simples = ${p}")
        params.append("S" if f.opcao_simples else "N")
        p += 1

    if f.busca_razao:
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

    simples_join = f"\n    {_SIMPLES_JOIN}" if needs_simples else ""
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"{_BASE_SQL}{simples_join} {where} ORDER BY est.cnpj_basico, est.cnpj_ordem LIMIT {f.limit}"
    return sql, params
