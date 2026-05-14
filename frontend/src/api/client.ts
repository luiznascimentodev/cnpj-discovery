import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/v1',
})

const paidHeaders = () => ({
  'X-Account-Id': import.meta.env.VITE_ACCOUNT_ID || 'development-account',
  'X-User-Id': import.meta.env.VITE_USER_ID || 'development-user',
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

export interface CnaeCatalog {
  all: CnaeItem[]
  segments: CnaeGroup[]
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

export interface CrawlerDomainOut {
  domain: string
  homepage_url: string | null
  source: string
  confidence: number
  status: string
  first_seen: string | null
  last_seen: string | null
}

export interface CrawlerContactOut {
  contact_type: string
  value: string
  normalized_value: string
  label: string | null
  source: string
  confidence: number
  evidence_url: string | null
  source_domain: string | null
  first_seen: string | null
  last_seen: string | null
}

export interface CrawlerEnrichmentOut {
  status: string
  domains: CrawlerDomainOut[]
  contacts: CrawlerContactOut[]
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
  enrichment_available: boolean
  enrichment_required_feature: string | null
  crawler_enrichment: CrawlerEnrichmentOut
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
  cursor_cnpj_basico?: string
  cursor_cnpj_ordem?: string
  limit?: number
}

export interface EnrichmentEstimateRequest {
  cnpjs?: string[]
  filters?: Filters
  max_items?: number
  stale_after_days?: number
}

export interface EnrichmentEstimateResponse {
  source_type: 'selection' | 'filter'
  requested_count: number
  eligible_count: number
  cache_hit_count: number
  new_count: number
  skipped_inactive_count: number
  cost_credits: number
  estimated_seconds_min: number
  estimated_seconds_max: number
}

export interface EnrichmentJobResponse extends EnrichmentEstimateResponse {
  job_id: number
  status: string
  idempotency_key: string | null
  created_at: string | null
}

export interface EnrichmentJobSummary {
  id: number
  status: string
  source_type: 'selection' | 'filter'
  requested_count: number
  accepted_count: number
  cache_hit_count: number
  skipped_count: number
  failed_count: number
  ready_count: number
  cost_credits: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  cancelled_at: string | null
}

export interface EnrichmentJobItem {
  cnpj: string
  status: string
  result_source: string | null
  attempts: number
  last_error: string | null
  updated_at: string | null
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

const buildParams = (filters: Filters): URLSearchParams => {
  const params = new URLSearchParams()

  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === '' || value === null) {
      return
    }

    if (Array.isArray(value)) {
      value.forEach(item => params.append(key, String(item)))
      return
    }

    params.set(key, String(value))
  })

  return params
}

export const searchEmpresas = (filters: Filters): Promise<EmpresaOut[]> =>
  api.get<EmpresaOut[]>('/prospecting', { params: buildParams(filters) }).then(r => r.data)

export const getEmpresa = (cnpj: string): Promise<EmpresaDetail> =>
  api.get<EmpresaDetail>(`/empresa/${cnpj}`).then(r => r.data)

export interface BairroItem {
  bairro: string
  municipio: number | null
  municipio_descricao: string | null
}

export interface MunicipioItem {
  codigo: number
  descricao: string
  total_estabelecimentos: number
}

export const getBairros = (uf: string, q: string, municipio?: number): Promise<BairroItem[]> =>
  api.get<BairroItem[]>('/bairros', { params: { uf, q, municipio } }).then(r => r.data)

export const getMunicipios = (uf: string, q: string): Promise<MunicipioItem[]> =>
  api.get<MunicipioItem[]>('/municipios', { params: { uf, q } }).then(r => r.data)

export const getCnaes = (): Promise<CnaeCatalog> =>
  api.get<CnaeCatalog>('/cnaes').then(r => r.data)

export const getStatus = (): Promise<StatusResponse> =>
  api.get<StatusResponse>('/status').then(r => r.data)

export const estimateEnrichment = (payload: EnrichmentEstimateRequest): Promise<EnrichmentEstimateResponse> =>
  api.post<EnrichmentEstimateResponse>('/paid/enrichment/estimate', payload, { headers: paidHeaders() }).then(r => r.data)

export const createEnrichmentJob = (payload: EnrichmentEstimateRequest): Promise<EnrichmentJobResponse> =>
  api.post<EnrichmentJobResponse>('/paid/enrichment/jobs', payload, {
    headers: {
      ...paidHeaders(),
      'Idempotency-Key': `job-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    },
  }).then(r => r.data)

export const listEnrichmentJobs = (): Promise<EnrichmentJobSummary[]> =>
  api.get<{ jobs: EnrichmentJobSummary[] }>('/paid/enrichment/jobs', { headers: paidHeaders() }).then(r => r.data.jobs)

export const listEnrichmentJobItems = (jobId: number): Promise<EnrichmentJobItem[]> =>
  api.get<{ items: EnrichmentJobItem[] }>(`/paid/enrichment/jobs/${jobId}/items`, { headers: paidHeaders() }).then(r => r.data.items)

export const cancelEnrichmentJob = (jobId: number): Promise<void> =>
  api.post(`/paid/enrichment/jobs/${jobId}/cancel`, null, { headers: paidHeaders() }).then(() => undefined)

export const buildExportCsvUrl = (filters: Filters): string => {
  const exportFilters = { ...filters }
  delete exportFilters.cursor_cnpj_basico
  delete exportFilters.cursor_cnpj_ordem
  const params = buildParams(exportFilters)
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/v1'
  return `${base}/export/csv?${params}`
}
