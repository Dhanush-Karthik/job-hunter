import { test, expect } from './fixtures'

test('Every sidebar link navigates to its page', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  const destinations = [
    ['Home', '/'], ['Jobs', '/leads'], ['Inbox', '/replies'], ['Follow-ups', '/outreach'],
    ['Applications', '/tracker'], ['Insights', '/analytics'], ['Settings', '/settings'],
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

test('The old Quick apply URL lands on Jobs > To apply', async ({ page }) => {
  await page.goto('/leads/quick-apply')
  await expect(page).toHaveURL('http://localhost:5174/leads?tab=apply')
  await expect(page.getByRole('tab', { name: /To apply/ })).toHaveAttribute('aria-selected', 'true')
})
