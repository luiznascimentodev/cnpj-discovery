import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from './Tabs'

describe('Tabs', () => {
  it('alterna conteúdo entre tabs', async () => {
    render(
      <TabsRoot defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">conteúdo A</TabsContent>
        <TabsContent value="b">conteúdo B</TabsContent>
      </TabsRoot>
    )
    expect(screen.getByText('conteúdo A')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'B' }))
    expect(screen.getByText('conteúdo B')).toBeInTheDocument()
  })
})
