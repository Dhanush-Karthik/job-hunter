import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { TodayPage } from './today-page'

const setup = () => renderWithProviders(<TodayPage />)

describe('Home page', () => {
  it('shows weekly progress, a to-do list in priority order and fresh matches', async () => {
    setup()
    expect(screen.getByLabelText('Loading today')).toBeInTheDocument()

    expect(await screen.findByLabelText('2 interview calls this week')).toBeInTheDocument()
    expect(screen.getByText('+1 vs last week (1)')).toBeInTheDocument()

    expect(screen.getByRole('progressbar', { name: 'Applied this week: 23 of 60' })).toBeInTheDocument()
    expect(screen.getByText('37 more applications to hit the weekly goal')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Referrals asked: 6 of 15' })).toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'TalentCorp Consulting' })).toHaveAttribute('href', '/jobs/8')
    expect(screen.getByRole('link', { name: 'Hashicorp Talent (via Uplers)' })).toBeInTheDocument()

    const todo = screen.getByRole('list', { name: 'To do' })
    await within(todo).findByText('3 shortlisted jobs to apply to') // its count comes from /api/leads
    const rows = within(todo).getAllByRole('listitem').map((li) => li.querySelector('.font-medium')?.textContent)
    expect(rows).toEqual([
      '1 recruiter reached out',
      '1 email update to confirm',
      '1 follow-up to send',
      '1 CV to approve',
      '3 shortlisted jobs to apply to',
      'Refresh your Naukri profile',
    ])
    expect(within(todo).getByText('TalentCorp Consulting')).toBeInTheDocument()
    expect(within(todo).getByText(/Freshworks · oldest overdue by \d+ days?/)).toBeInTheDocument()
    // raw internal labels never reach the page
    expect(screen.queryByText(/status_change|needs_eyes/)).not.toBeInTheDocument()

    // problems show as one banner pointing at Settings > System, not a permanent health card
    const banner = screen.getByRole('alert')
    expect(banner).toHaveTextContent('gmail (app password not set), glassdoor (paused after 3x 429)')
    expect(within(banner).getByRole('link', { name: 'Open System' })).toHaveAttribute('href', '/settings?tab=system')
    expect(screen.queryByText('scheduler')).not.toBeInTheDocument()
  })

  it('links each task to where it is handled', async () => {
    setup()
    await screen.findByLabelText('2 interview calls this week')
    const href = (name: RegExp) => screen.getByRole('link', { name }).getAttribute('href')
    expect(href(/Review: 1 recruiter/)).toBe('/replies')
    expect(href(/Confirm: 1 email update/)).toBe('/replies')
    expect(href(/Send: 1 follow-up/)).toBe('/outreach')
    expect(href(/Approve: 1 CV/)).toBe('/jobs/4')
    expect(await screen.findByRole('link', { name: /Apply: 3 shortlisted jobs/ })).toHaveAttribute('href', '/leads?tab=apply')
    expect(screen.getByRole('link', { name: /Open Naukri/ })).toHaveAttribute('href', 'https://www.naukri.com/mnjuser/profile')
  })

  it('marks the profile refreshed from Home', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    server.events.on('request:start', ({ request }) => {
      if (request.method === 'PATCH') calls.push(new URL(request.url).pathname)
    })
    setup()
    await user.click(await screen.findByRole('button', { name: 'Mark done' }))
    await waitFor(() => expect(calls).toContain('/api/profiles/naukri'))
    server.events.removeAllListeners()
  })

  it('shortlists a hot lead and removes it from the list', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('button', { name: 'Shortlist Hashicorp Talent (via Uplers)' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Hashicorp Talent (via Uplers)' })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'TalentCorp Consulting' })).toBeInTheDocument()
  })

  it('needs a reason to skip a hot lead', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('button', { name: 'Skip TalentCorp Consulting' }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Skip' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Reason'), '   ')
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Reason'), 'recruiter spam')
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    await waitFor(() => expect(screen.queryByRole('link', { name: 'TalentCorp Consulting' })).not.toBeInTheDocument())
  })

  it('shows the server error with a retry', async () => {
    server.use(http.get('/api/today', () => HttpResponse.json({ detail: 'db locked' }, { status: 500 })))
    setup()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('500 db locked')
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('shows empty states', async () => {
    server.use(
      http.get('/api/today', () =>
        HttpResponse.json({ interview_calls_week: 0, interview_calls_prev_week: 0, applied_week: 0, applied_target: 60, referrals_week: 0, referrals_target: 15, fresh_hot_leads: [], actions: [], health: [] }),
      ),
      http.get('/api/leads', () => HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 })),
    )
    setup()
    expect(await screen.findByText('No fresh matches right now')).toBeInTheDocument()
    expect(await screen.findByText('All caught up')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
