import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function RecuperarSenhaPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] py-12">
      <Container size="sm">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-8 shadow-sm">
          <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-fg-primary)]">
            Recuperar senha
          </h1>
          <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            Enviaremos um link de redefinição para o seu e-mail
          </p>
          <form
            className="mt-6 flex flex-col gap-4"
            onSubmit={(e) => e.preventDefault()}
            aria-label="Formulário de recuperação de senha"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" autoComplete="email" required />
            </div>
            <Button type="submit" size="lg">Enviar link</Button>
          </form>
          <p className="mt-4 text-[var(--text-sm)]">
            <Link to="/login" className="text-[var(--color-action)] hover:underline">
              Voltar para o login
            </Link>
          </p>
        </div>
      </Container>
    </div>
  )
}
