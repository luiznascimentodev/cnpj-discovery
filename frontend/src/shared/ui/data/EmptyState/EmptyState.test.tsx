import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState } from './EmptyState'
import { Inbox } from '@/shared/ui/icons'

describe('EmptyState', () => {
  it('renderiza título, descrição e ação', () => {
    render(<EmptyState icon={Inbox} title="vazio" description="adicione algo" action={<button>adicionar</button>} />)
    expect(screen.getByText('vazio')).toBeInTheDocument()
    expect(screen.getByText('adicione algo')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'adicionar' })).toBeInTheDocument()
  })
})
