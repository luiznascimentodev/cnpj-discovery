import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Pagination } from './Pagination'

describe('Pagination', () => {
  it('dispara onPrev e onNext', async () => {
    const onPrev = vi.fn()
    const onNext = vi.fn()
    render(<Pagination hasPrev hasNext onPrev={onPrev} onNext={onNext} pageSize={25} />)
    await userEvent.click(screen.getByLabelText('Próxima página'))
    await userEvent.click(screen.getByLabelText('Página anterior'))
    expect(onNext).toHaveBeenCalledOnce()
    expect(onPrev).toHaveBeenCalledOnce()
  })

  it('desabilita botões quando não tem páginas', () => {
    render(<Pagination hasPrev={false} hasNext={false} onPrev={vi.fn()} onNext={vi.fn()} pageSize={25} />)
    expect(screen.getByLabelText('Próxima página')).toBeDisabled()
    expect(screen.getByLabelText('Página anterior')).toBeDisabled()
  })
})
