import { describe, expect, it, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from './useDebounce'

describe('useDebounce', () => {
  it('atrasa atualização do valor', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ v }) => useDebounce(v, 100), { initialProps: { v: 'a' } })
    expect(result.current).toBe('a')
    rerender({ v: 'b' })
    expect(result.current).toBe('a')
    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('b')
    vi.useRealTimers()
  })
})
