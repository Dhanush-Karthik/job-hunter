import { test as base, expect } from '@playwright/test'

// Installed before navigation and checked after every test, including navigation and mutations.
export const test = base.extend<{ browserErrors: void }>({
  browserErrors: [async ({ page }, use) => {
    const errors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(`console: ${message.text()}`)
    })
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
    await use()
    expect(errors, 'Browser console errors and uncaught exceptions').toEqual([])
  }, { auto: true }],
})

export { expect }
