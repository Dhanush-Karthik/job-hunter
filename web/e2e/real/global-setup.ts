import { request, type FullConfig } from '@playwright/test'
import { rmSync } from 'node:fs'

export default async function globalSetup(config: FullConfig) {
  const api = await request.newContext({ baseURL: config.projects[0].use.baseURL })
  try {
    for (const [company, title, slug] of [
      ['Offline Browser Co', 'Java Backend Engineer', 'backend'],
      ['Offline Second Co', 'Spring Boot Developer', 'spring'],
    ]) {
      const response = await api.post('/api/leads', { data: {
        company, title, location: 'Chennai', url: `https://example.test/jobs/${slug}`,
        jd_text: 'Java Spring Boot backend services, 3 years experience, Chennai.',
      } })
      if (response.status() !== 201) throw new Error(`Seed failed: ${response.status()} ${await response.text()}`)
    }
  } finally {
    await api.dispose()
  }
  return async () => {
    const root = process.env.JOBHUNTER_E2E_DATA
    if (root) rmSync(root, { recursive: true, force: true })
  }
}
