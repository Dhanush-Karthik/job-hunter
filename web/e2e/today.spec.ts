import { test, expect } from './fixtures'

test('Today shows calls, targets, fresh hot leads and action queue', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Interview calls this week', { exact: true })).toBeVisible()
  await expect(page.getByLabel('2 interview calls this week')).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Applied: 23 of 60' })).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Referrals: 6 of 15' })).toBeVisible()
  await expect(page.getByText('Fresh hot leads', { exact: true })).toBeVisible()
  const hot = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: 'Shortlist TalentCorp Consulting', exact: true }) })
  await expect(hot).toContainText('Fresh')
  await expect(hot).toContainText('Keycloak / IAM Engineer')
  await expect(page.getByText('Action queue', { exact: true })).toBeVisible()
  for (const name of ['Inbound recruiters', 'Replies to confirm', 'Follow-ups due', 'Quick-applies waiting', 'Profile refresh', 'CVs to approve']) {
    await expect(page.getByRole('heading', { name })).toBeVisible()
  }
})

test('Shortlist updates a hot lead state and removes it from Today', async ({ page }) => {
  await page.goto('/')
  const shortlist = page.getByRole('button', { name: 'Shortlist TalentCorp Consulting', exact: true })
  await shortlist.click()
  await expect(shortlist).toHaveCount(0)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Leads', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: 'TalentCorp Consulting' })
  await expect(row).toContainText('Shortlisted')
})
