from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


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


class CrawlerDomainOut(BaseModel):
    domain: str
    homepage_url: Optional[str] = None
    source: str
    confidence: int
    status: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class CrawlerContactOut(BaseModel):
    contact_type: str
    value: str
    normalized_value: str
    label: Optional[str] = None
    source: str
    confidence: int
    evidence_url: Optional[str] = None
    source_domain: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class CrawlerEnrichmentOut(BaseModel):
    status: str = "not_enriched"
    domains: list[CrawlerDomainOut] = Field(default_factory=list)
    contacts: list[CrawlerContactOut] = Field(default_factory=list)


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
    cnae_secundarios: list[CnaeItem] = Field(default_factory=list)
    socios: list[SocioOut] = Field(default_factory=list)
    simples: Optional[SimplesOut] = None
    enrichment_available: bool = False
    enrichment_required_feature: Optional[str] = None
    crawler_enrichment: CrawlerEnrichmentOut = Field(default_factory=CrawlerEnrichmentOut)
