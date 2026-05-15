import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UserAvatar } from './UserAvatar'

describe('UserAvatar', () => {
  it('exibe fallback com iniciais quando não há avatarUrl', () => {
    render(<UserAvatar user={{ name: 'Maria Souza' }} />)
    expect(screen.getByText('MS')).toBeInTheDocument()
  })
})
