import { useEffect } from 'react'

export interface KeyboardShortcutOptions {
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
}

export function useKeyboardShortcut(
  key: string,
  handler: (e: KeyboardEvent) => void,
  opts: KeyboardShortcutOptions = {}
) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== key) return
      if (opts.ctrl && !e.ctrlKey) return
      if (opts.meta && !e.metaKey) return
      if (opts.shift && !e.shiftKey) return
      // Não dispara quando foco está em input/textarea/contentEditable
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      handler(e)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [key, handler, opts.ctrl, opts.meta, opts.shift])
}
