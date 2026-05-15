import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()

vi.mock('axios', () => ({
  default: {
    create: () => ({
      get,
      post,
      interceptors: { response: { use: vi.fn() }, request: { use: vi.fn() } },
    }),
  },
}))

describe('api client', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
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
})
