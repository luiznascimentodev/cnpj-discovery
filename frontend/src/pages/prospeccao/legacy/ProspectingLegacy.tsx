import { Download } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  buildExportCsvUrl,
  searchEmpresas,
  type EmpresaOut,
  type Filters,
} from '@/shared/api'
import { CompanyDetailModal } from './components/CompanyDetailModal'
import { FilterPanel } from './components/FilterPanel'
import { ResultsTable } from './components/ResultsTable'
import { cnpjFromCompanyPath, companyPath } from './utils/companyRoutes'

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

export function ProspectingLegacy() {
  const [currentFilters, setCurrentFilters] = useState<Filters>({ limit: DEFAULT_PAGE_SIZE })
  const [exportFilters, setExportFilters] = useState<Filters>({ limit: DEFAULT_PAGE_SIZE })
  const [allResults, setAllResults] = useState<EmpresaOut[]>([])
  const [selectedCnpj, setSelectedCnpj] = useState<string | null>(() => cnpjFromCompanyPath())
  const [selectedCnpjs, setSelectedCnpjs] = useState<Set<string>>(new Set())
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
  }

  const pageSize = currentFilters.limit ?? DEFAULT_PAGE_SIZE
  const hasMore = searched && lastPageSize === pageSize

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

        <ResultsTable
          data={allResults}
          onLoadMore={handleLoadMore}
          hasMore={hasMore}
          searched={searched}
          onSelectEmpresa={handleSelectEmpresa}
          selectedCnpjs={selectedCnpjs}
          onToggleEmpresa={toggleEmpresa}
          onTogglePage={togglePage}
        />
      </main>
      <CompanyDetailModal cnpj={selectedCnpj} onClose={handleCloseEmpresa} />
    </div>
  )
}
