import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Label } from './Label'

describe('Label', () => {
  it('renderiza com asterisco aria-hidden quando required', () => {
    render(<Label required>Nome</Label>)
    expect(screen.getByText('Nome')).toBeInTheDocument()
    expect(screen.getByText('*')).toHaveAttribute('aria-hidden', 'true')
  })
})
