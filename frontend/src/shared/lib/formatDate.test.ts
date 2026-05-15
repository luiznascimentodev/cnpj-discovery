import { describe, expect, it } from 'vitest'
import { formatDate } from './formatDate'

describe('formatDate', () => {
  it('formata ISO em pt-BR', () => {
    expect(formatDate('2026-05-14')).toMatch(/14\/05\/2026/)
  })
  it('aceita Date', () => {
    expect(formatDate(new Date(2026, 4, 14))).toMatch(/14\/05\/2026/)
  })
  it('retorna vazio em null/undefined/data inválida', () => {
    expect(formatDate(null)).toBe('')
    expect(formatDate(undefined)).toBe('')
    expect(formatDate('not-a-date')).toBe('')
  })
})
