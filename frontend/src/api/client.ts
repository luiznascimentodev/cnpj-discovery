import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/v1',
})

export interface EmpresaOut {
  cnpj_basico: string
  cnpj_ordem: string
  cnpj_dv: string
  cnpj_completo: string
  razao_social: string
  nome_fantasia: string | null
  situacao_cadastral: number | null
  cnae_principal: number | null
  cnae_descricao: string | null
  uf: string | null
  municipio: number | null
  municipio_descricao: string | null
  bairro: string | null
  email: string | null
  telefone1: string | null
  porte: number | null
  capital_social: number | null
  data_inicio: string | null
}

export interface CnaeItem {
  codigo: number
  descricao: string | null
}

export interface CnaeGroup {
  label: string
  cnaes: CnaeItem[]
}

export interface SocioOut {
  nome_socio: string | null
  cpf_cnpj_socio: string | null
  qualificacao: number | null
  qualificacao_descricao: string | null
  data_entrada: string | null
  faixa_etaria: number | null
}

export interface SimplesOut {
  opcao_simples: string | null
  data_opcao_simples: string | null
  data_exc_simples: string | null
  opcao_mei: string | null
  data_opcao_mei: string | null
  data_exc_mei: string | null
}

export interface EmpresaDetail {
  cnpj_basico: string
  cnpj_ordem: string
  cnpj_dv: string
  cnpj_completo: string
  razao_social: string
  nome_fantasia: string | null
  situacao_cadastral: number | null
  data_situacao: string | null
  motivo_situacao: number | null
  porte: number | null
  natureza_juridica: number | null
  ente_federativo: string | null
  data_inicio: string | null
  matriz_filial: number | null
  tipo_logradouro: string | null
  logradouro: string | null
  numero: string | null
  complemento: string | null
  bairro: string | null
  cep: string | null
  uf: string | null
  municipio: number | null
  municipio_descricao: string | null
  capital_social: number | null
  email: string | null
  telefone1: string | null
  telefone2: string | null
  fax: string | null
  cnae_principal: number | null
  cnae_principal_descricao: string | null
  cnae_secundarios: CnaeItem[]
  socios: SocioOut[]
  simples: SimplesOut | null
}

export interface Filters {
  cnpj?: string
  uf?: string
  municipio?: number
  bairro?: string
  cnaes?: number[]
  situacao_cadastral?: number
  porte?: number[]
  excluir_mei?: boolean
  capital_social_min?: number
  capital_social_max?: number
  matriz_filial?: number
  data_inicio_min?: string
  data_inicio_max?: string
  opcao_simples?: boolean
  natureza_juridica?: number
  cursor_cnpj_basico?: string
  cursor_cnpj_ordem?: string
  limit?: number
}

export interface StatusResponse {
  total_empresas: number
  total_estabelecimentos: number
  etl_files: Array<{
    arquivo: string
    status: string
    loaded_at: string | null
  }>
}

export const searchEmpresas = (filters: Filters): Promise<EmpresaOut[]> =>
  api.get<EmpresaOut[]>('/prospecting', { params: filters }).then(r => r.data)

export const getEmpresa = (cnpj: string): Promise<EmpresaDetail> =>
  api.get<EmpresaDetail>(`/empresa/${cnpj}`).then(r => r.data)

export interface BairroItem {
  bairro: string
  municipio: number | null
  municipio_descricao: string | null
}

export const getBairros = (uf: string, q: string): Promise<BairroItem[]> =>
  api.get<BairroItem[]>('/bairros', { params: { uf, q } }).then(r => r.data)

export const getCnaes = (): Promise<CnaeGroup[]> =>
  api.get<{ segments: CnaeGroup[] }>('/cnaes').then(r => r.data.segments)

export const getStatus = (): Promise<StatusResponse> =>
  api.get<StatusResponse>('/status').then(r => r.data)

export const buildExportCsvUrl = (filters: Filters): string => {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== '' && v !== null)
      .map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : String(v)])
  )
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/v1'
  return `${base}/export/csv?${params}`
}
