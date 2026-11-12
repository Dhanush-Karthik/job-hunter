import { test, expect } from './fixtures'

test('Every sidebar link navigates to its page', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  const destinations = [
    ['Today', '/'], ['Leads', '/leads'], ['Quick apply', '/leads/quick-apply'],
    ['Tracker', '/tracker'], ['Replies & Inbound', '/replies'],
    ['Outreach & Follow-ups', '/outreach'], ['Analytics', '/analytics'], ['Settings', '/settings'],
  ]
  await expect(nav.getByRole('link')).toHaveCount(destinations.length)
  for (const [title, path] of destinations) {
    const link = nav.locator(`a[href="${path}"]`)
    await link.click()
    await expect(page).toHaveURL(`http://localhost:5174${path}`)
    await expect(link).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
    await expect(page.getByText('Page not found', { exact: true })).toHaveCount(0)
  }
})
