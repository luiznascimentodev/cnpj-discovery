const ISO_DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/

export function formatDate(value: string | Date | null | undefined): string {
  if (value == null) return ''
  let d: Date
  if (typeof value === 'string') {
    // YYYY-MM-DD vira meia-noite local (não UTC, evita off-by-one em fusos negativos)
    const m = ISO_DATE_ONLY.exec(value)
    d = m
      ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
      : new Date(value)
  } else {
    d = value
  }
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' }).format(d)
}
