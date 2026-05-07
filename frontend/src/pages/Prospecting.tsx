import { Download } from 'lucide-react'
import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { buildExportCsvUrl, searchEmpresas, type EmpresaOut, type Filters } from '../api/client'
import { CompanyDetailModal } from '../components/CompanyDetailModal'
import { FilterPanel } from '../components/FilterPanel'
import { ResultsTable } from '../components/ResultsTable'

const DEFAULT_LIMIT = 50

const getCursorFromCnpj = (cnpj: string): Pick<Filters, 'cursor_cnpj_basico' | 'cursor_cnpj_ordem'> => ({
  cursor_cnpj_basico: cnpj.slice(0, 8),
  cursor_cnpj_ordem: cnpj.slice(8, 12),
})

export function Prospecting() {
  const [currentFilters, setCurrentFilters] = useState<Filters>({ situacao_cadastral: 2 })
  const [allResults, setAllResults] = useState<EmpresaOut[]>([])
  const [selectedCnpj, setSelectedCnpj] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [lastPageSize, setLastPageSize] = useState(0)
  const requestRef = useRef<{ filters: Filters; append: boolean }>({
    filters: { situacao_cadastral: 2, limit: DEFAULT_LIMIT },
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

  const runSearch = (filters: Filters, append: boolean) => {
    const nextFilters = { ...filters, limit: filters.limit ?? DEFAULT_LIMIT }
    setCurrentFilters(nextFilters)
    requestRef.current = { filters: nextFilters, append }
    void refetch()
  }

  const handleSearch = (filters: Filters) => {
    setAllResults([])
    setLastPageSize(0)
    setSearched(true)
    runSearch(filters, false)
  }

  const handleLoadMore = () => {
    const lastItem = allResults.at(-1)

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

  const hasMore = searched && lastPageSize === (currentFilters.limit ?? DEFAULT_LIMIT)

  return (
    <div className="min-h-screen bg-white text-gray-900 lg:flex">
      <FilterPanel onSearch={handleSearch} loading={isFetching} />

      <main className="min-w-0 flex-1 p-5 lg:p-8">
        <div className="mb-5 flex flex-col gap-3 border-b border-gray-200 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-gray-900">Empresas</h2>
            <p className="mt-1 text-sm text-gray-500">
              {searched ? `${allResults.length.toLocaleString('pt-BR')} resultado(s)` : 'Pronto para consulta'}
            </p>
          </div>

          <a
            href={buildExportCsvUrl(currentFilters)}
            className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white ${
              searched && allResults.length > 0
                ? 'bg-green-600 hover:bg-green-700'
                : 'pointer-events-none bg-gray-300'
            }`}
            aria-disabled={!searched || allResults.length === 0}
          >
            <Download className="h-4 w-4" />
            Export CSV
          </a>
        </div>

        <ResultsTable
          data={allResults}
          onLoadMore={handleLoadMore}
          hasMore={hasMore}
          searched={searched}
          onSelectEmpresa={setSelectedCnpj}
        />
      </main>
      <CompanyDetailModal cnpj={selectedCnpj} onClose={() => setSelectedCnpj(null)} />
    </div>
  )
}
