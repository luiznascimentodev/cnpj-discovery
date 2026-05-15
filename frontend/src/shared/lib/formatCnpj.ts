export function formatCnpj(value: string | null | undefined): string {
  if (value == null) return ''
  const digits = value.replace(/\D/g, '')
  if (digits.length !== 14) return value
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`
}
