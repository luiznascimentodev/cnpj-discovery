import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Kbd } from './Kbd'

describe('Kbd', () => {
  it('renderiza conteúdo dentro de <kbd>', () => {
    const { container } = render(<Kbd>⌘K</Kbd>)
    expect(container.querySelector('kbd')).toBeTruthy()
    expect(screen.getByText('⌘K')).toBeInTheDocument()
  })
})
