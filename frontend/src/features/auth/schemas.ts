import { z } from 'zod'

export const loginSchema = z.object({
  email: z.string().email('E-mail inválido'),
  password: z.string().min(1, 'Informe sua senha'),
})

export const registerSchema = z.object({
  name: z.string().min(2, 'Informe seu nome').max(120, 'Nome muito longo'),
  email: z.string().email('E-mail inválido'),
  password: z.string().min(12, 'Mínimo 12 caracteres'),
})

export const emailSchema = z.object({
  email: z.string().email('E-mail inválido'),
})

export const resetPasswordSchema = z.object({
  password: z.string().min(12, 'Mínimo 12 caracteres'),
})

export type LoginFormValues = z.infer<typeof loginSchema>
export type RegisterFormValues = z.infer<typeof registerSchema>
export type EmailFormValues = z.infer<typeof emailSchema>
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>
