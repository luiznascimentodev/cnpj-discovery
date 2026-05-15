import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { VisuallyHidden } from './VisuallyHidden'

describe('VisuallyHidden', () => {
  it('renderiza texto para screen reader', () => {
    render(<VisuallyHidden>conteúdo invisível</VisuallyHidden>)
    expect(screen.getByText('conteúdo invisível')).toBeInTheDocument()
  })
})
