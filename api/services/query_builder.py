from models.filters import ProspectingFilters

_BAIRRO_CANONICAL_EXPR = """trim(regexp_replace(
        regexp_replace(
            regexp_replace(upper(est.bairro), '^[^A-Z0-9]+', ''),
            '^([A-Z0-9]{1,3}[\\-.:])+', ''
        ),
        '\\s+', ' ', 'g'
    ))"""

_SELECT_SQL = """
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
        est.bairro,
        est.email,
        NULLIF(TRIM(COALESCE(est.ddd1, '') || COALESCE(est.telefone1, '')), '') AS telefone1,
        e.porte,
        e.capital_social,
        est.data_inicio
"""

_FROM_SQL = """
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    LEFT JOIN municipios m ON m.codigo = est.municipio
"""

_SIMPLES_JOIN = "LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico"

_EST_ONLY_CANDIDATE_SQL = """
WITH candidate_est AS MATERIALIZED (
    SELECT
        est.cnpj_basico,
        est.cnpj_ordem,
        est.cnpj_dv,
        est.nome_fantasia,
        est.situacao_cadastral,
        est.cnae_principal,
        est.uf,
        est.municipio,
        est.bairro,
        est.email,
        est.ddd1,
        est.telefone1,
        est.data_inicio
    FROM estabelecimentos est
    {where}
    ORDER BY est.cnpj_basico, est.cnpj_ordem
    LIMIT {limit}
)
"""


def build_prospecting_query(f: ProspectingFilters, *, include_limit: bool = True) -> tuple[str, list]:
    """
    Builds parameterized SQL ($1, $2, …) for asyncpg.
    When f.cnpj is set, returns a PK lookup ignoring all other filters.
    """
    if f.cnpj:
        sql = (
            f"{_SELECT_SQL}{_FROM_SQL}"
            f" WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3"
            f" LIMIT 1"
        )
        return sql, [f.cnpj[:8], f.cnpj[8:12], f.cnpj[12:]]

    est_conditions: list[str] = []
    company_conditions: list[str] = []
    simples_conditions: list[str] = []
    params: list = []
    needs_simples = False
    p = 1

    if f.situacao_cadastral is not None:
        est_conditions.append(f"est.situacao_cadastral = ${p}")
        params.append(f.situacao_cadastral)
        p += 1

    if f.uf:
        est_conditions.append(f"est.uf = ${p}")
        params.append(f.uf.upper())
        p += 1

    if f.municipio is not None:
        est_conditions.append(f"est.municipio = ${p}")
        params.append(f.municipio)
        p += 1

    if f.bairro:
        est_conditions.append("est.bairro IS NOT NULL")
        est_conditions.append("est.bairro != ''")
        est_conditions.append(f"{_BAIRRO_CANONICAL_EXPR} = ${p}")
        params.append(f.bairro.strip().upper())
        p += 1

    if f.cnaes:
        est_conditions.append(f"est.cnae_principal = ANY(${p}::int[])")
        params.append(f.cnaes)
        p += 1

    if f.porte:
        company_conditions.append(f"e.porte = ANY(${p}::int[])")
        params.append(f.porte)
        p += 1

    if f.excluir_mei:
        company_conditions.append("(e.porte IS NULL OR e.porte != 1)")

    if f.capital_social_min is not None:
        company_conditions.append(f"e.capital_social >= ${p}")
        params.append(f.capital_social_min)
        p += 1

    if f.capital_social_max is not None:
        company_conditions.append(f"e.capital_social <= ${p}")
        params.append(f.capital_social_max)
        p += 1

    if f.matriz_filial is not None:
        est_conditions.append(f"est.matriz_filial = ${p}")
        params.append(f.matriz_filial)
        p += 1

    if f.data_inicio_min is not None:
        est_conditions.append(f"est.data_inicio >= ${p}")
        params.append(f.data_inicio_min)
        p += 1

    if f.data_inicio_max is not None:
        est_conditions.append(f"est.data_inicio <= ${p}")
        params.append(f.data_inicio_max)
        p += 1

    if f.natureza_juridica is not None:
        company_conditions.append(f"e.natureza_juridica = ${p}")
        params.append(f.natureza_juridica)
        p += 1

    if f.opcao_simples is not None:
        needs_simples = True
        simples_conditions.append(f"s.opcao_simples = ${p}")
        params.append("S" if f.opcao_simples else "N")
        p += 1

    if include_limit and f.cursor_cnpj_basico and f.cursor_cnpj_ordem:
        est_conditions.append(f"(est.cnpj_basico, est.cnpj_ordem) > (${p}, ${p + 1})")
        params.extend([f.cursor_cnpj_basico, f.cursor_cnpj_ordem])
        p += 2

    if include_limit and not company_conditions and not simples_conditions:
        where = ("WHERE " + " AND ".join(est_conditions)) if est_conditions else ""
        sql = (
            _EST_ONLY_CANDIDATE_SQL.format(where=where, limit=f.limit)
            + f"{_SELECT_SQL}"
            + """
    FROM candidate_est est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    LEFT JOIN municipios m ON m.codigo = est.municipio
    ORDER BY est.cnpj_basico, est.cnpj_ordem
"""
        )
        return sql, params

    simples_join = f"\n    {_SIMPLES_JOIN}" if needs_simples else ""
    conditions = est_conditions + company_conditions + simples_conditions
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    limit = f" LIMIT {f.limit}" if include_limit else ""
    sql = f"{_SELECT_SQL}{_FROM_SQL}{simples_join} {where} ORDER BY est.cnpj_basico, est.cnpj_ordem{limit}"
    return sql, params


def build_enrichment_candidate_query(
    f: ProspectingFilters,
    *,
    max_items: int,
) -> tuple[str, list]:
    """Build a bounded CNPJ-only query from the same filters used by prospecting."""
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    bounded_filters = f.model_copy(update={"limit": max_items})
    sql, params = build_prospecting_query(bounded_filters)
    return (
        "SELECT cnpj_basico, cnpj_ordem, cnpj_dv "
        f"FROM ({sql}) enrichment_candidates",
        params,
    )
