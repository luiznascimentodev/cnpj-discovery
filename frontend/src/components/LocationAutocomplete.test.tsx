import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type React from 'react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BairroAutocomplete } from './BairroAutocomplete'
import { CityAutocomplete } from './CityAutocomplete'
import { getBairros, getMunicipios } from '../api/client'

vi.mock('../api/client', () => ({
  getBairros: vi.fn(),
  getMunicipios: vi.fn(),
}))

const renderWithQueryClient = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  )
}

function CityHarness({ uf, onChange }: { uf: string; onChange: (selection: unknown) => void }) {
  const [value, setValue] = useState('')

  return (
    <CityAutocomplete
      uf={uf}
      value={value}
      onChange={selection => {
        setValue(selection.descricao)
        onChange(selection)
      }}
    />
  )
}

function BairroHarness({ uf, municipio, onChange }: { uf: string; municipio?: number; onChange: (selection: unknown) => void }) {
  const [value, setValue] = useState('')

  return (
    <BairroAutocomplete
      uf={uf}
      municipio={municipio}
      value={value}
      onChange={selection => {
        setValue(selection.bairro)
        onChange(selection)
      }}
    />
  )
}

describe('CityAutocomplete', () => {
  beforeEach(() => {
    vi.mocked(getMunicipios).mockReset()
  })

  it('is disabled until UF is selected', () => {
    renderWithQueryClient(<CityAutocomplete uf="" value="" onChange={vi.fn()} />)

    expect(screen.getByPlaceholderText('Selecione uma UF primeiro')).toBeDisabled()
    expect(getMunicipios).not.toHaveBeenCalled()
  })

  it('queries municipalities by UF and search text, then emits the selected city', async () => {
    const onChange = vi.fn()
    vi.mocked(getMunicipios).mockResolvedValue([
      { codigo: 3550308, descricao: 'SAO PAULO', total_estabelecimentos: 1200000 },
    ])

    renderWithQueryClient(<CityHarness uf="SP" onChange={onChange} />)

    fireEvent.change(screen.getByPlaceholderText('Digite e selecione a cidade'), { target: { value: 'sao' } })

    await waitFor(() => {
      expect(getMunicipios).toHaveBeenCalledWith('SP', 'sao')
    })

    fireEvent.mouseDown(await screen.findByText('SAO PAULO'))

    expect(onChange).toHaveBeenLastCalledWith({ municipio: 3550308, descricao: 'SAO PAULO' })
  })
})

describe('BairroAutocomplete', () => {
  beforeEach(() => {
    vi.mocked(getBairros).mockReset()
  })

  it('is disabled until UF and city are selected', () => {
    renderWithQueryClient(<BairroAutocomplete uf="SP" value="" onChange={vi.fn()} />)

    expect(screen.getByPlaceholderText('Selecione uma cidade primeiro')).toBeDisabled()
    expect(getBairros).not.toHaveBeenCalled()
  })

  it('queries bairros by UF, municipality, and search text', async () => {
    const onChange = vi.fn()
    vi.mocked(getBairros).mockResolvedValue([
      { bairro: 'CENTRO', municipio: null, municipio_descricao: null },
    ])

    renderWithQueryClient(<BairroHarness uf="SP" municipio={3550308} onChange={onChange} />)

    fireEvent.change(screen.getByPlaceholderText('Digite e selecione o bairro'), { target: { value: 'cen' } })

    await waitFor(() => {
      expect(getBairros).toHaveBeenCalledWith('SP', 'cen', 3550308)
    })

    fireEvent.mouseDown(await screen.findByText('CENTRO'))

    expect(onChange).toHaveBeenLastCalledWith({ bairro: 'CENTRO' })
  })
})
