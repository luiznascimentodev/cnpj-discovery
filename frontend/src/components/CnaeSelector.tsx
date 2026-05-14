import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Layers, List } from 'lucide-react'
import { useCnaes } from '../hooks/useCnaes'

interface Props {
  selected: number[]
  onChange: (codes: number[]) => void
}

export function CnaeSelector({ selected, onChange }: Props) {
  const { data, isLoading } = useCnaes()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<'all' | 'segments'>('segments')

  const filteredGroups = useMemo(() => {
    if (!data) return []
    const query = q.trim().toLowerCase()
    if (!query) return data.segments
    return data.segments
      .map(group => ({
        ...group,
        cnaes: group.cnaes.filter(
          c => String(c.codigo).includes(query) || (c.descricao || '').toLowerCase().includes(query)
        ),
      }))
      .filter(group => group.cnaes.length > 0)
  }, [data, q])

  const filteredAll = useMemo(() => {
    if (!data) return []
    const query = q.trim().toLowerCase()
    if (!query) return data.all
    return data.all.filter(
      c => String(c.codigo).includes(query) || (c.descricao || '').toLowerCase().includes(query)
    )
  }, [data, q])

  const toggle = (code: number) => {
    if (selected.includes(code)) onChange(selected.filter(item => item !== code))
    else onChange([...selected, code])
  }

  const renderCnae = (cnae: { codigo: number; descricao: string | null }) => (
    <label key={cnae.codigo} className="flex items-start gap-2 text-xs text-gray-700">
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4"
        checked={selected.includes(cnae.codigo)}
        onChange={() => toggle(cnae.codigo)}
      />
      <span>
        <span className="font-mono">{cnae.codigo}</span> {cnae.descricao ? `- ${cnae.descricao}` : ''}
      </span>
    </label>
  )

  return (
    <div className="rounded-md border border-gray-300 bg-white">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm"
      >
        <span>{selected.length === 0 ? 'Selecionar CNAEs' : `${selected.length} CNAE(s) selecionado(s)`}</span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="border-t border-gray-200 p-3">
          <div className="mb-3 grid grid-cols-2 gap-2 rounded-md bg-gray-100 p-1">
            <button
              type="button"
              onClick={() => setMode('segments')}
              className={`inline-flex items-center justify-center gap-2 rounded px-2 py-1.5 text-xs font-medium ${mode === 'segments' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600'}`}
            >
              <Layers className="h-3.5 w-3.5" />
              Assuntos
            </button>
            <button
              type="button"
              onClick={() => setMode('all')}
              className={`inline-flex items-center justify-center gap-2 rounded px-2 py-1.5 text-xs font-medium ${mode === 'all' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600'}`}
            >
              <List className="h-3.5 w-3.5" />
              Todos
            </button>
          </div>
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            className="mb-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Buscar por código ou descrição"
          />
          <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
            {isLoading && <p className="text-xs text-gray-500">Carregando...</p>}
            {!isLoading && mode === 'all' && filteredAll.map(renderCnae)}
            {!isLoading && mode === 'segments' && filteredGroups.map(group => (
              <div key={group.label} className="rounded border border-gray-100 p-2">
                <p className="mb-2 text-xs font-semibold text-gray-700">{group.label}</p>
                <div className="space-y-1">
                  {group.cnaes.map(renderCnae)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
