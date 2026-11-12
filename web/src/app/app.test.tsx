import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { makeOutreach } from '@/mocks/fixtures'
import { server } from '@/mocks/node'
import { AppProviders } from './providers'
import { AppRoutes } from './routes'
import { THEME_STORAGE_KEY } from './theme'

// jsdom has no matchMedia; the theme provider and sonner read it.
beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
})
afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.className = ''
})

const setup = (route: string) =>
  render(
    <AppProviders>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )

describe('app shell', () => {
  it('routes to Today by default and lists every page in the nav', async () => {
    setup('/')
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const name of ['Today', 'Leads', 'Quick apply', 'Tracker', 'Analytics', 'Settings']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument()
    }
  })

  it('shows pending counts from the API on the nav', async () => {
    // the mock's due dates are relative to a fixed clock, so pin "due" here
    server.use(http.get('/api/outreach', () => HttpResponse.json(makeOutreach().slice(0, 2))))
    setup('/')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(await within(nav).findByRole('link', { name: /Replies & Inbound\s*3\s*pending/ })).toBeInTheDocument()
    expect(await within(nav).findByRole('link', { name: /Outreach & Follow-ups\s*2\s*pending/ })).toBeInTheDocument()
  })

  it('renders placeholders, including the lead id on job detail', async () => {
    setup('/jobs/42')
    expect(await screen.findByRole('heading', { name: 'Job detail' })).toBeInTheDocument()
    expect(screen.getByText('Lead #42')).toBeInTheDocument()
    cleanup()
    setup('/tracker')
    expect(await screen.findByRole('heading', { name: 'Tracker' })).toBeInTheDocument()
    expect(screen.getByText(/Coming in Wave 2/)).toBeInTheDocument()
  })

  it('persists the theme choice in localStorage', async () => {
    const user = userEvent.setup()
    setup('/analytics')
    await user.click(screen.getAllByRole('button', { name: 'Dark theme' })[0])
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    await user.click(screen.getAllByRole('button', { name: 'Light theme' })[0])
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement).not.toHaveClass('dark')
  })
})
