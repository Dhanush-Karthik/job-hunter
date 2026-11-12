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

describe('Replies & Inbound', () => {
  it('groups pending proposals, inbound recruiters first, with evidence and confidence', async () => {
    setup()
    await screen.findByText('TalentCorp Consulting · Keycloak / IAM Engineer')
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent?.replace(/\d+$/, ''))).toEqual(['Inbound recruiters', 'Status changes', 'Ghosted'])

    const inbound = card(/TalentCorp/)
    expect(within(inbound).getByText(/found your profile on Naukri/)).toBeInTheDocument()
    expect(within(inbound).getByText('88% confident')).toBeInTheDocument()
    expect(within(inbound).getByText(/from Arun K/)).toBeInTheDocument()
    expect(within(inbound).getByRole('link', { name: /TalentCorp/ })).toHaveAttribute('href', '/jobs/8')
    expect(within(inbound).getByRole('button', { name: 'Convert to application' })).toBeInTheDocument()
    expect(within(inbound).queryByRole('button', { name: /^Accept/ })).not.toBeInTheDocument()

    const change = card(/Freshworks/)
    expect(within(change).getByText('93% confident')).toBeInTheDocument()
    expect(within(change).getByText('Screening')).toBeInTheDocument()
    expect(within(change).getByText(/would like to schedule a 30 min call/)).toBeInTheDocument()
    expect(within(card(/Atlassian/)).getByText('100% confident')).toBeInTheDocument()
  })

  it('accepts a proposal as proposed (no payload edit)', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/1/accept')
    setup()
    await screen.findByText(/Freshworks/)
    await user.click(within(card(/Freshworks/)).getByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(screen.queryByText(/Freshworks/)).not.toBeInTheDocument())
    expect(posts).toEqual([{ payload: null }])
  })

  it('edits the target status before accepting', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/1/accept')
    setup()
    await screen.findByText(/Freshworks/)
    const c = card(/Freshworks/)
    await user.click(within(c).getByRole('button', { name: 'Edit' }))
    await user.selectOptions(within(c).getByRole('combobox', { name: /New status for Freshworks/ }), 'Technical')
    expect(within(c).getByRole('button', { name: 'Accept as Technical' })).toBeInTheDocument()
    await user.click(within(c).getByRole('button', { name: 'Accept as Technical' }))
    await waitFor(() => expect(posts).toEqual([{ payload: { to_status: 'Technical' } }]))
    await waitFor(() => expect(screen.queryByText(/Freshworks/)).not.toBeInTheDocument())
  })

  it('dismisses a proposal', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/3/dismiss')
    setup()
    await screen.findByText(/Atlassian/)
    await user.click(within(card(/Atlassian/)).getByRole('button', { name: 'Dismiss' }))
    await waitFor(() => expect(screen.queryByText(/Atlassian/)).not.toBeInTheDocument())
    expect(posts).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: /Ghosted/ })).not.toBeInTheDocument() // empty group disappears
  })

  it('converts an inbound recruiter into an application', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/proposals/2/convert')
    setup()
    await screen.findByText(/TalentCorp/)
    await user.click(within(card(/TalentCorp/)).getByRole('button', { name: 'Convert to application' }))
    await waitFor(() => expect(screen.queryByText(/TalentCorp/)).not.toBeInTheDocument())
    expect(posts).toHaveLength(1)
  })

  it('explains the empty state', async () => {
    server.use(http.get('/api/proposals', () => HttpResponse.json([])))
    setup()
    expect(await screen.findByText('Nothing to confirm')).toBeInTheDocument()
    expect(screen.getByText(/Gmail capture arrives in Wave 3/)).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(http.get('/api/proposals', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('500 boom')
  })
})
