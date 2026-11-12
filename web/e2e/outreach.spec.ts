import { test, expect } from './fixtures'

// The MSW fixtures are anchored to this date; keep due-date checks independent of the host clock.
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-11-13T09:00:00+05:30'))
})

test('edit a due draft, copy it, mark sent and find it in the sent log', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/outreach')
  const card = page.getByRole('listitem').filter({ hasText: 'Freshworks' })
  await expect(card).toContainText('Hello, following up')
  await card.getByRole('button', { name: /Edit draft/ }).click()
  await page.getByLabel(/^Draft for Freshworks/).fill('Following up on my Java application at Freshworks.')
  await page.getByRole('button', { name: 'Save draft', exact: true }).click()
  await expect(card).toContainText('Following up on my Java application at Freshworks.')
  await card.getByRole('button', { name: /Copy draft/ }).click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('Following up on my Java application at Freshworks.')
  await card.getByRole('button', { name: /Mark sent:/ }).click()
  await expect(page.getByText('No follow-ups due', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Sent log', exact: true }).click()
  await expect(card).toContainText('Following up on my Java application at Freshworks.')
  await expect(card.getByRole('button', { name: /Mark sent:/ })).toHaveCount(0)
})

test('snooze removes a follow-up from the due queue; referrals have drafts', async ({ page }) => {
  await page.goto('/outreach')
  await page.getByRole('button', { name: /^Snooze Freshworks.* 3 days$/ }).click()
  await expect(page.getByText('No follow-ups due', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Referrals', exact: true }).click()
  await expect(page.getByRole('listitem').filter({ hasText: 'Okta' })).toContainText('Hi Rahul')
})
