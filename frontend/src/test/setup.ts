import '@testing-library/jest-dom/vitest'
import { expect, afterEach } from 'vitest'
import * as axeMatchers from 'vitest-axe/matchers'
import { cleanup } from '@testing-library/react'

// jsdom polyfills (Radix/cmdk dependem)
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// hasPointerCapture / setPointerCapture / releasePointerCapture — usados por Radix Select etc
const proto = Element.prototype as unknown as Record<string, unknown>
if (typeof proto.hasPointerCapture === 'undefined') proto.hasPointerCapture = () => false
if (typeof proto.setPointerCapture === 'undefined') proto.setPointerCapture = () => {}
if (typeof proto.releasePointerCapture === 'undefined') proto.releasePointerCapture = () => {}
if (typeof proto.scrollIntoView === 'undefined') proto.scrollIntoView = () => {}

expect.extend(axeMatchers as never)

afterEach(() => {
  cleanup()
})
