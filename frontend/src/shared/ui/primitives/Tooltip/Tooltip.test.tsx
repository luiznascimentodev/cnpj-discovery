import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TooltipProvider, TooltipRoot, TooltipTrigger, TooltipContent } from './Tooltip'

describe('Tooltip', () => {
  it('mostra conteúdo on focus', async () => {
    render(
      <TooltipProvider delayDuration={0}>
        <TooltipRoot>
          <TooltipTrigger>btn</TooltipTrigger>
          <TooltipContent>oi</TooltipContent>
        </TooltipRoot>
      </TooltipProvider>
    )
    await userEvent.tab()
    // Radix renderiza tooltip e VisuallyHidden — basta encontrar ao menos um
    expect((await screen.findAllByText('oi')).length).toBeGreaterThan(0)
  })
})
