import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Switch } from './Switch'

describe('Switch', () => {
  it('alterna estado checked', async () => {
    render(<Switch aria-label="modo escuro" />)
    const s = screen.getByRole('switch', { name: 'modo escuro' })
    expect(s).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(s)
    expect(s).toHaveAttribute('aria-checked', 'true')
  })
})
