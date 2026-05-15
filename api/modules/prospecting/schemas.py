import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator

_CNPJ_RE = re.compile(r"[.\-/\s]")


def normalize_cnpj(raw: str) -> str:
    return _CNPJ_RE.sub("", raw)


class ProspectingFilters(BaseModel):
    cnpj: Optional[str] = Field(None, description="CNPJ com ou sem pontuação — ignora demais filtros")
    uf: Optional[str] = Field(None, max_length=2)
    municipio: Optional[int] = None
    bairro: Optional[str] = Field(None, min_length=2, max_length=100)
    cnaes: Optional[list[int]] = Field(None, description="Códigos CNAE (ANY match)")
    situacao_cadastral: Optional[int] = Field(2)
    porte: Optional[list[int]] = Field(None, description="1=MEI,2=ME,3=EPP,5=Demais (múltiplos)")
    excluir_mei: bool = Field(False)
    capital_social_min: Optional[float] = Field(None, ge=0)
    capital_social_max: Optional[float] = Field(None, ge=0)
    matriz_filial: Optional[int] = Field(None, description="1=Matriz, 2=Filial")
    data_inicio_min: Optional[date] = None
    data_inicio_max: Optional[date] = None
    opcao_simples: Optional[bool] = None
    cursor_cnpj_basico: Optional[str] = None
    cursor_cnpj_ordem: Optional[str] = None
    limit: int = Field(100, ge=50, le=50_000)

    @model_validator(mode="after")
    def validate_filters(self) -> "ProspectingFilters":
        if self.cnpj is not None:
            normalized = normalize_cnpj(self.cnpj)
            if len(normalized) != 14 or not normalized.isdigit():
                raise ValueError("CNPJ deve ter 14 dígitos numéricos")
            self.cnpj = normalized

        if self.porte and 1 in self.porte and self.excluir_mei:
            raise ValueError("Conflito: porte inclui MEI (1) e excluir_mei=True são mutuamente exclusivos")

        if (
            self.data_inicio_min is not None
            and self.data_inicio_max is not None
            and self.data_inicio_min > self.data_inicio_max
        ):
            raise ValueError("data_inicio_min não pode ser maior que data_inicio_max")

        return self
