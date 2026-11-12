import { test, expect } from './fixtures'

test('Leads renders ten rows; search and Fresh only narrow the list', async ({ page }) => {
  await page.goto('/leads')
  const rows = page.getByRole('table').locator('tbody tr')
  await expect(rows).toHaveCount(10)
  await page.getByRole('searchbox', { name: 'Search company or title' }).fill('Zoho')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('Zoho')
  await page.getByRole('searchbox', { name: 'Search company or title' }).fill('')
  await expect(rows).toHaveCount(10)
  const fresh = page.getByRole('checkbox', { name: 'Fresh only', exact: true })
  await fresh.click()
  await expect(fresh).toBeChecked()
  await expect(rows).toHaveCount(7)
  for (const row of await rows.all()) await expect(row).toContainText('Fresh')
  await expect(page.getByRole('row').filter({ hasText: 'Chargebee' })).toHaveCount(0)
})

test('Sort by posted date changes the rendered order', async ({ page }) => {
  await page.goto('/leads')
  const rows = page.getByRole('table').locator('tbody tr')
  await expect(rows).toHaveCount(10)
  const scoreOrder = await rows.locator('a').allTextContents()
  await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption('posted_at')
  await expect(rows.nth(1)).toContainText('Razorpay')
  const dateOrder = await rows.locator('a').allTextContents()
  expect(dateOrder).not.toEqual(scoreOrder)
  expect(dateOrder).toEqual([
    'Keycloak / IAM Engineer', 'SDE 2 - Payments Backend', 'Senior Software Engineer - Java',
    'Backend Developer (Java)', 'Software Engineer - Java Services', 'Software Engineer II, Identity Platform',
    'Remote Java Engineer', 'Backend Engineer, Jira Cloud', 'Platform Engineer', 'Java Developer',
  ])
})

test('Bulk skip requires a reason and removes both leads from the New queue', async ({ page }) => {
  await page.goto('/leads?status=New')
  const rows = page.getByRole('table').locator('tbody tr')
  await expect(rows).toHaveCount(4)
  const selected = await rows.locator('a').allTextContents()
  await rows.nth(0).getByRole('checkbox').check()
  await rows.nth(1).getByRole('checkbox').check()
  const toolbar = page.getByRole('toolbar', { name: 'Bulk actions' })
  await expect(toolbar).toContainText('2 selected')
  await toolbar.getByRole('button', { name: 'Skip…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Skip 2 leads' })
  const confirm = dialog.getByRole('button', { name: 'Skip', exact: true })
  await expect(confirm).toBeDisabled()
  await dialog.getByRole('textbox', { name: 'Reason', exact: true }).fill('   ')
  await expect(confirm).toBeDisabled()
  await dialog.getByRole('textbox', { name: 'Reason', exact: true }).fill('Role does not fit my search')
  await confirm.click()
  await expect(dialog).toHaveCount(0)
  await expect(rows).toHaveCount(2)
  for (const title of selected.slice(0, 2)) await expect(rows.getByRole('link', { name: title, exact: true })).toHaveCount(0)
  // Confirm persisted mock state through the status filter as well.
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('Skipped')
  await expect(rows).toHaveCount(2)
  for (const title of selected.slice(0, 2)) await expect(rows.getByRole('link', { name: title, exact: true })).toBeVisible()
})

test('Mobile uses ten cards instead of a table', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/leads')
  await expect(page.getByRole('checkbox', { name: 'Select all leads on this page' })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  const cards = page.getByRole('listitem').filter({ has: page.getByRole('checkbox') })
  await expect(cards).toHaveCount(10)
  await expect(cards.first()).toContainText('TalentCorp Consulting')
  await expect(cards.first().getByRole('button', { name: 'Shortlist TalentCorp Consulting' })).toBeVisible()
})

test('At 1280x800 row actions fit without horizontal scrolling', async ({ page }) => {
  await page.goto('/leads')
  const table = page.getByRole('table')
  await expect(table.locator('tbody tr')).toHaveCount(10)
  const dimensions = await table.evaluate((element) => {
    const container = element.parentElement!
    return { scroll: container.scrollWidth, client: container.clientWidth, left: container.scrollLeft,
      pageScroll: document.documentElement.scrollWidth, viewport: window.innerWidth }
  })
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client)
  expect(dimensions.pageScroll).toBeLessThanOrEqual(dimensions.viewport)
  expect(dimensions.left).toBe(0)
  for (const button of await table.getByRole('button', { name: /^(Shortlist|Skip|Evaluate|Restore) / }).all()) {
    const box = await button.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(1280)
    await expect(button).toBeVisible()
  }
})
