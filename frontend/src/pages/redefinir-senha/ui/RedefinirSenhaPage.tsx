import { Link, useSearchParams } from 'react-router'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { ApiError } from '@/shared/api'
import {
  resetPasswordSchema,
  type ResetPasswordFormValues,
  useResetPassword,
} from '@/features/auth'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function RedefinirSenhaPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const reset = useResetPassword()
  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: '' },
  })
  const error = reset.error instanceof ApiError ? reset.error.message : null
  const onSubmit = form.handleSubmit((values) => reset.mutateAsync({ token, password: values.password }))

  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] py-12">
      <Container size="sm">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-8 shadow-sm">
          <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-fg-primary)]">
            Redefinir senha
          </h1>
          <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            Informe uma nova senha para sua conta
          </p>
          <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit} aria-label="Formulário de redefinição de senha">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="senha">Nova senha</Label>
              <Input id="senha" type="password" autoComplete="new-password" disabled={!token} {...form.register('password')} />
              {form.formState.errors.password ? (
                <p className="text-[var(--text-xs)] text-[var(--color-danger-fg)]">{form.formState.errors.password.message}</p>
              ) : null}
            </div>
            {!token ? <p className="text-[var(--text-sm)] text-[var(--color-danger-fg)]">Token ausente.</p> : null}
            {error ? <p className="text-[var(--text-sm)] text-[var(--color-danger-fg)]">{error}</p> : null}
            {reset.data ? <p className="text-[var(--text-sm)] text-[var(--color-success-fg)]">{reset.data.message}</p> : null}
            <Button type="submit" size="lg" disabled={!token || reset.isPending}>
              {reset.isPending ? 'Redefinindo...' : 'Redefinir senha'}
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
