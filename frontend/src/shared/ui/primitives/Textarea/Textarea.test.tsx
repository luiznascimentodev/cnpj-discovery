import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { Textarea } from './Textarea'

describe('Textarea', () => {
  it('renderiza', () => {
    render(<Textarea aria-label="x" />)
    expect(screen.getByLabelText('x')).toBeInTheDocument()
  })
  it('passa axe', async () => {
    const { container } = render(<Textarea aria-label="x" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
