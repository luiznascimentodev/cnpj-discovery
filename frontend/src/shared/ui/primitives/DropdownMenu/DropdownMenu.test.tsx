import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from './DropdownMenu'

describe('DropdownMenu', () => {
  it('abre e dispara onSelect', async () => {
    let selected = ''
    render(
      <DropdownMenuRoot>
        <DropdownMenuTrigger>menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => { selected = 'a' }}>A</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenuRoot>
    )
    await userEvent.click(screen.getByText('menu'))
    await userEvent.click(await screen.findByText('A'))
    expect(selected).toBe('a')
  })
})
