import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Combobox } from './Combobox'

describe('Combobox', () => {
  it('seleciona uma opção', async () => {
    let chosen = ''
    render(
      <Combobox
        options={[{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }]}
        onChange={(v) => { chosen = v }}
      />
    )
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(await screen.findByText('A'))
    expect(chosen).toBe('a')
  })
})
