import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './ApiError'

const get = vi.fn()
const post = vi.fn()
const requestUse = vi.fn()
const responseUse = vi.fn()

vi.mock('axios', () => ({
  default: {
    create: () => ({
      get,
      post,
      interceptors: { response: { use: responseUse }, request: { use: requestUse } },
    }),
  },
}))

describe('api client', () => {
  beforeEach(() => {
    vi.resetModules()
    get.mockReset()
    post.mockReset()
    requestUse.mockClear()
    responseUse.mockClear()
  })

  it('normalizes API errors', async () => {
    await import('./client')
    const [, handleError] = responseUse.mock.calls[0]

    await expect(handleError({
      response: {
        status: 422,
        data: {
          message: 'Dados inválidos',
          code: 'validation_error',
          fieldErrors: { email: ['Obrigatório'] },
        },
      },
    })).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Dados inválidos',
      status: 422,
      code: 'validation_error',
      fieldErrors: { email: ['Obrigatório'] },
    })
  })

  it('adds CSRF header to mutating requests when cookie exists', async () => {
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: 'cnpj_csrf=token%20123',
    })
    await import('./client')
    const [handleRequest] = requestUse.mock.calls[0]

    const config = handleRequest({ method: 'post', headers: {} })

    expect(config.headers['X-CSRF-Token']).toBe('token 123')
  })

  it('sends estimate requests with paid headers', async () => {
    const { estimateEnrichment } = await import('./client')
    post.mockResolvedValueOnce({ data: { eligible_count: 1 } })

    const result = await estimateEnrichment({ cnpjs: ['12345678000190'] })

    expect(result.eligible_count).toBe(1)
    expect(post.mock.calls[0][0]).toBe('/paid/enrichment/estimate')
    expect(post.mock.calls[0][2].headers['X-Account-Id']).toBeTruthy()
  })

  it('builds CSV export URL without cursor fields', async () => {
    const { buildExportCsvUrl } = await import('./client')

    const url = buildExportCsvUrl({
      uf: 'SP',
      cursor_cnpj_basico: '12345678',
      cursor_cnpj_ordem: '0001',
    })

    expect(url).toContain('/export/csv?uf=SP')
    expect(url).not.toContain('cursor')
  })

  it('calls public read endpoints with query params', async () => {
    const {
      getBairros,
      getCnaes,
      getEmpresa,
      getMunicipios,
      getStatus,
      searchEmpresas,
    } = await import('./client')
    get.mockResolvedValue({ data: [] })

    await searchEmpresas({ uf: 'SP', cnaes: [6201501, 6311900], excluir_mei: false, limit: 25 })
    await getEmpresa('12345678000190')
    await getBairros('SP', 'centro', 7107)
    await getMunicipios('SP', 'sao')
    await getCnaes()
    await getStatus()

    expect(get.mock.calls[0][0]).toBe('/prospecting')
    expect(get.mock.calls[0][1].params.getAll('cnaes')).toEqual(['6201501', '6311900'])
    expect(get.mock.calls[1][0]).toBe('/empresa/12345678000190')
    expect(get.mock.calls[2][1].params).toEqual({ uf: 'SP', q: 'centro', municipio: 7107 })
  })

  it('calls auth endpoints', async () => {
    const {
      forgotPassword,
      getCsrf,
      getSession,
      login,
      logout,
      register,
      resendVerification,
      resetPassword,
      verifyEmail,
    } = await import('./client')
    get.mockResolvedValue({ data: { id: 'user-1' } })
    post.mockResolvedValue({ data: { ok: true } })

    await getCsrf()
    await getSession()
    await login({ email: 'demo@example.com', password: 'secret' })
    await register({ name: 'Demo', email: 'demo@example.com', password: 'secret' })
    await logout()
    await verifyEmail('verify-token')
    await resendVerification('demo@example.com')
    await forgotPassword('demo@example.com')
    await resetPassword('reset-token', 'new-secret')

    expect(get.mock.calls.map(call => call[0])).toEqual(['/auth/csrf', '/auth/me'])
    expect(post.mock.calls.map(call => call[0])).toEqual([
      '/auth/login',
      '/auth/register',
      '/auth/logout',
      '/auth/verify-email',
      '/auth/resend-verification',
      '/auth/forgot-password',
      '/auth/reset-password',
    ])
    expect(post.mock.calls.at(-1)?.[1]).toEqual({ token: 'reset-token', new_password: 'new-secret' })
  })

  it('calls job endpoints', async () => {
    const {
      cancelEnrichmentJob,
      createEnrichmentJob,
      listEnrichmentJobItems,
      listEnrichmentJobs,
    } = await import('./client')
    post.mockResolvedValue({ data: { job_id: 1 } })
    get
      .mockResolvedValueOnce({ data: { jobs: [{ id: 1 }] } })
      .mockResolvedValueOnce({ data: { items: [{ cnpj: '12345678000190' }] } })

    await createEnrichmentJob({ cnpjs: ['12345678000190'] })
    const jobs = await listEnrichmentJobs()
    const items = await listEnrichmentJobItems(1)
    await cancelEnrichmentJob(1)

    expect(jobs[0].id).toBe(1)
    expect(items[0].cnpj).toBe('12345678000190')
    expect(post.mock.calls.at(-1)?.[0]).toBe('/paid/enrichment/jobs/1/cancel')
  })

  it('creates ApiError instances with optional metadata', () => {
    const error = new ApiError({
      message: 'Falha',
      status: 500,
      code: 'internal_error',
      fieldErrors: { password: ['Fraca'] },
    })

    expect(error).toBeInstanceOf(Error)
    expect(error).toMatchObject({
      name: 'ApiError',
      message: 'Falha',
      status: 500,
      code: 'internal_error',
      fieldErrors: { password: ['Fraca'] },
    })
  })
})
