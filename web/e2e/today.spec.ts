import { test, expect } from './fixtures'

test('Home shows weekly progress, the to-do list and fresh matches', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByLabel('2 interview calls this week')).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Applied this week: 23 of 60' })).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Referrals asked: 6 of 15' })).toBeVisible()
  const todo = page.getByRole('list', { name: 'To do' })
  for (const text of ['1 recruiter reached out', '1 email update to confirm', '1 follow-up to send', '1 CV to approve', '3 shortlisted jobs to apply to', 'Refresh your Naukri profile']) {
    await expect(todo).toContainText(text)
  }
  await expect(page.getByText('Fresh matches', { exact: true })).toBeVisible()
  const hot = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: 'Shortlist TalentCorp Consulting', exact: true }) })
  await expect(hot).toContainText('Recruiter')
  await expect(hot).toContainText('Keycloak / IAM Engineer')
  // services that are down show as one banner, not a permanent health card
  await expect(page.getByRole('alert')).toContainText('glassdoor (paused after 3x 429)')
})

test('Shortlist on Home moves the lead to Jobs > To apply', async ({ page }) => {
  await page.goto('/')
  const shortlist = page.getByRole('button', { name: 'Shortlist TalentCorp Consulting', exact: true })
  await shortlist.click()
  await expect(shortlist).toHaveCount(0)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: /^Jobs/ }).click()
  await expect(page.getByRole('row').filter({ hasText: 'TalentCorp Consulting' })).toHaveCount(0)
  await page.getByRole('tab', { name: /To apply/ }).click()
  await expect(page.getByRole('list', { name: 'Jobs to apply to' })).toContainText('TalentCorp Consulting')
})
