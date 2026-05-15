import { Link } from 'react-router'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { ApiError } from '@/shared/api'
import { registerSchema, type RegisterFormValues, useRegister } from '@/features/auth'
import { Button } from '@/shared/ui/primitives/Button'
import { Input } from '@/shared/ui/primitives/Input'
import { Label } from '@/shared/ui/primitives/Label'
import { Container } from '@/shared/ui/layout/Container'

export function RegistroPage() {
  const register = useRegister()
  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: '', email: '', password: '' },
  })
  const error = register.error instanceof ApiError ? register.error.message : null
  const success = register.data?.message

  const onSubmit = form.handleSubmit((values) => register.mutateAsync(values))

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
            onSubmit={onSubmit}
            aria-label="Formulário de cadastro"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nome">Nome completo</Label>
              <Input id="nome" autoComplete="name" {...form.register('name')} />
              {form.formState.errors.name ? (
                <p className="text-[var(--text-xs)] text-[var(--color-danger-fg)]">{form.formState.errors.name.message}</p>
              ) : null}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" autoComplete="email" {...form.register('email')} />
              {form.formState.errors.email ? (
                <p className="text-[var(--text-xs)] text-[var(--color-danger-fg)]">{form.formState.errors.email.message}</p>
              ) : null}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="senha">Senha</Label>
              <Input id="senha" type="password" autoComplete="new-password" {...form.register('password')} />
              <p className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">
                Mínimo 12 caracteres
              </p>
              {form.formState.errors.password ? (
                <p className="text-[var(--text-xs)] text-[var(--color-danger-fg)]">{form.formState.errors.password.message}</p>
              ) : null}
            </div>
            {error ? <p className="text-[var(--text-sm)] text-[var(--color-danger-fg)]">{error}</p> : null}
            {success ? <p className="text-[var(--text-sm)] text-[var(--color-success-fg)]">{success}</p> : null}
            <Button type="submit" size="lg" disabled={register.isPending}>
              {register.isPending ? 'Criando...' : 'Criar conta'}
            </Button>
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
