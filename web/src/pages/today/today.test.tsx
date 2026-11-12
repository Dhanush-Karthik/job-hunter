import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { TodayPage } from './today-page'

const setup = () => renderWithProviders(<TodayPage />)

describe('Today page', () => {
  it('shows the headline KPI, targets, hot leads, action queue and health', async () => {
    setup()
    expect(screen.getByLabelText('Loading today')).toBeInTheDocument()

    expect(await screen.findByLabelText('2 interview calls this week')).toBeInTheDocument()
    expect(screen.getByText('+1 vs previous week (1)')).toBeInTheDocument()

    expect(screen.getByRole('progressbar', { name: 'Applied: 23 of 60' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Referrals: 6 of 15' })).toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'TalentCorp Consulting' })).toHaveAttribute('href', '/jobs/8')
    expect(screen.getByRole('link', { name: 'Hashicorp Talent (via Uplers)' })).toBeInTheDocument()
    expect(screen.getAllByText('Fresh').length).toBeGreaterThanOrEqual(2)

    for (const heading of ['Inbound recruiters', 'Replies to confirm', 'Follow-ups due', 'Quick-applies waiting', 'Profile refresh', 'CVs to approve']) {
      expect(screen.getByRole('heading', { name: new RegExp(heading) })).toBeInTheDocument()
    }
    const health = screen.getByRole('list', { name: 'Service health' })
    expect(within(health).getByText('scheduler')).toBeInTheDocument()
    expect(within(health).getByText(/paused after 3x 429/)).toBeInTheDocument()
  })

  it('links each action to where it is handled', async () => {
    setup()
    await screen.findByLabelText('2 interview calls this week')
    const href = (name: RegExp) => screen.getByRole('link', { name }).getAttribute('href')
    expect(href(/2 quick-applies waiting/)).toBe('/leads/quick-apply')
    expect(href(/Follow up with Freshworks/)).toBe('/outreach')
    expect(href(/Freshworks replied/)).toBe('/replies')
    expect(href(/Approve CV for Razorpay/)).toBe('/jobs/4')
    expect(href(/Refresh Naukri profile/)).toBe('/settings')
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

  it('runs intake and toasts the result', async () => {
    const success = vi.spyOn(toast, 'success')
    const calls: string[] = []
    server.events.on('request:start', ({ request }) => {
      if (request.method === 'POST') calls.push(new URL(request.url).pathname)
    })
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('button', { name: /Run intake now/ }))
    await waitFor(() => expect(success).toHaveBeenCalledWith(expect.stringContaining('Intake started: 3 runs')))
    expect(calls).toContain('/api/intake/run')
    server.events.removeAllListeners()
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
    )
    setup()
    expect(await screen.findByText('No fresh hot leads')).toBeInTheDocument()
    expect(screen.getByText('Nothing waiting')).toBeInTheDocument()
  })
})
