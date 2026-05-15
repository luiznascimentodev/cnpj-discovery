import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function RegistroPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] py-12">
      <Container size="sm">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-8 shadow-sm">
          <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-fg-primary)]">Criar conta</h1>
          <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            Crie sua conta para começar a prospectar
          </p>
          <form
            className="mt-6 flex flex-col gap-4"
            onSubmit={(e) => e.preventDefault()}
            aria-label="Formulário de cadastro"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nome">Nome completo</Label>
              <Input id="nome" autoComplete="name" required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" autoComplete="email" required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="senha">Senha</Label>
              <Input id="senha" type="password" autoComplete="new-password" required minLength={12} />
              <p className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">
                Mínimo 12 caracteres
              </p>
            </div>
            <Button type="submit" size="lg">Criar conta</Button>
          </form>
          <p className="mt-4 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            Já tem conta?{' '}
            <Link to="/login" className="text-[var(--color-action)] hover:underline">
              Entrar
            </Link>
          </p>
        </div>
      </Container>
    </div>
  )
}
