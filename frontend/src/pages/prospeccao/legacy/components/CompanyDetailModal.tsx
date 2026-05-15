import { useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, RefreshCw, X } from 'lucide-react'
import { getEmpresa, type CrawlerContactOut, type CrawlerDomainOut } from '@/shared/api'
import { companyPath } from '../utils/companyRoutes'

interface Props {
  cnpj: string | null
  onClose: () => void
  onRequestEnrichment?: (cnpj: string) => void
}

const SITUACAO_LABELS: Record<number, string> = {
  1: 'Nula',
  2: 'Ativa',
  3: 'Suspensa',
  4: 'Inapta',
  8: 'Baixada',
}

const PORTE_LABELS: Record<number, string> = { 1: 'MEI', 2: 'ME', 3: 'EPP', 5: 'Demais' }
const MATRIZ_LABELS: Record<number, string> = { 1: 'Matriz', 2: 'Filial' }
const CONTACT_TYPE_LABELS: Record<string, string> = {
  email: 'E-mail',
  phone: 'Telefone',
  whatsapp: 'WhatsApp',
  website: 'Website',
  social: 'Social',
}
const SOURCE_LABELS: Record<string, string> = {
  official_site: 'Site oficial',
  crawler: 'Crawler',
  rf_email_direct: 'Receita Federal',
  rf_email_mei: 'Receita Federal / MEI',
  rf_phone_mei: 'Receita Federal / MEI',
}

const formatCnpj = (v: string) =>
  `${v.slice(0, 2)}.${v.slice(2, 5)}.${v.slice(5, 8)}/${v.slice(8, 12)}-${v.slice(12)}`

const formatDate = (value: string | null | undefined) => {
  if (!value) return null
  const [year, month, day] = value.slice(0, 10).split('-')
  return year && month && day ? `${day}/${month}/${year}` : value
}

const sourceLabel = (value: string) => SOURCE_LABELS[value] ?? value.replace(/_/g, ' ')

const Row = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="grid gap-1 py-1 sm:grid-cols-[10rem_1fr] sm:gap-3">
    <span className="text-gray-500">{label}</span>
    <span className="font-medium text-gray-900">{value === null || value === undefined || value === '' ? '-' : value}</span>
  </div>
)

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="rounded-md border border-gray-200 bg-white p-4">
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
    {children}
  </section>
)

const DomainCard = ({ domain }: { domain: CrawlerDomainOut }) => (
  <li className="rounded-md border border-gray-100 p-3">
    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="font-medium text-gray-900">{domain.domain}</p>
        {domain.homepage_url && (
          <a
            href={domain.homepage_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-xs text-blue-700 hover:underline"
          >
            {domain.homepage_url}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
      <span className="text-xs font-medium text-gray-500">{domain.confidence}%</span>
    </div>
    <p className="mt-2 text-xs text-gray-500">
      {sourceLabel(domain.source)} · {domain.status}
      {formatDate(domain.last_seen) ? ` · visto em ${formatDate(domain.last_seen)}` : ''}
    </p>
  </li>
)

const ContactCard = ({ contact }: { contact: CrawlerContactOut }) => (
  <li className="rounded-md border border-gray-100 p-3">
    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          {CONTACT_TYPE_LABELS[contact.contact_type] ?? contact.contact_type}
        </p>
        <p className="mt-1 break-words font-medium text-gray-900">{contact.value}</p>
        {contact.label && <p className="mt-0.5 text-xs text-gray-500">{contact.label}</p>}
      </div>
      <span className="text-xs font-medium text-gray-500">{contact.confidence}%</span>
    </div>
    <div className="mt-2 space-y-1 text-xs text-gray-500">
      <p>
        Origem: {sourceLabel(contact.source)}
        {contact.source_domain ? ` · ${contact.source_domain}` : ''}
      </p>
      {contact.evidence_url && (
        <a
          href={contact.evidence_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-blue-700 hover:underline"
        >
          Evidência
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
      {formatDate(contact.last_seen) && <p>Visto em {formatDate(contact.last_seen)}</p>}
    </div>
  </li>
)

export function CompanyDetailModal({ cnpj, onClose, onRequestEnrichment }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['empresa', cnpj],
    queryFn: () => getEmpresa(cnpj!),
    enabled: !!cnpj,
  })

  useEffect(() => {
    if (!data) return

    const previousTitle = document.title
    const currentMeta = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    const previousDescription = currentMeta?.getAttribute('content') ?? null
    const descriptionMeta = currentMeta ?? document.createElement('meta')
    const createdMeta = !currentMeta

    if (createdMeta) {
      descriptionMeta.name = 'description'
      document.head.appendChild(descriptionMeta)
    }

    const displayName = data.nome_fantasia || data.razao_social
    document.title = `${displayName} | CNPJ ${formatCnpj(data.cnpj_completo)}`
    descriptionMeta.setAttribute(
      'content',
      `${displayName}, CNPJ ${formatCnpj(data.cnpj_completo)}, ${data.municipio_descricao || ''} ${data.uf || ''}. Dados cadastrais e contatos enriquecidos.`
    )

    return () => {
      document.title = previousTitle
      if (createdMeta) {
        descriptionMeta.remove()
      } else if (previousDescription === null) {
        descriptionMeta.removeAttribute('content')
      } else {
        descriptionMeta.setAttribute('content', previousDescription)
      }
    }
  }, [data])

  if (!cnpj) return null

  const address = data
    ? [
        data.tipo_logradouro,
        data.logradouro,
        data.numero,
        data.complemento,
        data.bairro,
        data.municipio_descricao,
        data.uf,
        data.cep ? `CEP ${data.cep}` : null,
      ]
        .filter(Boolean)
        .join(', ')
    : null

  const companyUrl = data ? companyPath(data) : `/empresa/${cnpj}`
  const crawler = data?.crawler_enrichment

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 flex h-full w-full max-w-3xl flex-col bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-gray-900">
              {data ? data.nome_fantasia || data.razao_social : 'Detalhes da empresa'}
            </h2>
            <a href={companyUrl} className="mt-1 inline-flex items-center gap-1 text-xs text-blue-700 hover:underline">
              {companyUrl}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-gray-500 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50 px-6 py-5 text-sm">
          {isLoading && <p className="text-gray-500">Carregando...</p>}
          {isError && <p className="text-red-600">Erro ao carregar dados da empresa.</p>}

          {data && (
            <div className="space-y-6">
              <div>
                <h3 className="mb-3 text-sm font-semibold text-gray-900">Receita Federal</h3>
                <div className="space-y-4">
                  <Section title="Identificação">
                    <Row label="CNPJ" value={formatCnpj(data.cnpj_completo)} />
                    <Row label="Razão Social" value={data.razao_social} />
                    <Row label="Nome Fantasia" value={data.nome_fantasia} />
                    <Row
                      label="Situação"
                      value={data.situacao_cadastral !== null ? (SITUACAO_LABELS[data.situacao_cadastral] ?? String(data.situacao_cadastral)) : null}
                    />
                    <Row label="Data Situação" value={formatDate(data.data_situacao)} />
                    <Row label="Data de Abertura" value={formatDate(data.data_inicio)} />
                    <Row label="Porte" value={data.porte !== null ? (PORTE_LABELS[data.porte] ?? String(data.porte)) : null} />
                    <Row label="Tipo" value={data.matriz_filial !== null ? (MATRIZ_LABELS[data.matriz_filial] ?? String(data.matriz_filial)) : null} />
                    <Row label="Natureza Jurídica" value={data.natureza_juridica} />
                  </Section>

                  <Section title="Endereço">
                    <Row label="Endereço" value={address} />
                  </Section>

                  <Section title="Contato">
                    <Row label="E-mail" value={data.email} />
                    <Row label="Telefone 1" value={data.telefone1} />
                    <Row label="Telefone 2" value={data.telefone2} />
                    <Row label="Fax" value={data.fax} />
                  </Section>

                  <Section title="CNAEs">
                    <Row
                      label="Principal"
                      value={data.cnae_principal_descricao ? `${data.cnae_principal} - ${data.cnae_principal_descricao}` : data.cnae_principal}
                    />
                    {data.cnae_secundarios.length > 0 && (
                      <div className="mt-2">
                        <p className="mb-1 text-gray-500">Secundários</p>
                        <ul className="ml-2 space-y-0.5">
                          {data.cnae_secundarios.map(c => (
                            <li key={c.codigo} className="font-medium text-gray-900">
                              <span className="font-mono">{c.codigo}</span>
                              {c.descricao ? ` - ${c.descricao}` : ''}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </Section>

                  <Section title="Capital Social">
                    <Row
                      label="Capital"
                      value={data.capital_social !== null ? data.capital_social.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : null}
                    />
                  </Section>

                  {data.simples && (
                    <Section title="Simples Nacional / MEI">
                      <Row label="Simples" value={data.simples.opcao_simples === 'S' ? 'Optante' : 'Não optante'} />
                      <Row label="Entrada Simples" value={formatDate(data.simples.data_opcao_simples)} />
                      <Row label="Saída Simples" value={formatDate(data.simples.data_exc_simples)} />
                      <Row label="MEI" value={data.simples.opcao_mei === 'S' ? 'Sim' : 'Não'} />
                      <Row label="Entrada MEI" value={formatDate(data.simples.data_opcao_mei)} />
                      <Row label="Saída MEI" value={formatDate(data.simples.data_exc_mei)} />
                    </Section>
                  )}

                  {data.socios.length > 0 && (
                    <Section title={`Quadro Societário (${data.socios.length})`}>
                      <ul className="space-y-3">
                        {data.socios.map((s, i) => (
                          <li key={`${s.nome_socio ?? 'socio'}-${i}`} className="rounded-md border border-gray-100 p-3">
                            <p className="font-medium text-gray-900">{s.nome_socio || '-'}</p>
                            <p className="mt-0.5 text-xs text-gray-500">
                              {s.qualificacao_descricao || `Qualificação ${s.qualificacao}`}
                              {s.data_entrada ? ` · Desde ${formatDate(s.data_entrada)}` : ''}
                            </p>
                            {s.cpf_cnpj_socio && (
                              <p className="mt-0.5 text-xs text-gray-500">CPF/CNPJ: {s.cpf_cnpj_socio}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </Section>
                  )}
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-gray-900">Crawler / Enriquecimento</h3>
                  {onRequestEnrichment && (
                    <button
                      type="button"
                      onClick={() => onRequestEnrichment(data.cnpj_completo)}
                      className="inline-flex items-center gap-2 rounded-md border border-blue-200 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Atualizar
                    </button>
                  )}
                </div>
                <div className="space-y-4">
                  {!crawler || (crawler.domains.length === 0 && crawler.contacts.length === 0) ? (
                    <Section title="Status">
                      <p className="text-gray-500">Nenhum dado enriquecido publicado para este CNPJ.</p>
                    </Section>
                  ) : (
                    <>
                      <Section title={`Domínios (${crawler.domains.length})`}>
                        {crawler.domains.length > 0 ? (
                          <ul className="space-y-3">
                            {crawler.domains.map(domain => <DomainCard key={domain.domain} domain={domain} />)}
                          </ul>
                        ) : (
                          <p className="text-gray-500">Nenhum domínio publicado.</p>
                        )}
                      </Section>

                      <Section title={`Contatos (${crawler.contacts.length})`}>
                        {crawler.contacts.length > 0 ? (
                          <ul className="space-y-3">
                            {crawler.contacts.map(contact => (
                              <ContactCard
                                key={`${contact.contact_type}-${contact.normalized_value}-${contact.evidence_url ?? ''}`}
                                contact={contact}
                              />
                            ))}
                          </ul>
                        ) : (
                          <p className="text-gray-500">Nenhum contato publicado.</p>
                        )}
                      </Section>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
