import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useCnaes } from '../hooks/useCnaes'

interface Props {
  selected: number[]
  onChange: (codes: number[]) => void
}

export function CnaeSelector({ selected, onChange }: Props) {
  const { data, isLoading } = useCnaes()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    if (!data) return []
    const query = q.trim().toLowerCase()
    if (!query) return data
    return data
      .map(group => ({
        ...group,
        cnaes: group.cnaes.filter(
          c => String(c.codigo).includes(query) || (c.descricao || '').toLowerCase().includes(query)
        ),
      }))
      .filter(group => group.cnaes.length > 0)
  }, [data, q])

  const toggle = (code: number) => {
    if (selected.includes(code)) onChange(selected.filter(item => item !== code))
    else onChange([...selected, code])
  }

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
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            className="mb-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Buscar por código ou descrição"
          />
          <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
            {isLoading && <p className="text-xs text-gray-500">Carregando...</p>}
            {filtered.map(group => (
              <div key={group.label}>
                <p className="mb-1 text-xs font-semibold text-gray-600">{group.label}</p>
                <div className="space-y-1">
                  {group.cnaes.map(c => (
                    <label key={c.codigo} className="flex items-start gap-2 text-xs text-gray-700">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4"
                        checked={selected.includes(c.codigo)}
                        onChange={() => toggle(c.codigo)}
                      />
                      <span>
                        <span className="font-mono">{c.codigo}</span> {c.descricao ? `— ${c.descricao}` : ''}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
