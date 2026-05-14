import { describe, expect, it } from 'vitest'

// Pares semantic que DEVEM atender WCAG AA (4.5:1 texto / 3:1 large)
const PAIRS: Array<[string, string, number]> = [
  ['#1a2333', '#f6f8fb', 4.5],   // fg-primary on bg-app
  ['#4a5878', '#f6f8fb', 4.5],   // fg-secondary on bg-app
  ['#5b6878', '#f6f8fb', 4.5],   // fg-muted on bg-app
  ['#ffffff', '#1351b4', 4.5],   // action-fg on action
  ['#1a2333', '#ffcd07', 4.5],   // brand-fg on brand
  ['#1351b4', '#ffffff', 4.5],   // action on bg-surface
]

function srgbToLin(c: number): number {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

function relLuminance(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return 0.2126 * srgbToLin(r) + 0.7152 * srgbToLin(g) + 0.0722 * srgbToLin(b)
}

function ratio(a: string, b: string): number {
  const la = relLuminance(a)
  const lb = relLuminance(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

describe('design tokens — contraste WCAG AA', () => {
  it.each(PAIRS)('par %s sobre %s tem ratio >= %f', (fg, bg, min) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(min)
  })
})
