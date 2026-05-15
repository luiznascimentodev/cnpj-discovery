type MockRow = {
  cnpj: string
  razao: string
  uf: string
  porte: string
}

const ROWS: MockRow[] = [
  { cnpj: '12.345.678/0001-90', razao: 'Acme Indústria S.A.', uf: 'SP', porte: 'Grande' },
  { cnpj: '23.456.789/0001-01', razao: 'Brava Tecnologia Ltda.', uf: 'SP', porte: 'Médio' },
  { cnpj: '34.567.890/0001-12', razao: 'Cíntia Comércio EIRELI', uf: 'RJ', porte: 'Pequeno' },
  { cnpj: '45.678.901/0001-23', razao: 'Delta Logística ME', uf: 'MG', porte: 'Pequeno' },
  { cnpj: '56.789.012/0001-34', razao: 'Êxito Serviços Ltda.', uf: 'PR', porte: 'Médio' },
]

export function ProductMockup() {
  return (
    <div
      aria-hidden="true"
      className="select-none rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] shadow-[var(--shadow-lg)]"
    >
      <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-gray-300)]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-gray-300)]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-gray-300)]" />
        <span className="ml-3 text-[var(--text-xs)] text-[var(--color-fg-muted)]">
          cnpj-discovery — Prospecção
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-3">
        <FilterPill>CNAE 62.04-0</FilterPill>
        <FilterPill>UF: SP</FilterPill>
        <FilterPill>Capital &gt; R$ 100k</FilterPill>
        <FilterPill variant="ghost">+ adicionar filtro</FilterPill>
      </div>
      <table className="w-full text-left text-[var(--text-xs)]">
        <thead className="bg-[var(--color-bg-subtle)] text-[var(--color-fg-secondary)]">
          <tr>
            <th className="px-4 py-2 font-medium">CNPJ</th>
            <th className="px-4 py-2 font-medium">Razão social</th>
            <th className="px-4 py-2 font-medium">UF</th>
            <th className="px-4 py-2 font-medium">Porte</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.cnpj} className="border-t border-[var(--color-border)]">
              <td className="px-4 py-2 font-mono text-[var(--color-fg-primary)]">{r.cnpj}</td>
              <td className="px-4 py-2 text-[var(--color-fg-primary)]">{r.razao}</td>
              <td className="px-4 py-2 text-[var(--color-fg-secondary)]">{r.uf}</td>
              <td className="px-4 py-2 text-[var(--color-fg-secondary)]">{r.porte}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FilterPill({
  children,
  variant = 'solid',
}: {
  children: React.ReactNode
  variant?: 'solid' | 'ghost'
}) {
  if (variant === 'ghost') {
    return (
      <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] border border-dashed border-[var(--color-border-strong)] px-2.5 py-1 text-[var(--text-xs)] text-[var(--color-fg-muted)]">
        {children}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-[var(--color-info-bg)] px-2.5 py-1 text-[var(--text-xs)] font-medium text-[var(--color-info-fg)]">
      {children}
    </span>
  )
}
