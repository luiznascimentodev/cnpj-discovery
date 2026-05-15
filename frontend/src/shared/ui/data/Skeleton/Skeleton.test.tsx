import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Skeleton } from './Skeleton'

describe('Skeleton', () => {
  it('expõe role=status', () => {
    render(<Skeleton className="h-8 w-32" />)
    expect(screen.getByRole('status', { name: 'Carregando' })).toBeInTheDocument()
  })
})
