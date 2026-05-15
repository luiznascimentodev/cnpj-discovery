import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Checkbox } from './Checkbox'

describe('Checkbox', () => {
  it('alterna estado checked', async () => {
    render(<Checkbox aria-label="aceito" />)
    const cb = screen.getByRole('checkbox', { name: 'aceito' })
    expect(cb).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(cb)
    expect(cb).toHaveAttribute('aria-checked', 'true')
  })
})
