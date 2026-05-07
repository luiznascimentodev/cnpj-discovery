import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { getEmpresa } from '../api/client'

interface Props {
  cnpj: string | null
  onClose: () => void
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

const formatCnpj = (v: string) =>
  `${v.slice(0, 2)}.${v.slice(2, 5)}.${v.slice(5, 8)}/${v.slice(8, 12)}-${v.slice(12)}`

const Row = ({ label, value }: { label: string; value: string | number | null | undefined }) => (
  <div className="flex gap-2 py-1">
    <span className="w-40 shrink-0 text-gray-500">{label}</span>
    <span className="font-medium text-gray-900">{value ?? '-'}</span>
  </div>
)

export function CompanyDetailModal({ cnpj, onClose }: Props) {
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

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">Detalhes da empresa</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-gray-500 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 text-sm">
          {isLoading && <p className="text-gray-500">Carregando...</p>}
          {isError && <p className="text-red-600">Erro ao carregar dados da empresa.</p>}

          {data && (
            <div className="space-y-6">
              {/* Identificação */}
              <section>
                <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Identificação
                </h3>
                <Row label="CNPJ" value={formatCnpj(data.cnpj_completo)} />
                <Row label="Razão Social" value={data.razao_social} />
                <Row label="Nome Fantasia" value={data.nome_fantasia} />
                <Row label="Situação" value={data.situacao_cadastral !== null ? (SITUACAO_LABELS[data.situacao_cadastral] ?? String(data.situacao_cadastral)) : null} />
                <Row label="Data Situação" value={data.data_situacao} />
                <Row label="Data de Abertura" value={data.data_inicio} />
                <Row label="Porte" value={data.porte !== null ? (PORTE_LABELS[data.porte] ?? String(data.porte)) : null} />
                <Row label="Tipo" value={data.matriz_filial !== null ? (MATRIZ_LABELS[data.matriz_filial] ?? String(data.matriz_filial)) : null} />
                <Row label="Natureza Jurídica" value={data.natureza_juridica} />
              </section>

              {/* Endereço */}
              <section>
                <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Endereço
                </h3>
                <Row label="Endereço" value={address} />
              </section>

              {/* Contato */}
              <section>
                <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Contato
                </h3>
                <Row label="E-mail" value={data.email} />
                <Row label="Telefone 1" value={data.telefone1} />
                <Row label="Telefone 2" value={data.telefone2} />
                <Row label="Fax" value={data.fax} />
              </section>

              {/* CNAEs */}
              <section>
                <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  CNAEs
                </h3>
                <Row
                  label="Principal"
                  value={data.cnae_principal_descricao ? `${data.cnae_principal} — ${data.cnae_principal_descricao}` : data.cnae_principal}
                />
                {data.cnae_secundarios.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-gray-500">Secundários</p>
                    <ul className="ml-2 space-y-0.5">
                      {data.cnae_secundarios.map(c => (
                        <li key={c.codigo} className="font-medium text-gray-900">
                          <span className="font-mono">{c.codigo}</span>
                          {c.descricao ? ` — ${c.descricao}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>

              {/* Capital */}
              <section>
                <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Capital Social
                </h3>
                <Row
                  label="Capital"
                  value={data.capital_social !== null ? data.capital_social.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : null}
                />
              </section>

              {/* Simples Nacional */}
              {data.simples && (
                <section>
                  <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Simples Nacional / MEI
                  </h3>
                  <Row label="Simples" value={data.simples.opcao_simples === 'S' ? 'Optante' : 'Não optante'} />
                  <Row label="Entrada Simples" value={data.simples.data_opcao_simples} />
                  <Row label="Saída Simples" value={data.simples.data_exc_simples} />
                  <Row label="MEI" value={data.simples.opcao_mei === 'S' ? 'Sim' : 'Não'} />
                  <Row label="Entrada MEI" value={data.simples.data_opcao_mei} />
                  <Row label="Saída MEI" value={data.simples.data_exc_mei} />
                </section>
              )}

              {/* Sócios */}
              {data.socios.length > 0 && (
                <section>
                  <h3 className="mb-3 border-b border-gray-100 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Quadro Societário ({data.socios.length})
                  </h3>
                  <ul className="space-y-3">
                    {data.socios.map((s, i) => (
                      <li key={i} className="rounded-md border border-gray-100 p-3">
                        <p className="font-medium text-gray-900">{s.nome_socio || '-'}</p>
                        <p className="mt-0.5 text-xs text-gray-500">
                          {s.qualificacao_descricao || `Qualificação ${s.qualificacao}`}
                          {s.data_entrada ? ` · Desde ${s.data_entrada}` : ''}
                        </p>
                        {s.cpf_cnpj_socio && (
                          <p className="mt-0.5 text-xs text-gray-500">CPF/CNPJ: {s.cpf_cnpj_socio}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
