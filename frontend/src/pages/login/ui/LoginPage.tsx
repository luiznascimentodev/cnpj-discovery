import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function LoginPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] py-12">
      <Container size="sm">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-8 shadow-sm">
          <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-fg-primary)]">Entrar</h1>
          <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            Acesse sua conta para continuar
          </p>
          <form
            className="mt-6 flex flex-col gap-4"
            onSubmit={(e) => e.preventDefault()}
            aria-label="Formulário de login"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" autoComplete="email" required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="senha">Senha</Label>
              <Input id="senha" type="password" autoComplete="current-password" required />
            </div>
            <Button type="submit" size="lg">Entrar</Button>
          </form>
          <div className="mt-4 flex items-center justify-between text-[var(--text-sm)]">
            <Link to="/recuperar-senha" className="text-[var(--color-action)] hover:underline">
              Esqueci minha senha
            </Link>
            <Link to="/registro" className="text-[var(--color-action)] hover:underline">
              Criar conta
            </Link>
          </div>
        </div>
      </Container>
    </div>
  )
}
