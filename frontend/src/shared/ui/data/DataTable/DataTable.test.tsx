import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataTable } from './DataTable'

interface Row { id: string; name: string }
const cols = [{ accessorKey: 'name', header: 'Nome' }] as const

describe('DataTable', () => {
  it('renderiza header', () => {
    render(<DataTable<Row> data={[{ id: '1', name: 'A' }]} columns={cols as unknown as never} rowKey={(r) => r.id} />)
    expect(screen.getByText('Nome')).toBeInTheDocument()
  })
  it('mostra empty message quando data vazio', () => {
    render(<DataTable<Row> data={[]} columns={cols as unknown as never} rowKey={(r) => r.id} emptyMessage="vazio" />)
    expect(screen.getByText('vazio')).toBeInTheDocument()
  })
  it('expõe aria-busy quando loading', () => {
    render(<DataTable<Row> data={[]} columns={cols as unknown as never} rowKey={(r) => r.id} loading />)
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true')
  })
})
