from datetime import date
from typing import Optional
from pydantic import BaseModel


class CnaeItem(BaseModel):
    codigo: int
    descricao: Optional[str] = None


class SocioOut(BaseModel):
    nome_socio: Optional[str] = None
    cpf_cnpj_socio: Optional[str] = None
    qualificacao: Optional[int] = None
    qualificacao_descricao: Optional[str] = None
    data_entrada: Optional[date] = None
    faixa_etaria: Optional[int] = None


class SimplesOut(BaseModel):
    opcao_simples: Optional[str] = None
    data_opcao_simples: Optional[date] = None
    data_exc_simples: Optional[date] = None
    opcao_mei: Optional[str] = None
    data_opcao_mei: Optional[date] = None
    data_exc_mei: Optional[date] = None


class EmpresaDetail(BaseModel):
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    cnpj_completo: str
    razao_social: str
    nome_fantasia: Optional[str] = None
    situacao_cadastral: Optional[int] = None
    data_situacao: Optional[date] = None
    motivo_situacao: Optional[int] = None
    porte: Optional[int] = None
    natureza_juridica: Optional[int] = None
    ente_federativo: Optional[str] = None
    data_inicio: Optional[date] = None
    matriz_filial: Optional[int] = None
    tipo_logradouro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cep: Optional[str] = None
    uf: Optional[str] = None
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None
    capital_social: Optional[float] = None
    email: Optional[str] = None
    telefone1: Optional[str] = None
    telefone2: Optional[str] = None
    fax: Optional[str] = None
    cnae_principal: Optional[int] = None
    cnae_principal_descricao: Optional[str] = None
    cnae_secundarios: list[CnaeItem] = []
    socios: list[SocioOut] = []
    simples: Optional[SimplesOut] = None
