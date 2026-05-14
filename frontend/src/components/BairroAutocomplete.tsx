import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { BairroItem } from '@/shared/api'
import { getBairros } from '@/shared/api'

export interface BairroSelection {
  bairro: string
  municipio?: number
}

interface Props {
  uf: string
  municipio?: number
  value: string
  onChange: (selection: BairroSelection) => void
}

export function BairroAutocomplete({ uf, municipio, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const trimmed = value.trim()
  const { data = [] } = useQuery({
    queryKey: ['bairros', uf, municipio, trimmed],
    queryFn: () => getBairros(uf, trimmed, municipio),
    enabled: !!uf && municipio !== undefined && trimmed.length >= 2,
    staleTime: 1000 * 60 * 60,
  })

  const handleInput = (v: string) => {
    setOpen(true)
    onChange({ bairro: v.trim() ? v : '' })
  }

  const handleSelect = (item: BairroItem) => {
    onChange({ bairro: item.bairro })
    setOpen(false)
  }

  const disabled = !uf || municipio === undefined

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={value}
        disabled={disabled}
        onChange={e => handleInput(e.target.value)}
        onFocus={() => data.length > 0 && setOpen(true)}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
        placeholder={!uf ? 'Selecione uma UF primeiro' : municipio === undefined ? 'Selecione uma cidade primeiro' : 'Digite e selecione o bairro'}
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
              {item.bairro}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
