import { describe, expect, it } from 'vitest'
import { formatCnpj } from './formatCnpj'

describe('formatCnpj', () => {
  it('formata 14 dígitos canônico', () => {
    expect(formatCnpj('12345678000190')).toBe('12.345.678/0001-90')
  })
  it('mantém input já formatado idempotente', () => {
    expect(formatCnpj('12.345.678/0001-90')).toBe('12.345.678/0001-90')
  })
  it('retorna entrada inalterada se não tem 14 dígitos', () => {
    expect(formatCnpj('abc')).toBe('abc')
    expect(formatCnpj('123')).toBe('123')
  })
  it('lida com null/undefined retornando string vazia', () => {
    expect(formatCnpj(null)).toBe('')
    expect(formatCnpj(undefined)).toBe('')
  })
})
