import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Separator } from './Separator'

describe('Separator', () => {
  it('renderiza sem erro', () => {
    const { container } = render(<Separator />)
    expect(container.firstChild).toBeTruthy()
  })
})
