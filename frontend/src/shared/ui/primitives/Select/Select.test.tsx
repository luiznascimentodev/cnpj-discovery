import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  SelectRoot, SelectTrigger, SelectContent, SelectItem, SelectValue,
} from './Select'

describe('Select', () => {
  it('renderiza trigger com placeholder', () => {
    render(
      <SelectRoot>
        <SelectTrigger><SelectValue placeholder="escolha" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="a">A</SelectItem>
        </SelectContent>
      </SelectRoot>
    )
    expect(screen.getByText('escolha')).toBeInTheDocument()
  })
})
