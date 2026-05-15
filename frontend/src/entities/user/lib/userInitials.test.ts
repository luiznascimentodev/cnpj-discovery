import { describe, expect, it } from 'vitest'
import { userInitials } from './userInitials'

describe('userInitials', () => {
  it('retorna iniciais do primeiro e último nome', () => {
    expect(userInitials('Luiz Felippe Nascimento')).toBe('LN')
  })
  it('retorna 2 letras quando há apenas um nome', () => {
    expect(userInitials('Ana')).toBe('AN')
  })
  it('retorna ? quando vazio', () => {
    expect(userInitials('  ')).toBe('?')
  })
})
