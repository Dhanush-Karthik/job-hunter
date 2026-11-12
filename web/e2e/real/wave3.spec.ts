import { test, expect } from '../fixtures'

test('real API: analytics, outreach and settings render and companies load', async ({ page, request }) => {
  const company = await request.post('/api/companies', { data: { name: 'Real Browser Company', careers_url: 'https://example.test/careers' } })
  expect(company.status()).toBe(201)
  try {
    for (const [path, title] of [['/analytics', 'Analytics'], ['/outreach', 'Outreach & Follow-ups'], ['/settings', 'Settings']]) {
      const failures: string[] = []
      const listen = (r: import('@playwright/test').Response) => {
        if (r.url().includes('/api/') && !r.ok()) failures.push(`${r.status()} ${r.url()}`)
      }
      page.on('response', listen)
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
      if (path === '/analytics') await expect(page.getByRole('list', { name: 'Funnel stages' })).toBeVisible()
      if (path === '/outreach') await expect(page.getByText('No follow-ups due', { exact: true })).toBeVisible()
      if (path === '/settings') await expect(page.getByRole('switch', { name: 'Enable Real Browser Company', exact: true })).toBeChecked()
      await expect(page.getByText('Something went wrong', { exact: true })).toHaveCount(0)
      expect(failures).toEqual([])
      page.off('response', listen)
    }
  } finally {
    expect((await request.delete('/api/companies/Real Browser Company')).status()).toBe(204)
  }
})
