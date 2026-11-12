import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { TrackerPage } from './tracker-page'
import { allowedTargets, REJECT_STAGES } from './transitions'

afterEach(() => {
  server.events.removeAllListeners()
  vi.restoreAllMocks()
})

function capture(pathname: string) {
  const bodies: unknown[] = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === 'POST' && new URL(request.url).pathname === pathname) bodies.push(await request.clone().json())
  })
  return bodies
}

const column = (status: string) => screen.getByRole('region', { name: `${status} column` })
const setup = (route = '/tracker') => renderWithProviders(<TrackerPage />, { route })

describe('transitions map', () => {
  it('mirrors the server rules, plus Applied from Shortlisted', () => {
    expect(allowedTargets('Shortlisted')).toEqual(['Ready', 'Skipped', 'Applied'])
    expect(allowedTargets('Ready')).toEqual(['Applied'])
    expect(allowedTargets('Applied')).toContain('Rejected')
    expect(allowedTargets('Rejected')).toEqual([])
    expect(REJECT_STAGES).toEqual(['Applied', 'Screening', 'Technical', 'Final'])
  })
})

describe('Tracker board', () => {
  it('renders the pipeline columns with their cards and a collapsed Closed column', async () => {
    setup()
    expect(screen.getByLabelText('Loading tracker')).toBeInTheDocument()
    expect(await screen.findByText('Zoho')).toBeInTheDocument()
    for (const s of ['Shortlisted', 'Ready', 'Applied', 'Screening', 'Technical', 'Final', 'Offer']) expect(column(s)).toBeInTheDocument()
    expect(within(column('Shortlisted')).getByText('Postman')).toBeInTheDocument()
    expect(within(column('Ready')).getByText('Razorpay')).toBeInTheDocument()
    expect(within(column('Applied')).getByText('Freshworks')).toBeInTheDocument()
    expect(within(column('Screening')).getByText('Okta')).toBeInTheDocument()
    expect(within(column('Offer')).queryByRole('listitem')).not.toBeInTheDocument()

    // Atlassian is Rejected: hidden until Closed is opened
    const toggle = screen.getByRole('button', { name: /Closed/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Atlassian')).not.toBeInTheDocument()
    expect(within(toggle).getByText('1')).toBeInTheDocument()
    await userEvent.setup().click(toggle)
    expect(within(column('Rejected')).getByText('Atlassian')).toBeInTheDocument()
    for (const s of ['Ghosted', 'Withdrawn', 'Declined', 'Accepted', 'Skipped', 'Expired']) expect(column(s)).toBeInTheDocument()
  })

  it('links each card to its job page', async () => {
    setup()
    const link = await screen.findByRole('link', { name: 'Zoho: Backend Developer (Java)' })
    expect(link).toHaveAttribute('href', '/jobs/2')
  })

  it('moves a card with the Move to menu and posts the transition', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/applications/2/transition')
    setup()
    await screen.findByText('Zoho')
    const menu = screen.getByRole('combobox', { name: 'Move Zoho to' })
    expect(within(menu).getAllByRole('option').map((o) => o.textContent)).toEqual(['Move to…', 'Ready', 'Skipped', 'Applied'])
    await user.selectOptions(menu, 'Ready')
    await waitFor(() => expect(within(column('Ready')).getByText('Zoho')).toBeInTheDocument())
    expect(within(column('Shortlisted')).queryByText('Zoho')).not.toBeInTheDocument()
    expect(posts).toEqual([{ to_status: 'Ready', rejected_at_stage: null }])
  })

  it('snaps the card back and toasts when the server answers 409', async () => {
    const user = userEvent.setup()
    const toastError = vi.spyOn(toast, 'error')
    server.use(http.post('/api/applications/:id/transition', () => HttpResponse.json({ detail: 'cannot move Shortlisted -> Ready' }, { status: 409 })))
    setup()
    await screen.findByText('Zoho')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Move Zoho to' }), 'Ready')
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('409 cannot move Shortlisted -> Ready'))
    await waitFor(() => expect(within(column('Shortlisted')).getByText('Zoho')).toBeInTheDocument())
    expect(within(column('Ready')).queryByText('Zoho')).not.toBeInTheDocument()
  })

  it('asks for the rejected stage and will not confirm without one', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/applications/1/transition')
    setup()
    await screen.findByText('Freshworks')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Move Freshworks to' }), 'Rejected')

    const dialog = await screen.findByRole('dialog')
    expect(posts).toEqual([]) // nothing sent yet
    const confirm = within(dialog).getByRole('button', { name: 'Mark rejected' })
    expect(confirm).toBeDisabled()
    await user.selectOptions(within(dialog).getByLabelText('Rejected at stage'), 'Screening')
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    await waitFor(() => expect(posts).toEqual([{ to_status: 'Rejected', rejected_at_stage: 'Screening' }]))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(within(column('Applied')).queryByText('Freshworks')).not.toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: /Closed/ })).getByText('2')).toBeInTheDocument()
  })

  it('cancelling the Rejected dialog leaves the card alone', async () => {
    const user = userEvent.setup()
    const posts = capture('/api/applications/1/transition')
    setup()
    await screen.findByText('Freshworks')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Move Freshworks to' }), 'Rejected')
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(posts).toEqual([])
    expect(within(column('Applied')).getByText('Freshworks')).toBeInTheDocument()
  })

  it('offers no moves from a closed status', async () => {
    const user = userEvent.setup()
    setup()
    await screen.findByText('Zoho')
    await user.click(screen.getByRole('button', { name: /Closed/ }))
    expect(within(column('Rejected')).getByText('Atlassian')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Move Atlassian to' })).not.toBeInTheDocument()
  })

  it('shows empty and error states', async () => {
    server.use(http.get('/api/applications', () => HttpResponse.json([])))
    const { unmount } = setup()
    expect(await screen.findByText('Nothing tracked yet')).toBeInTheDocument()
    unmount()
    server.use(http.get('/api/applications', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('500 boom')
  })
})

describe('Tracker table', () => {
  it('lists every application with the requested columns, searchable and filterable by status', async () => {
    const user = userEvent.setup()
    setup('/tracker?view=table')
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Company', 'Title', 'Status', 'Variant', 'Applied', 'Next follow-up', 'Score', 'Source'])
    expect(within(table).getAllByRole('row')).toHaveLength(7) // header + 6 applications
    const freshworks = within(table).getByRole('row', { name: /Freshworks/ })
    expect(within(freshworks).getByText('Applied')).toBeInTheDocument()
    expect(within(freshworks).getByText('A')).toBeInTheDocument() // variant
    expect(within(freshworks).getByText('4.4')).toBeInTheDocument()
    expect(within(freshworks).getByText('LinkedIn')).toBeInTheDocument()
    expect(within(freshworks).getByRole('link', { name: 'Senior Software Engineer - Java' })).toHaveAttribute('href', '/jobs/1')

    await user.type(screen.getByRole('searchbox', { name: 'Search company or title' }), 'zoho')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
    await user.clear(screen.getByRole('searchbox'))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'Shortlisted')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3) // Zoho, Postman
    await user.type(screen.getByRole('searchbox'), 'nomatch')
    expect(screen.getByText('No applications match')).toBeInTheDocument()
  })

  it('toggles between board and table and keeps the choice in the URL', async () => {
    const user = userEvent.setup()
    setup()
    await screen.findByText('Zoho')
    await user.click(screen.getByRole('tab', { name: 'Table' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/tracker?view=table')
    await user.click(screen.getByRole('tab', { name: 'Board' }))
    expect(await screen.findByRole('region', { name: 'Applied column' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/tracker$/)
  })

  it('links to the CSV export', async () => {
    setup()
    const link = await screen.findByRole('link', { name: /Export CSV/ })
    expect(link).toHaveAttribute('href', '/api/applications/export.csv')
    expect(link).toHaveAttribute('download')
  })
})
