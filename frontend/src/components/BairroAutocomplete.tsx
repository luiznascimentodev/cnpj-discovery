import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { BairroItem } from '../api/client'
import { getBairros } from '../api/client'

export interface BairroSelection {
  bairro: string
  municipio?: number
}

interface Props {
  uf: string
  value: string
  onChange: (selection: BairroSelection) => void
}

function labelFor(item: BairroItem): string {
  return item.municipio_descricao ? `${item.bairro} · ${item.municipio_descricao}` : item.bairro
}

export function BairroAutocomplete({ uf, value, onChange }: Props) {
  const [q, setQ] = useState(value)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setQ(value) }, [value])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const trimmed = q.trim()
  const { data = [] } = useQuery({
    queryKey: ['bairros', uf, trimmed],
    queryFn: () => getBairros(uf, trimmed),
    enabled: !!uf && trimmed.length >= 2,
    staleTime: 1000 * 60 * 60,
  })

  const handleInput = (v: string) => {
    setQ(v)
    setOpen(true)
    if (!v.trim()) onChange({ bairro: '' })
  }

  const handleSelect = (item: BairroItem) => {
    setQ(labelFor(item))
    onChange({
      bairro: item.bairro,
      ...(item.municipio !== null && { municipio: item.municipio }),
    })
    setOpen(false)
  }

  const disabled = !uf

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={q}
        disabled={disabled}
        onChange={e => handleInput(e.target.value)}
        onFocus={() => data.length > 0 && setOpen(true)}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
        placeholder={disabled ? 'Selecione uma UF primeiro' : 'Digite o bairro…'}
        autoComplete="off"
      />
      {open && data.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
          {data.map((item, i) => (
            <li
              key={`${item.bairro}-${item.municipio ?? i}`}
              onMouseDown={() => handleSelect(item)}
              className="cursor-pointer px-3 py-1.5 text-sm hover:bg-blue-50"
            >
              {labelFor(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
