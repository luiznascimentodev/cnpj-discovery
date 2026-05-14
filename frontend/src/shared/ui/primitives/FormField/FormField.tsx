import { createContext, useContext, useId } from 'react'
import { cn } from '@/shared/lib'
import { Label } from '../Label/Label'

interface Ctx { id: string; descId: string; errId: string; invalid: boolean }
const FormFieldCtx = createContext<Ctx | null>(null)

export interface FormFieldProps {
  label: string
  required?: boolean
  helper?: string
  error?: string
  children: React.ReactNode
  className?: string
}

export function FormField({ label, required, helper, error, children, className }: FormFieldProps) {
  const id = useId()
  const descId = `${id}-desc`
  const errId = `${id}-err`
  const invalid = Boolean(error)
  return (
    <FormFieldCtx.Provider value={{ id, descId, errId, invalid }}>
      <div className={cn('flex flex-col gap-1.5', className)}>
        <Label htmlFor={id} required={required}>{label}</Label>
        {children}
        {helper && !error && <p id={descId} className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{helper}</p>}
        {error && <p id={errId} className="text-[var(--text-xs)] text-[var(--color-danger)]">{error}</p>}
      </div>
    </FormFieldCtx.Provider>
  )
}

export function useFormField() {
  const ctx = useContext(FormFieldCtx)
  if (!ctx) throw new Error('useFormField must be used inside <FormField>')
  return ctx
}
