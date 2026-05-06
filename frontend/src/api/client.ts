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
  email: string | null
  telefone1: string | null
  porte: number | null
  capital_social: number | null
  data_inicio: string | null
}

export interface Filters {
  uf?: string
  municipio?: number
  cnae_principal?: number
  situacao_cadastral?: number
  porte?: number
  excluir_mei?: boolean
  capital_social_min?: number
  capital_social_max?: number
  busca_razao?: string
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

export const getStatus = (): Promise<StatusResponse> =>
  api.get<StatusResponse>('/status').then(r => r.data)

export const buildExportCsvUrl = (filters: Filters): string => {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== '' && v !== null)
      .map(([k, v]) => [k, String(v)])
  )
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/v1'
  return `${base}/export/csv?${params}`
}
