import { test, expect } from './fixtures'

test('insights shows calls, suggestions, funnel and all breakdown dimensions', async ({ page }) => {
  await page.goto('/analytics')
  await expect(page.getByLabel('9 interview calls', { exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Insights', exact: true })).toContainText('Naukri: 3 calls')
  await expect(page.getByRole('list', { name: 'Funnel stages' })).toContainText('Screening')
  for (const [tab, text] of [['Source', 'LinkedIn'], ['Channel', 'Company ATS'], ['Title', 'Backend Engineer'], ['CV variant', 'Variant B']]) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expect(page.getByRole('tabpanel')).toContainText(text)
    await expect(page.getByRole('tabpanel')).toContainText('Call rate')
  }
  await page.getByLabel('Date range', { exact: true }).selectOption('7')
  await expect(page.getByLabel('Date range', { exact: true })).toHaveValue('7')
})

test('the filter audit lives in Settings > Job search and restores a sample', async ({ page }) => {
  await page.goto('/settings')
  await page.getByRole('button', { name: /Location: a city you did not pick/ }).click()
  await expect(page.getByRole('link', { name: /Infosys/ })).toBeVisible()
  const restore = page.getByRole('button', { name: 'Restore lead #10', exact: true })
  await restore.click()
  await expect(restore).toHaveCount(0)
  await expect(page.getByText('Restored', { exact: true })).toBeVisible()
})
