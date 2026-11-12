import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { makeOutreach } from '@/mocks/fixtures'
import { server } from '@/mocks/node'
import './test-utils' // ResizeObserver stub for Radix form controls
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

  it('routes the Wave 2 pages (job detail, tracker, replies, settings)', async () => {
    setup('/jobs/7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Java Developer' })).toBeInTheDocument()
    cleanup()
    setup('/tracker')
    expect(await screen.findByRole('heading', { name: 'Tracker' })).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Applied column' })).toBeInTheDocument()
    cleanup()
    setup('/replies')
    expect(await screen.findByRole('heading', { name: 'Replies & Inbound' })).toBeInTheDocument()
    expect(await screen.findByText('Inbound recruiters')).toBeInTheDocument()
    expect(screen.queryByText(/Coming in Wave/)).not.toBeInTheDocument()
    cleanup()
    setup('/settings')
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Claude concurrency')).toBeInTheDocument()
  })

  it('routes the Wave 3 pages (outreach, analytics) with no placeholders left', async () => {
    setup('/outreach')
    expect(await screen.findByRole('heading', { name: 'Outreach & Follow-ups' })).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: 'Due follow-ups' })).toBeInTheDocument()
    cleanup()
    setup('/analytics')
    expect(await screen.findByRole('heading', { name: 'Analytics' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Date range')).toBeInTheDocument()
    expect(screen.queryByText(/Coming in Wave/)).not.toBeInTheDocument()
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
