import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Stack } from './Stack'

describe('Stack', () => {
  it('aplica gap, align e justify corretos', () => {
    const { container } = render(
      <Stack gap={6} align="center" justify="between">
        <span>a</span>
        <span>b</span>
      </Stack>
    )
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('gap-6')
    expect(el.className).toContain('items-center')
    expect(el.className).toContain('justify-between')
  })
})
