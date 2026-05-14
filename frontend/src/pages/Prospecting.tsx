import { CheckSquare, Download, ListChecks, Play, RefreshCw, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  buildExportCsvUrl,
  cancelEnrichmentJob,
  createEnrichmentJob,
  estimateEnrichment,
  listEnrichmentJobItems,
  listEnrichmentJobs,
  searchEmpresas,
  type EmpresaOut,
  type EnrichmentEstimateRequest,
  type EnrichmentEstimateResponse,
  type EnrichmentJobSummary,
  type Filters,
} from '@/shared/api'
import { CompanyDetailModal } from '../components/CompanyDetailModal'
import { FilterPanel } from '../components/FilterPanel'
import { ResultsTable } from '../components/ResultsTable'
import { cnpjFromCompanyPath, companyPath } from '../utils/companyRoutes'

const DEFAULT_PAGE_SIZE = 100

const getCursorFromCnpj = (cnpj: string): Pick<Filters, 'cursor_cnpj_basico' | 'cursor_cnpj_ordem'> => ({
  cursor_cnpj_basico: cnpj.slice(0, 8),
  cursor_cnpj_ordem: cnpj.slice(8, 12),
})

const getLastCursorEmpresa = (items: EmpresaOut[]): EmpresaOut | undefined =>
  items.reduce<EmpresaOut | undefined>((last, item) => {
    if (!last) return item
    return item.cnpj_completo > last.cnpj_completo ? item : last
  }, undefined)

export function Prospecting() {
  const [currentFilters, setCurrentFilters] = useState<Filters>({ limit: DEFAULT_PAGE_SIZE })
  const [exportFilters, setExportFilters] = useState<Filters>({ limit: DEFAULT_PAGE_SIZE })
  const [allResults, setAllResults] = useState<EmpresaOut[]>([])
  const [selectedCnpj, setSelectedCnpj] = useState<string | null>(() => cnpjFromCompanyPath())
  const [selectedCnpjs, setSelectedCnpjs] = useState<Set<string>>(new Set())
  const [selectCurrentFilter, setSelectCurrentFilter] = useState(false)
  const [estimate, setEstimate] = useState<EnrichmentEstimateResponse | null>(null)
  const [estimateOpen, setEstimateOpen] = useState(false)
  const [estimateLoading, setEstimateLoading] = useState(false)
  const [jobsOpen, setJobsOpen] = useState(false)
  const [jobs, setJobs] = useState<EnrichmentJobSummary[]>([])
  const [enrichmentStatuses, setEnrichmentStatuses] = useState<Record<string, string>>({})
  const [actionError, setActionError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [lastPageSize, setLastPageSize] = useState(0)
  const requestRef = useRef<{ filters: Filters; append: boolean }>({
    filters: { limit: DEFAULT_PAGE_SIZE },
    append: false,
  })

  const { isFetching, refetch } = useQuery({
    queryKey: ['prospecting'],
    enabled: false,
    queryFn: async () => {
      const { filters, append } = requestRef.current
      const results = await searchEmpresas(filters)

      setLastPageSize(results.length)
      setAllResults(previous => (append ? [...previous, ...results] : results))

      return results
    },
  })

  useEffect(() => {
    const handlePopState = () => setSelectedCnpj(cnpjFromCompanyPath())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const runSearch = (filters: Filters, append: boolean) => {
    setCurrentFilters(filters)
    requestRef.current = { filters, append }
    void refetch()
  }

  const handleSearch = (filters: Filters) => {
    setAllResults([])
    setLastPageSize(0)
    setSelectedCnpjs(new Set())
    setSelectCurrentFilter(false)
    setEstimate(null)
    setExportFilters(filters)
    setSearched(true)
    runSearch(filters, false)
  }

  const handleLoadMore = () => {
    const lastItem = getLastCursorEmpresa(allResults)

    if (!lastItem) {
      return
    }

    runSearch(
      {
        ...currentFilters,
        ...getCursorFromCnpj(lastItem.cnpj_completo),
      },
      true
    )
  }

  const handleSelectEmpresa = (empresa: EmpresaOut) => {
    window.history.pushState({}, '', companyPath(empresa))
    setSelectedCnpj(empresa.cnpj_completo)
  }

  const handleCloseEmpresa = () => {
    if (cnpjFromCompanyPath()) {
      window.history.pushState({}, '', '/')
    }
    setSelectedCnpj(null)
  }

  const toggleEmpresa = (cnpj: string) => {
    setSelectedCnpjs(previous => {
      const next = new Set(previous)
      if (next.has(cnpj)) next.delete(cnpj)
      else next.add(cnpj)
      return next
    })
    setSelectCurrentFilter(false)
    setEstimate(null)
  }

  const togglePage = (cnpjs: string[], selected: boolean) => {
    setSelectedCnpjs(previous => {
      const next = new Set(previous)
      cnpjs.forEach(cnpj => {
        if (selected) next.add(cnpj)
        else next.delete(cnpj)
      })
      return next
    })
    setSelectCurrentFilter(false)
    setEstimate(null)
  }

  const enrichmentPayload = (singleCnpj?: string): EnrichmentEstimateRequest | null => {
    if (singleCnpj) return { cnpjs: [singleCnpj], max_items: 1, stale_after_days: 180 }
    if (selectCurrentFilter) return { filters: exportFilters, max_items: exportFilters.limit ?? 5000, stale_after_days: 180 }
    const cnpjs = [...selectedCnpjs]
    return cnpjs.length ? { cnpjs, max_items: cnpjs.length, stale_after_days: 180 } : null
  }

  const refreshJobs = async () => {
    const nextJobs = await listEnrichmentJobs()
    setJobs(nextJobs)
    const activeJob = nextJobs[0]
    if (!activeJob) return
    const items = await listEnrichmentJobItems(activeJob.id)
    setEnrichmentStatuses(previous => {
      const next = { ...previous }
      items.forEach(item => {
        next[item.cnpj] = item.status
      })
      return next
    })
  }

  const handleEstimate = async (singleCnpj?: string) => {
    const payload = enrichmentPayload(singleCnpj)
    if (!payload) return
    setEstimateLoading(true)
    setActionError(null)
    try {
      const nextEstimate = await estimateEnrichment(payload)
      setEstimate(nextEstimate)
      setEstimateOpen(true)
    } catch {
      setActionError('Não foi possível estimar o enrichment agora.')
    } finally {
      setEstimateLoading(false)
    }
  }

  const handleCreateJob = async (singleCnpj?: string) => {
    const payload = enrichmentPayload(singleCnpj)
    if (!payload) return
    setEstimateLoading(true)
    setActionError(null)
    try {
      const job = await createEnrichmentJob(payload)
      setEstimate(job)
      setEstimateOpen(false)
      setJobsOpen(true)
      await refreshJobs()
    } catch {
      setActionError('Não foi possível criar o job de enrichment.')
    } finally {
      setEstimateLoading(false)
    }
  }

  const handleCancelJob = async (jobId: number) => {
    await cancelEnrichmentJob(jobId)
    await refreshJobs()
  }

  const pageSize = currentFilters.limit ?? DEFAULT_PAGE_SIZE
  const hasMore = searched && lastPageSize === pageSize
  const selectedCount = selectCurrentFilter ? (exportFilters.limit ?? DEFAULT_PAGE_SIZE) : selectedCnpjs.size

  return (
    <div className="min-h-screen bg-white text-gray-900 lg:flex">
      <FilterPanel onSearch={handleSearch} loading={isFetching} />

      <main className="min-w-0 flex-1 p-5 lg:p-8">
        <div className="mb-5 flex flex-col gap-3 border-b border-gray-200 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-gray-900">Empresas</h2>
            <p className="mt-1 text-sm text-gray-500">
              {searched
                ? `${allResults.length.toLocaleString('pt-BR')} carregado(s)${hasMore ? ' — há mais resultados' : ''}`
                : 'Pronto para consulta'}
            </p>
          </div>

          {searched && (
            <div className="flex flex-col gap-2 sm:items-end">
              <a
                href={buildExportCsvUrl(exportFilters)}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
                title="Exporta todos os resultados que correspondem aos filtros atuais, não apenas os carregados na tela."
              >
                <Download className="h-4 w-4" />
                Exportar CSV completo
              </a>
              <span className="text-xs text-gray-500">
                Exporta 100% dos resultados desses filtros, não apenas os {allResults.length.toLocaleString('pt-BR')} carregados.
              </span>
            </div>
          )}
        </div>

        {searched && (
          <div className="mb-4 flex flex-col gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-gray-900">
                {selectCurrentFilter
                  ? `Filtro atual selecionado até ${selectedCount.toLocaleString('pt-BR')} empresas`
                  : `${selectedCnpjs.size.toLocaleString('pt-BR')} CNPJ(s) selecionado(s)`}
              </span>
              <button
                type="button"
                onClick={() => {
                  setSelectCurrentFilter(true)
                  setSelectedCnpjs(new Set())
                  setEstimate(null)
                }}
                className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-gray-700 hover:bg-white"
              >
                <CheckSquare className="h-4 w-4" />
                Usar filtro
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedCnpjs(new Set())
                  setSelectCurrentFilter(false)
                  setEstimate(null)
                }}
                className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-gray-700 hover:bg-white"
              >
                <X className="h-4 w-4" />
                Limpar
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={selectedCount === 0 || estimateLoading}
                onClick={() => handleEstimate()}
                className="inline-flex items-center gap-2 rounded-md border border-blue-200 px-3 py-1.5 font-medium text-blue-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw className="h-4 w-4" />
                Estimar
              </button>
              <button
                type="button"
                disabled={selectedCount === 0 || estimateLoading}
                onClick={() => handleCreateJob()}
                className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Play className="h-4 w-4" />
                Enriquecer
              </button>
              <button
                type="button"
                onClick={() => {
                  setJobsOpen(true)
                  void refreshJobs()
                }}
                className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-gray-700 hover:bg-white"
              >
                <ListChecks className="h-4 w-4" />
                Jobs
              </button>
            </div>
          </div>
        )}

        {actionError && <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>}

        <ResultsTable
          data={allResults}
          onLoadMore={handleLoadMore}
          hasMore={hasMore}
          searched={searched}
          onSelectEmpresa={handleSelectEmpresa}
          selectedCnpjs={selectedCnpjs}
          onToggleEmpresa={toggleEmpresa}
          onTogglePage={togglePage}
          enrichmentStatuses={enrichmentStatuses}
        />
      </main>
      <CompanyDetailModal cnpj={selectedCnpj} onClose={handleCloseEmpresa} onRequestEnrichment={cnpj => void handleCreateJob(cnpj)} />

      {estimateOpen && estimate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-lg rounded-md bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Estimativa de enrichment</h3>
                <p className="mt-1 text-sm text-gray-500">Confirme o lote antes de colocar o worker para rodar.</p>
              </div>
              <button type="button" onClick={() => setEstimateOpen(false)} className="rounded-md p-1 text-gray-500 hover:bg-gray-100">
                <X className="h-5 w-5" />
              </button>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-md bg-gray-50 p-3">
                <dt className="text-gray-500">Elegíveis</dt>
                <dd className="mt-1 text-lg font-semibold">{estimate.eligible_count.toLocaleString('pt-BR')}</dd>
              </div>
              <div className="rounded-md bg-gray-50 p-3">
                <dt className="text-gray-500">Cache</dt>
                <dd className="mt-1 text-lg font-semibold">{estimate.cache_hit_count.toLocaleString('pt-BR')}</dd>
              </div>
              <div className="rounded-md bg-gray-50 p-3">
                <dt className="text-gray-500">Crawler</dt>
                <dd className="mt-1 text-lg font-semibold">{estimate.new_count.toLocaleString('pt-BR')}</dd>
              </div>
              <div className="rounded-md bg-gray-50 p-3">
                <dt className="text-gray-500">Créditos</dt>
                <dd className="mt-1 text-lg font-semibold">{estimate.cost_credits.toLocaleString('pt-BR')}</dd>
              </div>
            </dl>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setEstimateOpen(false)} className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700">
                Cancelar
              </button>
              <button type="button" onClick={() => handleCreateJob()} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                Criar job
              </button>
            </div>
          </div>
        </div>
      )}

      {jobsOpen && (
        <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
            <h3 className="text-base font-semibold text-gray-900">Jobs de enrichment</h3>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => void refreshJobs()} className="rounded-md p-2 text-gray-500 hover:bg-gray-100">
                <RefreshCw className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setJobsOpen(false)} className="rounded-md p-2 text-gray-500 hover:bg-gray-100">
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto bg-gray-50 p-5">
            {jobs.length === 0 ? (
              <p className="rounded-md border border-dashed border-gray-300 bg-white p-5 text-sm text-gray-500">Nenhum job criado nesta conta.</p>
            ) : (
              <ul className="space-y-3">
                {jobs.map(job => (
                  <li key={job.id} className="rounded-md border border-gray-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-gray-900">Job #{job.id}</p>
                        <p className="mt-1 text-xs text-gray-500">
                          {job.status} · {job.ready_count.toLocaleString('pt-BR')}/{job.accepted_count.toLocaleString('pt-BR')} prontos
                        </p>
                      </div>
                      {job.status === 'queued' || job.status === 'running' ? (
                        <button
                          type="button"
                          onClick={() => void handleCancelJob(job.id)}
                          className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                        >
                          Cancelar
                        </button>
                      ) : null}
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className="h-full bg-blue-600"
                        style={{ width: `${job.accepted_count ? Math.min(100, (job.ready_count / job.accepted_count) * 100) : 0}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
