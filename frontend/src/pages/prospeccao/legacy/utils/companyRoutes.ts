interface CompanyRouteData {
  cnpj_completo: string
  razao_social: string
  nome_fantasia: string | null
}

const slugify = (value: string): string =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)

export const companyPath = (empresa: CompanyRouteData): string => {
  const slug = slugify(empresa.nome_fantasia || empresa.razao_social)
  return `/empresa/${empresa.cnpj_completo}${slug ? `-${slug}` : ''}`
}

export const cnpjFromCompanyPath = (pathname = window.location.pathname): string | null => {
  const match = pathname.match(/^\/empresa\/([^/]+)/)
  if (!match) return null

  return match[1].match(/\d{14}/)?.[0] ?? null
}
