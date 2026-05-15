"""Router de detalhe de empresa — todos os dados de uma empresa pelo CNPJ."""
import re
from fastapi import APIRouter, HTTPException

from core.cache import cache_get, cache_set, make_cache_key
from core.config import settings
from core.db import get_pool
from modules.empresa.detail_schemas import EmpresaDetail

router = APIRouter()

_CNPJ_STRIP = re.compile(r"[.\-/\s]")
_DETAIL_TTL = 3600

_SQL_DETAIL = """
    SELECT
        e.cnpj_basico, est.cnpj_ordem, est.cnpj_dv,
        e.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
        e.razao_social, est.nome_fantasia,
        est.situacao_cadastral, est.data_situacao, est.motivo_situacao,
        e.porte, e.natureza_juridica, e.ente_federativo,
        est.data_inicio, est.matriz_filial,
        est.tipo_logradouro, est.logradouro, est.numero, est.complemento,
        est.bairro, est.cep, est.uf, est.municipio,
        m.descricao AS municipio_descricao,
        e.capital_social, est.email,
        NULLIF(TRIM(COALESCE(est.ddd1,'') || COALESCE(est.telefone1,'')), '') AS telefone1,
        NULLIF(TRIM(COALESCE(est.ddd2,'') || COALESCE(est.telefone2,'')), '') AS telefone2,
        NULLIF(TRIM(COALESCE(est.ddd_fax,'') || COALESCE(est.fax,'')), '') AS fax,
        est.cnae_principal, c.descricao AS cnae_principal_descricao,
        est.cnae_secundarios
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN municipios m ON m.codigo = est.municipio
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3
"""

_SQL_SOCIOS = """
    SELECT s.nome_socio, s.cpf_cnpj_socio, s.qualificacao,
           q.descricao AS qualificacao_descricao, s.data_entrada, s.faixa_etaria
    FROM socios s
    LEFT JOIN qualificacoes q ON q.codigo = s.qualificacao
    WHERE s.cnpj_basico = $1
    ORDER BY s.nome_socio
"""

_SQL_SIMPLES = """
    SELECT opcao_simples, data_opcao_simples, data_exc_simples,
           opcao_mei, data_opcao_mei, data_exc_mei
    FROM simples WHERE cnpj_basico = $1
"""

_SQL_CNAE_SECONDARY = """
    SELECT codigo, descricao FROM cnaes WHERE codigo = ANY($1::int[]) ORDER BY codigo
"""

_SQL_CRAWLER_DOMAINS = """
    SELECT domain, homepage_url, source, confidence, status, first_seen, last_seen
    FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND status IN ('candidate', 'verified')
    ORDER BY confidence DESC, domain
"""

_SQL_CRAWLER_CONTACTS = """
    SELECT
        contact_type, value, normalized_value, label, source, confidence,
        evidence_url, source_domain, first_seen, last_seen
    FROM paid_enrichment.published_contacts
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
    ORDER BY confidence DESC, contact_type, value
"""

_SPLIT_RE = re.compile(r"[\s,]+")


def _normalize(cnpj: str) -> str:
    return _CNPJ_STRIP.sub("", cnpj)


def _parse_secondary(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(p) for p in _SPLIT_RE.split(raw.strip()) if p.strip().isdigit()]


@router.get(
    "/empresa/{cnpj}",
    response_model=EmpresaDetail,
    tags=["empresa"],
    summary="Detalhes completos de uma empresa pelo CNPJ",
)
async def get_empresa(cnpj: str):
    normalized = _normalize(cnpj)
    if len(normalized) != 14 or not normalized.isdigit():
        raise HTTPException(status_code=422, detail="CNPJ deve ter 14 dígitos numéricos")

    cache_key = make_cache_key("detail", {"cnpj": normalized})
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    basico, ordem, dv = normalized[:8], normalized[8:12], normalized[12:]
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_DETAIL, basico, ordem, dv)
        if row is None:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        data = dict(row)
        secondary_codes = _parse_secondary(data.pop("cnae_secundarios", None))

        if secondary_codes:
            cnae_rows = await conn.fetch(_SQL_CNAE_SECONDARY, secondary_codes)
            data["cnae_secundarios"] = [dict(r) for r in cnae_rows]
        else:
            data["cnae_secundarios"] = []

        data["socios"] = [dict(r) for r in await conn.fetch(_SQL_SOCIOS, basico)]
        simples_row = await conn.fetchrow(_SQL_SIMPLES, basico)
        data["simples"] = dict(simples_row) if simples_row else None

        crawler_domains = [
            dict(r) for r in await conn.fetch(_SQL_CRAWLER_DOMAINS, basico, ordem, dv)
        ]
        crawler_contacts = [
            dict(r) for r in await conn.fetch(_SQL_CRAWLER_CONTACTS, basico, ordem, dv)
        ]
        has_paid = bool(crawler_domains or crawler_contacts)
        data["enrichment_available"] = has_paid
        data["enrichment_required_feature"] = (
            settings.paid_contact_feature_key if has_paid else None
        )
        data["crawler_enrichment"] = {
            "status": "done" if has_paid else "not_enriched",
            "domains": crawler_domains,
            "contacts": crawler_contacts,
        }

    await cache_set(cache_key, data, ttl=_DETAIL_TTL)
    return data
