import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ResultsTable } from './ResultsTable'
import type { EmpresaOut } from '@/shared/api'

const row = (cnpj: string): EmpresaOut => ({
  cnpj_basico: cnpj.slice(0, 8),
  cnpj_ordem: cnpj.slice(8, 12),
  cnpj_dv: cnpj.slice(12),
  cnpj_completo: cnpj,
  razao_social: `Empresa ${cnpj}`,
  nome_fantasia: null,
  situacao_cadastral: 2,
  cnae_principal: 6201500,
  cnae_descricao: 'Software',
  uf: 'SP',
  municipio: 3550308,
  municipio_descricao: 'Sao Paulo',
  bairro: 'Centro',
  email: 'contato@test.com',
  telefone1: '11999999999',
  porte: 3,
  capital_social: 1000,
  data_inicio: '2020-01-02',
})

describe('ResultsTable', () => {
  it('renders empty states', () => {
    const props = {
      data: [],
      onLoadMore: vi.fn(),
      hasMore: false,
      searched: false,
      onSelectEmpresa: vi.fn(),
      selectedCnpjs: new Set<string>(),
      onToggleEmpresa: vi.fn(),
      onTogglePage: vi.fn(),
    }

    render(<ResultsTable {...props} />)

    expect(screen.getByText('Use os filtros para buscar empresas.')).toBeInTheDocument()
  })

  it('supports row selection without opening details', () => {
    const onToggleEmpresa = vi.fn()
    const onSelectEmpresa = vi.fn()
    const data = [row('12345678000190')]

    render(
      <ResultsTable
        data={data}
        onLoadMore={vi.fn()}
        hasMore={false}
        searched
        onSelectEmpresa={onSelectEmpresa}
        selectedCnpjs={new Set()}
        onToggleEmpresa={onToggleEmpresa}
        onTogglePage={vi.fn()}
      />
    )

    fireEvent.click(screen.getByLabelText('Selecionar 12345678000190'))

    expect(onToggleEmpresa).toHaveBeenCalledWith('12345678000190')
    expect(onSelectEmpresa).not.toHaveBeenCalled()
  })

  it('supports page selection and load more', () => {
    const onTogglePage = vi.fn()
    const onLoadMore = vi.fn()
    const data = [row('12345678000190')]

    render(
      <ResultsTable
        data={data}
        onLoadMore={onLoadMore}
        hasMore
        searched
        onSelectEmpresa={vi.fn()}
        selectedCnpjs={new Set(['12345678000190'])}
        onToggleEmpresa={vi.fn()}
        onTogglePage={onTogglePage}
      />
    )

    fireEvent.click(screen.getByLabelText('Selecionar pagina'))
    fireEvent.click(screen.getByText('Carregar mais'))

    expect(onTogglePage).toHaveBeenCalledWith(['12345678000190'], false)
    expect(onLoadMore).toHaveBeenCalledOnce()
  })
})
