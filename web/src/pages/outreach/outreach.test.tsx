import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { OutreachPage } from './outreach-page'

// The mock's due dates are relative to a fixed clock (13 Nov 2026 09:00 IST); pin Date so "due" is stable.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-13T09:00:00+05:30'))
})
afterEach(() => {
  vi.useRealTimers()
  server.events.removeAllListeners()
})

function capture(method: string, pathname: string) {
  const bodies: unknown[] = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === method && new URL(request.url).pathname === pathname) {
      const t = await request.clone().text()
      bodies.push(t ? JSON.parse(t) : null)
    }
  })
  return bodies
}

const setup = () => renderWithProviders(<OutreachPage />, { route: '/outreach' })
const card = (name: RegExp) => screen.getByRole('listitem', { name })

describe('Follow-ups', () => {
  it('says nothing is sent by the app and lists the due follow-up with contact, due date and draft', async () => {
    setup()
    expect(screen.getByText(/send it yourself .*then mark it sent\. The app never sends anything/)).toBeInTheDocument()
    const c = await waitFor(() => card(/Freshworks/))
    expect(within(c).getByRole('link', { name: /Freshworks/ })).toHaveAttribute('href', '/jobs/1')
    expect(within(c).getByText(/to careers@freshworks\.example/)).toBeInTheDocument()
    expect(within(c).getByText(/^(Overdue by|Due today)/)).toBeInTheDocument()
    // the message stays folded until asked for
    expect(within(c).queryByText(/following up on my application/)).not.toBeInTheDocument()
    await userEvent.setup().click(within(c).getByRole('button', { name: /Show message for Freshworks/ }))
    expect(within(c).getByText(/following up on my application/)).toBeInTheDocument()
    // referrals are on their own tab
    expect(screen.queryByText(/Okta/)).not.toBeInTheDocument()
  })

  it('shows referral drafts on the Referrals tab', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('tab', { name: 'Referral requests' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/outreach?tab=referrals')
    const c = await waitFor(() => card(/Okta/))
    expect(within(c).getByText(/Referral request · to Rahul S - Staff Engineer/)).toBeInTheDocument()
    expect(within(c).queryByText(/Overdue|Due/)).not.toBeInTheDocument()
  })

  it('copies the draft to the clipboard', async () => {
    const user = userEvent.setup() // installs a clipboard stub on navigator
    setup()
    const c = await waitFor(() => card(/Freshworks/))
    await user.click(within(c).getByRole('button', { name: /Copy draft for Freshworks/ }))
    expect(await navigator.clipboard.readText()).toMatch(/^Hello, following up on my application/)
    expect(await within(c).findByText('Copied')).toBeInTheDocument()
  })

  it('marks sent: the item leaves the list and appears in the Sent log', async () => {
    const user = userEvent.setup()
    const posts = capture('POST', '/api/outreach/2/mark-sent')
    setup()
    const c = await waitFor(() => card(/Freshworks/))
    await user.click(within(c).getByRole('button', { name: /Mark sent: Freshworks/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    await waitFor(() => expect(screen.getByText('No follow-ups due')).toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: 'Sent' }))
    const sent = await waitFor(() => card(/Freshworks/))
    expect(within(sent).getByText(/^Sent /)).toBeInTheDocument()
    expect(within(sent).queryByRole('button', { name: /Mark sent/ })).not.toBeInTheDocument()
    expect(within(sent).getByRole('button', { name: /Copy draft/ })).toBeInTheDocument()
  })

  it('snoozes for 3 days via POST', async () => {
    const user = userEvent.setup()
    const posts = capture('POST', '/api/outreach/2/snooze')
    setup()
    const c = await waitFor(() => card(/Freshworks/))
    await user.click(within(c).getByRole('button', { name: /Show message for Freshworks/ }))
    await user.click(within(c).getByRole('button', { name: 'Snooze Freshworks · Senior Software Engineer - Java 3 days' }))
    await waitFor(() => expect(posts).toEqual([{ days: 3 }]))
    // the mock keeps snoozed items in the list; the real API excludes them, so just check the request and the offered choices
    expect(within(c).getByRole('group', { name: /Snooze Freshworks/ }).querySelectorAll('button')).toHaveLength(3)
  })

  it('edits the draft with PATCH and shows the new text', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/outreach/2')
    setup()
    const c = await waitFor(() => card(/Freshworks/))
    await user.click(within(c).getByRole('button', { name: /Show message for Freshworks/ }))
    await user.click(within(c).getByRole('button', { name: /Edit draft for Freshworks/ }))
    const box = within(c).getByLabelText(/Draft for Freshworks/)
    await user.clear(box)
    await user.type(box, 'Hi team, a short nudge.')
    await user.click(within(c).getByRole('button', { name: 'Save draft' }))
    await waitFor(() => expect(patches).toEqual([{ draft: 'Hi team, a short nudge.', contact: 'careers@freshworks.example' }]))
    expect(await screen.findByText('Hi team, a short nudge.')).toBeInTheDocument()
  })

  it('shows an empty state and an error state', async () => {
    server.use(http.get('/api/outreach', () => HttpResponse.json([])))
    const user = userEvent.setup()
    setup()
    expect(await screen.findByText('No follow-ups due')).toBeInTheDocument()
    server.use(http.get('/api/outreach', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    await user.click(screen.getByRole('tab', { name: 'Sent' }))
    expect(await screen.findByText('500 boom')).toBeInTheDocument()
  })
})
