import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Avatar, AvatarFallback } from './Avatar'

describe('Avatar', () => {
  it('renderiza fallback', () => {
    render(<Avatar><AvatarFallback>LF</AvatarFallback></Avatar>)
    expect(screen.getByText('LF')).toBeInTheDocument()
  })
})
