from datetime import date
from typing import Annotated, Optional

from fastapi import HTTPException, Query

from models.filters import ProspectingFilters


def _parse_int_list(*groups: Optional[list[str]]) -> Optional[list[int]]:
    values: list[int] = []
    for group in groups:
        if not group:
            continue
        for raw in group:
            try:
                values.extend(int(part) for part in raw.split(",") if part.strip())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="List filters must contain integers") from exc
    return values or None


def prospecting_filters_dependency(
    cnpj: Annotated[Optional[str], Query()] = None,
    uf: Annotated[Optional[str], Query(max_length=2)] = None,
    municipio: Annotated[Optional[int], Query()] = None,
    bairro: Annotated[Optional[str], Query(min_length=2, max_length=100)] = None,
    cnaes: Annotated[Optional[list[str]], Query()] = None,
    cnaes_bracket: Annotated[Optional[list[str]], Query(alias="cnaes[]")] = None,
    situacao_cadastral: Annotated[Optional[int], Query()] = 2,
    porte: Annotated[Optional[list[str]], Query()] = None,
    porte_bracket: Annotated[Optional[list[str]], Query(alias="porte[]")] = None,
    excluir_mei: Annotated[bool, Query()] = False,
    capital_social_min: Annotated[Optional[float], Query(ge=0)] = None,
    capital_social_max: Annotated[Optional[float], Query(ge=0)] = None,
    matriz_filial: Annotated[Optional[int], Query()] = None,
    data_inicio_min: Annotated[Optional[date], Query()] = None,
    data_inicio_max: Annotated[Optional[date], Query()] = None,
    opcao_simples: Annotated[Optional[bool], Query()] = None,
    natureza_juridica: Annotated[Optional[int], Query()] = None,
    cursor_cnpj_basico: Annotated[Optional[str], Query()] = None,
    cursor_cnpj_ordem: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> ProspectingFilters:
    return ProspectingFilters(
        cnpj=cnpj,
        uf=uf,
        municipio=municipio,
        bairro=bairro,
        cnaes=_parse_int_list(cnaes, cnaes_bracket),
        situacao_cadastral=situacao_cadastral,
        porte=_parse_int_list(porte, porte_bracket),
        excluir_mei=excluir_mei,
        capital_social_min=capital_social_min,
        capital_social_max=capital_social_max,
        matriz_filial=matriz_filial,
        data_inicio_min=data_inicio_min,
        data_inicio_max=data_inicio_max,
        opcao_simples=opcao_simples,
        natureza_juridica=natureza_juridica,
        cursor_cnpj_basico=cursor_cnpj_basico,
        cursor_cnpj_ordem=cursor_cnpj_ordem,
        limit=limit,
    )
