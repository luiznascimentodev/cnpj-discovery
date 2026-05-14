import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  AlertDialogRoot, AlertDialogTrigger, AlertDialogContent,
  AlertDialogTitle, AlertDialogAction,
} from './AlertDialog'

describe('AlertDialog', () => {
  it('abre via trigger', async () => {
    render(
      <AlertDialogRoot>
        <AlertDialogTrigger>excluir</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogTitle>Tem certeza?</AlertDialogTitle>
          <AlertDialogAction>Sim</AlertDialogAction>
        </AlertDialogContent>
      </AlertDialogRoot>
    )
    await userEvent.click(screen.getByText('excluir'))
    expect(await screen.findByText('Tem certeza?')).toBeInTheDocument()
  })
})
