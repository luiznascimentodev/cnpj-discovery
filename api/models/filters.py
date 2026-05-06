from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ProspectingFilters(BaseModel):
    uf: Optional[str] = Field(None, max_length=2, description="Sigla da UF (ex: SP)")
    municipio: Optional[int] = Field(None, description="Código IBGE do município")
    cnae_principal: Optional[int] = Field(None, description="Código CNAE principal (ex: 6201500)")
    situacao_cadastral: Optional[int] = Field(2, description="2=Ativa, 3=Suspensa, 4=Inapta, 8=Baixada")
    porte: Optional[int] = Field(None, description="1=MEI, 2=ME, 3=EPP, 5=Demais")
    excluir_mei: bool = Field(False, description="Excluir empresas com porte MEI")
    capital_social_min: Optional[float] = Field(None, ge=0, description="Capital social mínimo (R$)")
    capital_social_max: Optional[float] = Field(None, ge=0, description="Capital social máximo (R$)")
    busca_razao: Optional[str] = Field(None, min_length=2, max_length=200, description="Full-text search em razão social e nome fantasia")
    cursor_cnpj_basico: Optional[str] = Field(None, description="Cursor keyset: cnpj_basico da última linha da página anterior")
    cursor_cnpj_ordem: Optional[str] = Field(None, description="Cursor keyset: cnpj_ordem da última linha da página anterior")
    limit: int = Field(50, ge=1, le=500, description="Número máximo de resultados (1–500)")

    @model_validator(mode="after")
    def porte_mei_not_conflicting(self) -> "ProspectingFilters":
        if self.porte == 1 and self.excluir_mei:
            raise ValueError("Conflito: porte=1 (MEI) e excluir_mei=True são mutuamente exclusivos")
        return self
