import { useState, type FormEvent } from 'react'
import { Loader2, RotateCcw, Search } from 'lucide-react'
import type { Filters } from '../api/client'
import type { BairroSelection } from './BairroAutocomplete'
import { BairroAutocomplete } from './BairroAutocomplete'
import { CnaeSelector } from './CnaeSelector'

interface Props {
  onSearch: (filters: Filters) => void
  loading: boolean
}

const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO']
const PORTES = [
  { value: 1, label: 'MEI' },
  { value: 2, label: 'ME' },
  { value: 3, label: 'EPP' },
  { value: 5, label: 'Demais' },
]
const RESULT_LIMITS = [50, 100, 500, 1000, 5000, 10000, 50000]

export function FilterPanel({ onSearch, loading }: Props) {
  const [cnpj, setCnpj] = useState('')
  const [uf, setUf] = useState('')
  const [bairro, setBairro] = useState('')
  const [municipioBairro, setMunicipioBairro] = useState<number | undefined>(undefined)

  const handleUfChange = (newUf: string) => {
    setUf(newUf)
    setBairro('')
    setMunicipioBairro(undefined)
  }

  const handleBairroChange = ({ bairro: b, municipio: mun }: BairroSelection) => {
    setBairro(b)
    setMunicipioBairro(mun)
  }
  const [selectedCnaes, setSelectedCnaes] = useState<number[]>([])
  const [portes, setPortes] = useState<number[]>([])
  const [excluirMei, setExcluirMei] = useState(false)
  const [capitalMin, setCapitalMin] = useState('')
  const [capitalMax, setCapitalMax] = useState('')
  const [matrizFilial, setMatrizFilial] = useState('')
  const [dataMin, setDataMin] = useState('')
  const [dataMax, setDataMax] = useState('')
  const [opcaoSimples, setOpcaoSimples] = useState(false)
  const [naturezaJuridica, setNaturezaJuridica] = useState('')
  const [resultLimit, setResultLimit] = useState(100)

  const cnpjMode = cnpj.trim().length > 0
  const meiInPortes = portes.includes(1)

  const togglePorte = (value: number) =>
    setPortes(prev => (prev.includes(value) ? prev.filter(p => p !== value) : [...prev, value]))

  const buildFilters = (): Filters => {
    if (cnpjMode) return { cnpj: cnpj.trim() }
    return {
      situacao_cadastral: 2,
      ...(uf && { uf }),
      ...(bairro.trim() && { bairro: bairro.trim() }),
      ...(municipioBairro !== undefined && { municipio: municipioBairro }),
      ...(selectedCnaes.length > 0 && { cnaes: selectedCnaes }),
      ...(portes.length > 0 && { porte: portes }),
      ...(!meiInPortes && excluirMei && { excluir_mei: true }),
      ...(capitalMin && { capital_social_min: Number(capitalMin) }),
      ...(capitalMax && { capital_social_max: Number(capitalMax) }),
      ...(matrizFilial && { matriz_filial: Number(matrizFilial) }),
      ...(dataMin && { data_inicio_min: dataMin }),
      ...(dataMax && { data_inicio_max: dataMax }),
      ...(opcaoSimples && { opcao_simples: true }),
      ...(naturezaJuridica && { natureza_juridica: Number(naturezaJuridica) }),
      limit: resultLimit,
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSearch(buildFilters())
  }

  const handleClear = () => {
    setCnpj('')
    setUf('')
    setBairro('')
    setMunicipioBairro(undefined)
    setSelectedCnaes([])
    setPortes([])
    setExcluirMei(false)
    setCapitalMin('')
    setCapitalMax('')
    setMatrizFilial('')
    setDataMin('')
    setDataMax('')
    setOpcaoSimples(false)
    setNaturezaJuridica('')
    setResultLimit(100)
    onSearch({ situacao_cadastral: 2, limit: 100 })
  }

  const inputClass = 'rounded-md border border-gray-300 bg-white px-3 py-2 text-sm'
  const labelClass = 'flex flex-col gap-2 text-sm font-medium text-gray-700'

  return (
    <aside className="h-full w-full border-r border-gray-200 bg-gray-50 p-5 lg:w-96">
      <form className="flex h-full flex-col gap-4" onSubmit={handleSubmit}>
        <label className={labelClass}>
          Buscar por CNPJ
          <input value={cnpj} onChange={e => setCnpj(e.target.value)} className={inputClass} placeholder="00.000.000/0001-00" />
          {cnpjMode && <span className="text-xs text-yellow-700">Demais filtros serão ignorados.</span>}
        </label>

        <div className={cnpjMode ? 'pointer-events-none opacity-50' : ''}>
          <label className={labelClass}>
            UF
            <select value={uf} onChange={e => handleUfChange(e.target.value)} className={inputClass}>
              <option value="">Todos</option>
              {UFS.map(x => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <div className={labelClass}>
            Bairro
            <BairroAutocomplete uf={uf} value={bairro} onChange={handleBairroChange} />
          </div>
          <div className={labelClass}>
            CNAE
            <CnaeSelector selected={selectedCnaes} onChange={setSelectedCnaes} />
          </div>
          <div className="text-sm font-medium text-gray-700">
            Porte
            <div className="mt-2 flex flex-wrap gap-3">
              {PORTES.map(p => (
                <label key={p.value} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={portes.includes(p.value)} onChange={() => togglePorte(p.value)} />
                  {p.label}
                </label>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={!meiInPortes && excluirMei} disabled={meiInPortes} onChange={e => setExcluirMei(e.target.checked)} />
            Excluir MEI
          </label>
          <div className={labelClass}>
            Capital social (R$)
            <div className="flex gap-2">
              <input type="number" value={capitalMin} onChange={e => setCapitalMin(e.target.value)} className={inputClass} />
              <input type="number" value={capitalMax} onChange={e => setCapitalMax(e.target.value)} className={inputClass} />
            </div>
          </div>
          <label className={labelClass}>
            Estabelecimento
            <select value={matrizFilial} onChange={e => setMatrizFilial(e.target.value)} className={inputClass}>
              <option value="">Todos</option>
              <option value="1">Somente Matriz</option>
              <option value="2">Somente Filial</option>
            </select>
          </label>
          <div className={labelClass}>
            Data de abertura
            <div className="flex gap-2">
              <input type="date" value={dataMin} onChange={e => setDataMin(e.target.value)} className={inputClass} />
              <input type="date" value={dataMax} onChange={e => setDataMax(e.target.value)} className={inputClass} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={opcaoSimples} onChange={e => setOpcaoSimples(e.target.checked)} />
            Somente Simples Nacional
          </label>
          <label className={labelClass}>
            Natureza jurídica
            <input type="number" value={naturezaJuridica} onChange={e => setNaturezaJuridica(e.target.value)} className={inputClass} />
          </label>
          <label className={labelClass}>
            Resultados na tela
            <select value={resultLimit} onChange={e => setResultLimit(Number(e.target.value))} className={inputClass}>
              {RESULT_LIMITS.map(value => (
                <option key={value} value={value}>
                  {value.toLocaleString('pt-BR')} resultados
                </option>
              ))}
            </select>
            <span className="rounded-md border border-yellow-200 bg-yellow-50 px-3 py-2 text-xs font-normal text-yellow-800">
              Quanto maior a quantidade, mais a busca pode demorar e consumir memória no navegador.
            </span>
          </label>
        </div>

        <div className="mt-auto grid grid-cols-2 gap-3">
          <button type="button" onClick={handleClear} className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm">
            <RotateCcw className="h-4 w-4" /> Limpar
          </button>
          <button type="submit" disabled={loading} className="inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm text-white">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Buscar
          </button>
        </div>
      </form>
    </aside>
  )
}
