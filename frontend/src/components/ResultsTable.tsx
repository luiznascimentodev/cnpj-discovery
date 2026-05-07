import { useState } from 'react'
import type { EmpresaOut } from '../api/client'

interface Props {
  data: EmpresaOut[]
  onLoadMore: () => void
  hasMore: boolean
  searched: boolean
  onSelectEmpresa: (cnpj: string) => void
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

export function ResultsTable({ data, onLoadMore, hasMore, searched, onSelectEmpresa }: Props) {
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
  const pageItems = getPageItems(safePage, totalPages)
  const showingStart = startIndex + 1
  const showingEnd = Math.min(startIndex + LOCAL_PAGE_SIZE, data.length)

  return (
    <div className="overflow-hidden rounded-md border border-gray-200 bg-white">
      <div className="max-h-[calc(100vh-12rem)] overflow-auto">
        <table className="min-w-[1280px] w-full table-fixed divide-y divide-gray-200 text-sm">
          <thead className="sticky top-0 z-10 bg-gray-100">
            <tr>
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
              <th className="w-24 px-4 py-3 text-left font-semibold text-gray-700">Porte</th>
              <th className="w-40 px-4 py-3 text-right font-semibold text-gray-700">Capital Social</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {pageRows.map(row => (
              <tr key={row.cnpj_completo} className="cursor-pointer hover:bg-blue-50" onClick={() => onSelectEmpresa(row.cnpj_completo)}>
                <td className="px-4 py-3 text-gray-700">{row.cnpj_completo}</td>
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
