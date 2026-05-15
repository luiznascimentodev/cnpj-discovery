import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('concatena classes', () => {
    expect(cn('a', 'b')).toBe('a b')
  })
  it('ignora falsy', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })
  it('faz merge inteligente de classes Tailwind conflitantes', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })
})
