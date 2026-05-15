import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Toaster, toast } from './Toaster'

describe('Toaster', () => {
  it('renderiza container do sonner após disparar toast', async () => {
    render(<Toaster />)
    toast('Pronto')
    const region = await screen.findByLabelText(/notifica/i)
    expect(region).toBeInTheDocument()
  })
})
