import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Inline } from './Inline'

describe('Inline', () => {
  it('renders with default layout classes', () => {
    render(<Inline>Item</Inline>)

    expect(screen.getByText('Item')).toHaveClass('flex', 'gap-2', 'items-center', 'justify-start')
  })

  it('supports spacing, alignment, justification and wrapping variants', () => {
    render(
      <Inline gap={6} align="baseline" justify="between" wrap className="custom-class">
        Item
      </Inline>
    )

    expect(screen.getByText('Item')).toHaveClass(
      'flex',
      'flex-wrap',
      'gap-6',
      'items-baseline',
      'justify-between',
      'custom-class'
    )
  })
})
