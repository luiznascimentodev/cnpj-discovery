import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcut } from './useKeyboardShortcut'

describe('useKeyboardShortcut', () => {
  it('dispara handler na key correta', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboardShortcut('/', handler))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '/' }))
    expect(handler).toHaveBeenCalledOnce()
  })
  it('não dispara quando foco está em input', () => {
    const handler = vi.fn()
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    renderHook(() => useKeyboardShortcut('/', handler))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }))
    expect(handler).not.toHaveBeenCalled()
    document.body.removeChild(input)
  })
})
