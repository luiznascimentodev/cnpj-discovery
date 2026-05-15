from datetime import date
from typing import Optional

from pydantic import BaseModel


class EmpresaOut(BaseModel):
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    cnpj_completo: str
    razao_social: str
    nome_fantasia: Optional[str] = None
    situacao_cadastral: Optional[int] = None
    cnae_principal: Optional[int] = None
    cnae_descricao: Optional[str] = None
    uf: Optional[str] = None
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None
    bairro: Optional[str] = None
    email: Optional[str] = None
    telefone1: Optional[str] = None
    porte: Optional[int] = None
    capital_social: Optional[float] = None
    data_inicio: Optional[date] = None
