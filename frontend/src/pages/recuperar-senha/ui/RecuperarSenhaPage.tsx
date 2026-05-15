import { Link } from 'react-router'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { ApiError } from '@/shared/api'
import { emailSchema, type EmailFormValues, useForgotPassword } from '@/features/auth'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function RecuperarSenhaPage() {
  const forgot = useForgotPassword()
  const form = useForm<EmailFormValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: '' },
  })
  const error = forgot.error instanceof ApiError ? forgot.error.message : null
  const success = forgot.data?.message
  const onSubmit = form.handleSubmit((values) => forgot.mutateAsync(values.email))

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
            onSubmit={onSubmit}
            aria-label="Formulário de recuperação de senha"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" autoComplete="email" {...form.register('email')} />
              {form.formState.errors.email ? (
                <p className="text-[var(--text-xs)] text-[var(--color-danger-fg)]">{form.formState.errors.email.message}</p>
              ) : null}
            </div>
            {error ? <p className="text-[var(--text-sm)] text-[var(--color-danger-fg)]">{error}</p> : null}
            {success ? <p className="text-[var(--text-sm)] text-[var(--color-success-fg)]">{success}</p> : null}
            <Button type="submit" size="lg" disabled={forgot.isPending}>
              {forgot.isPending ? 'Enviando...' : 'Enviar link'}
            </Button>
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
