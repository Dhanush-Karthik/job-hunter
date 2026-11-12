import { test, expect } from './fixtures'

test('setup saves Gmail secrets and tests the connection', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.getByRole('list', { name: 'Setup checklist' })).toBeVisible()
  await page.getByLabel(/^Gmail address/).fill('owner@example.com')
  await page.getByLabel(/^App password/).fill('abcd efgh ijkl mnop')
  const writes: Record<string, string> = {}
  page.on('request', (r) => {
    if (r.method() === 'PUT' && r.url().includes('/api/secrets/')) writes[r.url().split('/').pop()!] = r.postDataJSON().value
  })
  await page.getByRole('button', { name: 'Save to Keychain', exact: true }).click()
  await expect(page.getByLabel(/^App password/)).toHaveValue('')
  expect(writes).toEqual({ gmail_address: 'owner@example.com', gmail_app_password: 'abcdefghijklmnop' })
  await page.getByRole('button', { name: 'Test Gmail', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: /^OK:/ })).toBeVisible()
})

test('companies can be added, disabled and deleted', async ({ page }) => {
  await page.goto('/settings')
  await page.getByLabel('Company name', { exact: true }).fill('Browser Test Co')
  await page.getByLabel('Careers URL', { exact: true }).fill('https://example.test/careers')
  await page.getByRole('button', { name: 'Add company', exact: true }).click()
  const toggle = page.getByRole('switch', { name: 'Enable Browser Test Co', exact: true })
  await expect(toggle).toBeChecked()
  await toggle.click()
  await expect(toggle).not.toBeChecked()
  await page.getByRole('button', { name: 'Delete Browser Test Co', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(toggle).toHaveCount(0)
})

test('follow-up rules save and a run log opens', async ({ page }) => {
  await page.goto('/settings')
  await page.getByRole('spinbutton', { name: 'First follow-up after (business days)', exact: true }).fill('7')
  await page.getByRole('spinbutton', { name: 'Propose ghosted after (days)', exact: true }).fill('28')
  const saved = page.waitForResponse((r) => r.url().endsWith('/api/settings') && r.request().method() === 'PUT')
  await page.getByRole('button', { name: 'Save settings', exact: true }).click()
  expect((await saved).ok()).toBeTruthy()
  await expect(page.getByRole('spinbutton', { name: 'First follow-up after (business days)', exact: true })).toHaveValue('7')
  await expect(page.getByRole('spinbutton', { name: 'Propose ghosted after (days)', exact: true })).toHaveValue('28')
  await page.getByRole('button', { name: 'Show log of run 2', exact: true }).click()
  await expect(page.getByLabel('Log of run 2', { exact: true })).toContainText('linkedin: 48 rows')
  await page.getByRole('button', { name: 'Hide log of run 2', exact: true }).click()
  await expect(page.getByLabel('Log of run 2', { exact: true })).toHaveCount(0)
})
