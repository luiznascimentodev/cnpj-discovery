import { useState } from 'react'
import type { EmpresaOut } from '@/shared/api'
import { companyPath } from '../utils/companyRoutes'

interface Props {
  data: EmpresaOut[]
  onLoadMore: () => void
  hasMore: boolean
  searched: boolean
  onSelectEmpresa: (empresa: EmpresaOut) => void
  selectedCnpjs: Set<string>
  onToggleEmpresa: (cnpj: string) => void
  onTogglePage: (cnpjs: string[], selected: boolean) => void
  enrichmentStatuses: Record<string, string>
}

const porteLabels: Record<number, string> = {
  1: 'MEI',
  2: 'ME',
  3: 'EPP',
  5: 'Demais',
}

const formatCurrency = (value: number | null) =>
  value === null
    ? '-'
    : value.toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL',
      })

const formatPorte = (value: number | null) => (value === null ? '-' : porteLabels[value] ?? String(value))

const formatPhone = (value: string | null) => value || '-'

const formatDate = (value: string | null) => {
  if (!value) return '-'

  const [year, month, day] = value.split('-')
  return year && month && day ? `${day}/${month}/${year}` : value
}

const LOCAL_PAGE_SIZE = 100

const getPageItems = (currentPage: number, totalPages: number) => {
  const pages = new Set([1, totalPages])

  for (let page = currentPage - 2; page <= currentPage + 2; page += 1) {
    if (page >= 1 && page <= totalPages) pages.add(page)
  }

  const ordered = [...pages].sort((a, b) => a - b)
  return ordered.flatMap((page, index) => {
    const previous = ordered[index - 1]
    return previous && page - previous > 1 ? [`gap-${previous}-${page}`, page] : [page]
  })
}

const statusLabels: Record<string, string> = {
  pending: 'Processando',
  leased: 'Processando',
  cache_hit: 'Pronto',
  enriched: 'Pronto',
  no_public_contact: 'Sem contato',
  failed_retryable: 'Falhou',
  failed_terminal: 'Falhou',
  cancelled: 'Cancelado',
}

const statusClass = (status: string) => {
  if (status === 'cache_hit' || status === 'enriched') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (status === 'pending' || status === 'leased') return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (status === 'no_public_contact') return 'bg-gray-50 text-gray-600 ring-gray-200'
  if (status.startsWith('failed')) return 'bg-red-50 text-red-700 ring-red-200'
  return 'bg-gray-50 text-gray-600 ring-gray-200'
}

export function ResultsTable({
  data,
  onLoadMore,
  hasMore,
  searched,
  onSelectEmpresa,
  selectedCnpjs,
  onToggleEmpresa,
  onTogglePage,
  enrichmentStatuses,
}: Props) {
  const [currentPage, setCurrentPage] = useState(1)

  if (data.length === 0) {
    return (
      <div className="flex min-h-96 items-center justify-center rounded-md border border-dashed border-gray-300 bg-white text-sm text-gray-500">
        {searched ? 'Nenhum resultado encontrado.' : 'Use os filtros para buscar empresas.'}
      </div>
    )
  }

  const totalPages = Math.max(1, Math.ceil(data.length / LOCAL_PAGE_SIZE))
  const safePage = Math.min(currentPage, totalPages)
  const startIndex = (safePage - 1) * LOCAL_PAGE_SIZE
  const pageRows = data.slice(startIndex, startIndex + LOCAL_PAGE_SIZE)
  const pageCnpjs = pageRows.map(row => row.cnpj_completo)
  const selectedOnPage = pageCnpjs.filter(cnpj => selectedCnpjs.has(cnpj)).length
  const pageFullySelected = pageRows.length > 0 && selectedOnPage === pageRows.length
  const pageItems = getPageItems(safePage, totalPages)
  const showingStart = startIndex + 1
  const showingEnd = Math.min(startIndex + LOCAL_PAGE_SIZE, data.length)

  return (
    <div className="overflow-hidden rounded-md border border-gray-200 bg-white">
      <div className="max-h-[calc(100vh-12rem)] overflow-auto">
        <table className="min-w-[1280px] w-full table-fixed divide-y divide-gray-200 text-sm">
          <thead className="sticky top-0 z-10 bg-gray-100">
            <tr>
              <th className="w-12 px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={pageFullySelected}
                  ref={element => {
                    if (element) element.indeterminate = selectedOnPage > 0 && !pageFullySelected
                  }}
                  onChange={event => onTogglePage(pageCnpjs, event.currentTarget.checked)}
                  aria-label="Selecionar pagina"
                  className="h-4 w-4 rounded border-gray-300"
                />
              </th>
              <th className="w-36 px-4 py-3 text-left font-semibold text-gray-700">CNPJ</th>
              <th className="w-64 px-4 py-3 text-left font-semibold text-gray-700">Razão Social</th>
              <th className="w-52 px-4 py-3 text-left font-semibold text-gray-700">Fantasia</th>
              <th className="w-16 px-4 py-3 text-left font-semibold text-gray-700">UF</th>
              <th className="w-44 px-4 py-3 text-left font-semibold text-gray-700">Município</th>
              <th className="w-40 px-4 py-3 text-left font-semibold text-gray-700">Bairro</th>
              <th className="w-32 px-4 py-3 text-left font-semibold text-gray-700">CNAE</th>
              <th className="w-28 px-4 py-3 text-left font-semibold text-gray-700">Abertura</th>
              <th className="w-36 px-4 py-3 text-left font-semibold text-gray-700">Telefone</th>
              <th className="w-56 px-4 py-3 text-left font-semibold text-gray-700">E-mail</th>
              <th className="w-36 px-4 py-3 text-left font-semibold text-gray-700">Enrichment</th>
              <th className="w-24 px-4 py-3 text-left font-semibold text-gray-700">Porte</th>
              <th className="w-40 px-4 py-3 text-right font-semibold text-gray-700">Capital Social</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {pageRows.map(row => (
              <tr key={row.cnpj_completo} className="cursor-pointer hover:bg-blue-50" onClick={() => onSelectEmpresa(row)}>
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={selectedCnpjs.has(row.cnpj_completo)}
                    onClick={event => event.stopPropagation()}
                    onChange={() => onToggleEmpresa(row.cnpj_completo)}
                    aria-label={`Selecionar ${row.cnpj_completo}`}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                </td>
                <td className="px-4 py-3 text-gray-700">
                  <a
                    href={companyPath(row)}
                    onClick={event => {
                      event.preventDefault()
                      event.stopPropagation()
                      onSelectEmpresa(row)
                    }}
                    className="font-mono text-blue-700 hover:underline"
                  >
                    {row.cnpj_completo}
                  </a>
                </td>
                <td className="truncate px-4 py-3 font-medium text-gray-900" title={row.razao_social}>
                  {row.razao_social}
                </td>
                <td className="truncate px-4 py-3 text-gray-700" title={row.nome_fantasia ?? undefined}>
                  {row.nome_fantasia || '-'}
                </td>
                <td className="px-4 py-3 text-gray-700">{row.uf || '-'}</td>
                <td className="truncate px-4 py-3 text-gray-700" title={row.municipio_descricao ?? undefined}>
                  {row.municipio_descricao || '-'}
                </td>
                <td className="truncate px-4 py-3 text-gray-700" title={row.bairro ?? undefined}>
                  {row.bairro || '-'}
                </td>
                <td className="px-4 py-3 text-gray-700">{row.cnae_descricao || row.cnae_principal || '-'}</td>
                <td className="px-4 py-3 text-gray-700">{formatDate(row.data_inicio)}</td>
                <td className="px-4 py-3 text-gray-700">{formatPhone(row.telefone1)}</td>
                <td className="truncate px-4 py-3 text-gray-700" title={row.email ?? undefined}>
                  {row.email || '-'}
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded px-2 py-1 text-xs font-medium ring-1 ${statusClass(enrichmentStatuses[row.cnpj_completo] ?? 'none')}`}>
                    {statusLabels[enrichmentStatuses[row.cnpj_completo] ?? ''] ?? 'Não solicitado'}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-700">{formatPorte(row.porte)}</td>
                <td className="px-4 py-3 text-right text-gray-700">{formatCurrency(row.capital_social)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-3 border-t border-gray-200 p-4 text-sm text-gray-600 lg:flex-row lg:items-center lg:justify-between">
        <span>
          Mostrando {showingStart.toLocaleString('pt-BR')}-{showingEnd.toLocaleString('pt-BR')} de {data.length.toLocaleString('pt-BR')} carregados.
        </span>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentPage(page => Math.max(1, page - 1))}
            disabled={safePage === 1}
            className="rounded-md border border-gray-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Anterior
          </button>
          {pageItems.map(item =>
            typeof item === 'string' ? (
              <span key={item} className="px-2 text-gray-400">
                ...
              </span>
            ) : (
              <button
                key={item}
                type="button"
                onClick={() => setCurrentPage(item)}
                className={`rounded-md px-3 py-1 ${item === safePage ? 'bg-blue-600 text-white' : 'border border-gray-300 text-gray-700'}`}
              >
                {item}
              </button>
            )
          )}
          <button
            type="button"
            onClick={() => setCurrentPage(page => Math.min(totalPages, page + 1))}
            disabled={safePage === totalPages}
            className="rounded-md border border-gray-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Próxima
          </button>
        </div>

        {hasMore && (
          <button
            type="button"
            onClick={onLoadMore}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Carregar mais
          </button>
        )}
      </div>
    </div>
  )
}
