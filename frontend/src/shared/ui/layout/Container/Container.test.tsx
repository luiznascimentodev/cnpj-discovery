import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Container } from './Container'

describe('Container', () => {
  it('renders default and custom classes', () => {
    render(<Container className="custom-class">Conteúdo</Container>)

    expect(screen.getByText('Conteúdo')).toHaveClass('mx-auto', 'w-full', 'px-6', 'max-w-7xl', 'custom-class')
  })

  it('supports the full size variant', () => {
    render(<Container size="full">Largura total</Container>)

    expect(screen.getByText('Largura total')).toHaveClass('max-w-none')
  })
})
