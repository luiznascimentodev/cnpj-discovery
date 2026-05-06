import type { EmpresaOut } from '../api/client'

interface Props {
  data: EmpresaOut[]
  onLoadMore: () => void
  hasMore: boolean
  searched: boolean
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

export function ResultsTable({ data, onLoadMore, hasMore, searched }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex min-h-96 items-center justify-center rounded-md border border-dashed border-gray-300 bg-white text-sm text-gray-500">
        {searched ? 'Nenhum resultado encontrado.' : 'Use os filtros para buscar empresas.'}
      </div>
    )
  }

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
              <th className="w-32 px-4 py-3 text-left font-semibold text-gray-700">CNAE</th>
              <th className="w-36 px-4 py-3 text-left font-semibold text-gray-700">Telefone</th>
              <th className="w-56 px-4 py-3 text-left font-semibold text-gray-700">E-mail</th>
              <th className="w-24 px-4 py-3 text-left font-semibold text-gray-700">Porte</th>
              <th className="w-40 px-4 py-3 text-right font-semibold text-gray-700">Capital Social</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {data.map(row => (
              <tr key={row.cnpj_completo} className="hover:bg-blue-50">
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
                <td className="px-4 py-3 text-gray-700">{row.cnae_principal ?? '-'}</td>
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

      {hasMore && (
        <div className="border-t border-gray-200 p-4 text-center">
          <button
            type="button"
            onClick={onLoadMore}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Carregar mais
          </button>
        </div>
      )}
    </div>
  )
}
