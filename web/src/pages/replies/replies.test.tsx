import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { RepliesPage } from './replies-page'

afterEach(() => server.events.removeAllListeners())

function capture(pathname: string) {
  const bodies: unknown[] = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === 'POST' && new URL(request.url).pathname === pathname) {
      const t = await request.clone().text()
      bodies.push(t ? JSON.parse(t) : null)
    }
  })
  return bodies
}

const setup = () => renderWithProviders(<RepliesPage />, { route: '/replies' })
const card = (name: RegExp) => screen.getByRole('listitem', { name })

const NEEDS_EYES = {
  id: 7,
  type: 'needs_eyes',
  application_id: 1,
  lead_id: 1,
  company: 'Freshworks',
  title: 'Senior Software Engineer - Java',
  payload: { message_id: '<x@y>' },
  evidence: 'Your application was viewed by Freshworks\n---------- This email was intended for You. Learn why we included this: https://www.linkedin.com/help/x?lipi=abc&amp;b=1',
  confidence: 0,
  state: 'pending',
  created_at: new Date().toISOString(),
}

describe('Inbox', () => {
  it('groups pending emails, recruiters first, with a readable preview', async () => {
    setup()
    await screen.findByText('TalentCorp Consulting · Keycloak / IAM Engineer')
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent?.replace(/\d+$/, ''))).toEqual(['Recruiters reaching out', 'Application updates'])

    const inbound = card(/TalentCorp/)
    expect(within(inbound).getByText(/found your profile on Naukri/)).toBeInTheDocument()
    expect(within(inbound).getByText(/from Arun K/)).toBeInTheDocument()
    expect(within(inbound).getByRole('link', { name: /TalentCorp/ })).toHaveAttribute('href', '/jobs/8')
    expect(within(inbound).getByRole('button', { name: 'Add to my jobs' })).toBeInTheDocument()
    expect(within(inbound).queryByText(/confident/)).not.toBeInTheDocument()

    const change = card(/Freshworks/)
    expect(within(change).getByText('Screening')).toBeInTheDocument()
    expect(within(change).getByRole('button', { name: 'Mark Screening' })).toBeInTheDocument()
    expect(within(change).getByText(/would like to schedule a 30 min call/)).toBeInTheDocument()
    expect(within(card(/Atlassian/)).getByRole('button', { name: 'Mark Ghosted' })).toBeInTheDocument()
  })

  it('confirms an update as proposed (no payload edit)', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/1/accept')
    setup()
    await screen.findByText(/Freshworks/)
    await user.click(within(card(/Freshworks/)).getByRole('button', { name: 'Mark Screening' }))
    await waitFor(() => expect(screen.queryByText(/Freshworks/)).not.toBeInTheDocument())
    expect(posts).toEqual([{ payload: null }])
  })

  it('picks a different status before confirming', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/1/accept')
    setup()
    await screen.findByText(/Freshworks/)
    const c = card(/Freshworks/)
    await user.click(within(c).getByRole('button', { name: 'Different status' }))
    await user.selectOptions(within(c).getByRole('combobox', { name: /New status for Freshworks/ }), 'Technical')
    await user.click(within(c).getByRole('button', { name: 'Mark Technical' }))
    await waitFor(() => expect(posts).toEqual([{ payload: { to_status: 'Technical', rejected_at_stage: null } }]))
    await waitFor(() => expect(screen.queryByText(/Freshworks/)).not.toBeInTheDocument())
  })

  it('ignores an email', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/3/dismiss')
    setup()
    await screen.findByText(/Atlassian/)
    await user.click(within(card(/Atlassian/)).getByRole('button', { name: 'Ignore' }))
    await waitFor(() => expect(screen.queryByText(/Atlassian/)).not.toBeInTheDocument())
    expect(posts).toHaveLength(1)
  })

  it('adds an inbound recruiter role to my jobs', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/2/convert')
    setup()
    await screen.findByText(/TalentCorp/)
    await user.click(within(card(/TalentCorp/)).getByRole('button', { name: 'Add to my jobs' }))
    await waitFor(() => expect(screen.queryByText(/TalentCorp/)).not.toBeInTheDocument())
    expect(posts).toHaveLength(1)
  })

  it('moves the application itself for an unsure email, then closes it', async () => {
    server.use(http.get('/api/proposals', () => HttpResponse.json([NEEDS_EYES])))
    const user = userEvent.setup()
    const moves = capture('/api/applications/1/transition')
    const accepts = capture('/api/proposals/7/accept')
    setup()
    const c = await screen.findByRole('listitem', { name: /Freshworks/ })
    expect(screen.getByRole('heading', { level: 2, name: /Please check/ })).toBeInTheDocument()
    // the preview drops the separator line, the footer and the tracking URL
    expect(within(c).getByText('Your application was viewed by Freshworks')).toBeInTheDocument()
    expect(c).not.toHaveTextContent(/linkedin\.com|intended for|-----/)
    await user.selectOptions(await within(c).findByRole('combobox', { name: /New status for Freshworks/ }), 'Rejected')
    await user.click(within(c).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(moves).toEqual([{ to_status: 'Rejected', rejected_at_stage: 'Applied' }]))
    await waitFor(() => expect(accepts).toEqual([{ payload: null }]))
  })

  it('explains the empty state', async () => {
    server.use(http.get('/api/proposals', () => HttpResponse.json([])))
    setup()
    expect(await screen.findByText('Inbox zero')).toBeInTheDocument()
    expect(screen.getByText(/Gmail is checked every 30 minutes/)).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(http.get('/api/proposals', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('500 boom')
  })
})
