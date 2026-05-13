import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { MunicipioItem } from '../api/client'
import { getMunicipios } from '../api/client'

export interface CitySelection {
  municipio?: number
  descricao: string
}

interface Props {
  uf: string
  value: string
  onChange: (selection: CitySelection) => void
}

export function CityAutocomplete({ uf, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const trimmed = value.trim()
  const { data = [] } = useQuery({
    queryKey: ['municipios', uf, trimmed],
    queryFn: () => getMunicipios(uf, trimmed),
    enabled: !!uf && trimmed.length >= 2,
    staleTime: 1000 * 60 * 60,
  })

  const handleInput = (v: string) => {
    setOpen(true)
    onChange({ descricao: v.trim() ? v : '' })
  }

  const handleSelect = (item: MunicipioItem) => {
    onChange({ municipio: item.codigo, descricao: item.descricao })
    setOpen(false)
  }

  const disabled = !uf

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={value}
        disabled={disabled}
        onChange={e => handleInput(e.target.value)}
        onFocus={() => data.length > 0 && setOpen(true)}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
        placeholder={disabled ? 'Selecione uma UF primeiro' : 'Digite e selecione a cidade'}
        autoComplete="off"
      />
      {open && data.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
          {data.map(item => (
            <li
              key={item.codigo}
              onMouseDown={() => handleSelect(item)}
              className="cursor-pointer px-3 py-1.5 text-sm hover:bg-blue-50"
            >
              <span className="font-medium text-gray-900">{item.descricao}</span>
              {item.total_estabelecimentos > 0 && (
                <span className="ml-2 text-xs text-gray-500">
                  {item.total_estabelecimentos.toLocaleString('pt-BR')}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
