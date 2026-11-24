import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import './test-utils' // ResizeObserver stub for Radix form controls
import { AppProviders } from './providers'
import { AppRoutes } from './routes'
import { TOUR_KEY } from '@/components/tour/tour'
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
beforeEach(() => localStorage.setItem(TOUR_KEY, 'done')) // the first-visit tour has its own tests
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
  it('routes to Home by default and lists every page in the nav, grouped', async () => {
    setup('/')
    expect(await screen.findByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    const links = within(nav).getAllByRole('link').map((a) => [a.textContent?.replace(/\d+\s*(pending|problems)$/, ''), a.getAttribute('href')])
    expect(links).toEqual([
      ['Home', '/'],
      ['Jobs', '/leads'],
      ['Inbox', '/replies'],
      ['Applications', '/tracker'],
      ['Insights', '/analytics'],
      ['Settings', '/settings'],
    ])
    expect(within(nav).getByText('Daily work')).toBeInTheDocument()
    expect(within(nav).getByText('Progress')).toBeInTheDocument()
  })

  it('shows pending counts from the API on the nav', async () => {
    setup('/')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(await within(nav).findByRole('link', { name: /Inbox\s*3\s*pending/ })).toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: /Follow-ups/ })).not.toBeInTheDocument()
    expect(await within(nav).findByRole('link', { name: /Jobs\s*3\s*pending/ })).toBeInTheDocument() // shortlisted, not applied
    expect(await within(nav).findByRole('link', { name: /Settings\s*2\s*problems/ })).toBeInTheDocument() // services down
  })

  it('redirects the old Quick apply page to the To apply tab', async () => {
    setup('/leads/quick-apply')
    expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: /To apply/, selected: true })).toBeInTheDocument()
  })

  it('routes job detail, applications, inbox and settings', async () => {
    setup('/jobs/7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Java Developer' })).toBeInTheDocument()
    cleanup()
    setup('/tracker')
    expect(await screen.findByRole('heading', { name: 'Applications' })).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Applied column' })).toBeInTheDocument()
    cleanup()
    setup('/replies')
    expect(await screen.findByRole('heading', { level: 1, name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByText('Recruiters reaching out')).toBeInTheDocument()
    cleanup()
    setup('/settings')
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(await screen.findByText('What to search for')).toBeInTheDocument()
  })

  it('sends the retired Reach out and Follow-ups URLs to Jobs, and routes insights', async () => {
    setup('/reachout')
    expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeInTheDocument()
    cleanup()
    setup('/outreach')
    expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeInTheDocument()
    cleanup()
    setup('/analytics')
    expect(await screen.findByRole('heading', { name: 'Insights' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Date range')).toBeInTheDocument()
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
