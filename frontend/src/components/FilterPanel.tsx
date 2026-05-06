import { useState, type FormEvent } from 'react'
import { Loader2, RotateCcw, Search } from 'lucide-react'
import type { Filters } from '../api/client'

interface Props {
  onSearch: (filters: Filters) => void
  loading: boolean
}

const UFS = [
  'AC',
  'AL',
  'AP',
  'AM',
  'BA',
  'CE',
  'DF',
  'ES',
  'GO',
  'MA',
  'MT',
  'MS',
  'MG',
  'PA',
  'PB',
  'PR',
  'PE',
  'PI',
  'RJ',
  'RN',
  'RS',
  'RO',
  'RR',
  'SC',
  'SP',
  'SE',
  'TO',
]

const DEFAULT_FILTERS: Filters = {
  situacao_cadastral: 2,
}

export function FilterPanel({ onSearch, loading }: Props) {
  const [buscaRazao, setBuscaRazao] = useState('')
  const [uf, setUf] = useState('')
  const [cnaePrincipal, setCnaePrincipal] = useState('')
  const [porte, setPorte] = useState('')
  const [excluirMei, setExcluirMei] = useState(false)
  const [capitalSocialMin, setCapitalSocialMin] = useState('')

  const selectedPorte = porte ? Number(porte) : undefined
  const meiSelected = selectedPorte === 1

  const buildFilters = (): Filters => ({
    ...DEFAULT_FILTERS,
    ...(buscaRazao.trim() && { busca_razao: buscaRazao.trim() }),
    ...(uf && { uf }),
    ...(cnaePrincipal && { cnae_principal: Number(cnaePrincipal) }),
    ...(selectedPorte && { porte: selectedPorte }),
    ...(!meiSelected && excluirMei && { excluir_mei: true }),
    ...(capitalSocialMin && { capital_social_min: Number(capitalSocialMin) }),
  })

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSearch(buildFilters())
  }

  const handleClear = () => {
    setBuscaRazao('')
    setUf('')
    setCnaePrincipal('')
    setPorte('')
    setExcluirMei(false)
    setCapitalSocialMin('')
    onSearch(DEFAULT_FILTERS)
  }

  return (
    <aside className="h-full w-full border-r border-gray-200 bg-gray-50 p-5 lg:w-80">
      <form className="flex h-full flex-col gap-5" onSubmit={handleSubmit}>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">CNPJ Discovery</h1>
          <p className="mt-1 text-sm text-gray-500">Prospecção de empresas</p>
        </div>

        <label className="flex flex-col gap-2 text-sm font-medium text-gray-700">
          Razão social ou fantasia
          <input
            type="text"
            value={buscaRazao}
            onChange={event => setBuscaRazao(event.target.value)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="Buscar empresa"
          />
        </label>

        <label className="flex flex-col gap-2 text-sm font-medium text-gray-700">
          UF
          <select
            value={uf}
            onChange={event => setUf(event.target.value)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">Todos</option>
            {UFS.map(item => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-2 text-sm font-medium text-gray-700">
          CNAE principal
          <input
            type="number"
            inputMode="numeric"
            min="0"
            value={cnaePrincipal}
            onChange={event => setCnaePrincipal(event.target.value)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="ex: 6201500"
          />
        </label>

        <label className="flex flex-col gap-2 text-sm font-medium text-gray-700">
          Porte
          <select
            value={porte}
            onChange={event => {
              const nextPorte = event.target.value
              setPorte(nextPorte)
              if (nextPorte === '1') {
                setExcluirMei(false)
              }
            }}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">Todos</option>
            <option value="1">MEI</option>
            <option value="2">ME</option>
            <option value="3">EPP</option>
            <option value="5">Demais</option>
          </select>
        </label>

        <label className="flex items-center gap-3 text-sm font-medium text-gray-700">
          <input
            type="checkbox"
            checked={!meiSelected && excluirMei}
            disabled={meiSelected}
            onChange={event => setExcluirMei(event.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
          />
          Excluir MEI
        </label>

        <label className="flex flex-col gap-2 text-sm font-medium text-gray-700">
          Capital Mínimo (R$)
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="0.01"
            value={capitalSocialMin}
            onChange={event => setCapitalSocialMin(event.target.value)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="0,00"
          />
        </label>

        <div className="mt-auto grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={handleClear}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            <RotateCcw className="h-4 w-4" />
            Limpar
          </button>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Buscar
          </button>
        </div>
      </form>
    </aside>
  )
}
