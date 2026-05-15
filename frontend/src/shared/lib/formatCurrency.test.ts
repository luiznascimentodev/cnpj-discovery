import { describe, expect, it } from 'vitest'
import { formatCurrency } from './formatCurrency'

describe('formatCurrency', () => {
  it('formata centavos em BRL', () => {
    expect(formatCurrency(12990)).toMatch(/R\$\s*129,90/)
  })
  it('aceita 0', () => {
    expect(formatCurrency(0)).toMatch(/R\$\s*0,00/)
  })
})
