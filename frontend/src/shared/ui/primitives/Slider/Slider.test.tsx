import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Slider } from './Slider'

describe('Slider', () => {
  it('expõe aria-valuenow do defaultValue', () => {
    render(<Slider defaultValue={[50]} max={100} />)
    expect(screen.getByRole('slider')).toHaveAttribute('aria-valuenow', '50')
  })
})
