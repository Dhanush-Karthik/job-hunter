import { describe, expect, it } from 'vitest'
import { api, unwrap } from './client'

describe('api client on MSW', () => {
  it('reads health', async () => {
    expect(unwrap(await api.GET('/api/health')).ok).toBe(true)
  })
  it('lists leads without prefilter drops by default', async () => {
    const page = unwrap(await api.GET('/api/leads', { params: { query: { limit: 100 } } }))
    expect(page.items.every((l) => l.prefilter_pass)).toBe(true)
    expect(page.items[0].quick_score).toBeGreaterThanOrEqual(page.items[1].quick_score)
  })
  it('rejects an illegal transition with 409', async () => {
    const r = await api.POST('/api/applications/{app_id}/transition', {
      params: { path: { app_id: 1 } },
      body: { to_status: 'Offer' },
    })
    expect(r.response.status).toBe(409)
  })
})
