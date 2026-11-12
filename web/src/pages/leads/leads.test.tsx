import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { makeLeads } from '@/mocks/fixtures'
import { server } from '@/mocks/node'
import { LeadsPage } from './leads-page'
import { QuickApplyPage } from './quick-apply-page'

const leadRequests: URL[] = []
server.events.on('request:start', ({ request }) => {
  const u = new URL(request.url)
  if (u.pathname === '/api/leads' && request.method === 'GET') leadRequests.push(u)
})
afterEach(() => {
  leadRequests.length = 0
})

const row = (name: RegExp) => screen.getByRole('row', { name })

describe('Leads page', () => {
  it('renders ranked rows from the mocks and hides prefilter drops by default', async () => {
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    expect(screen.getByLabelText('Loading leads')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Senior Software Engineer - Java' })).toHaveAttribute('href', '/jobs/1')
    expect(screen.queryByText('Infosys')).not.toBeInTheDocument()

    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('TalentCorp Consulting')).toBeInTheDocument() // highest quick score first
    expect(within(rows[0]).getByText('Inbound')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Fresh')).toBeInTheDocument()
    expect(within(row(/Freshworks/)).getByText('A 4.4')).toBeInTheDocument()
    expect(within(row(/Razorpay/)).queryByText('CTC unknown')).not.toBeInTheDocument()
    expect(within(row(/Zoho/)).getByText('CTC unknown')).toBeInTheDocument()
    expect(screen.getByText('1–10 of 10')).toBeInTheDocument()
  })

  it('binds filters to the URL and the request', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Zoho')

    await user.type(screen.getByRole('searchbox', { name: /search company or title/i }), 'zoho')
    await waitFor(() => expect(screen.queryByText('Freshworks')).not.toBeInTheDocument())
    expect(screen.getByTestId('location')).toHaveTextContent('/leads?q=zoho')
    expect(leadRequests.at(-1)!.searchParams.get('q')).toBe('zoho')

    await user.clear(screen.getByRole('searchbox'))
    await user.click(screen.getByRole('checkbox', { name: 'Fresh only' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Source' }), 'linkedin')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Min score' }), '0.8')
    await waitFor(() => expect(leadRequests.at(-1)!.searchParams.get('source')).toBe('linkedin'))
    const last = () => leadRequests.at(-1)!.searchParams
    await waitFor(() => expect(last().get('min_score')).toBe('0.8'))
    expect(last().get('fresh_only')).toBe('true')
    await waitFor(() => expect(last().get('q')).toBeNull()) // cleared search lands after the debounce
    expect(screen.getByTestId('location').textContent).toContain('fresh_only=true')
    expect(await screen.findByText('Razorpay')).toBeInTheDocument()
    expect(screen.queryByText('Zoho')).not.toBeInTheDocument()
  })

  it('reads initial filters from the URL', async () => {
    renderWithProviders(<LeadsPage />, { route: '/leads?inbound_only=true&sort=found_at' })
    expect(await screen.findByText('TalentCorp Consulting')).toBeInTheDocument()
    expect(screen.queryByText('Zoho')).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Inbound only' })).toBeChecked()
    expect(screen.getByRole('combobox', { name: 'Sort by' })).toHaveValue('found_at')
    expect(leadRequests.at(-1)!.searchParams.get('inbound_only')).toBe('true')
  })

  it('shows rejected rows muted with Restore, and restores them', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads?include_rejected=true' })
    const infosys = await screen.findByRole('row', { name: /Infosys/ })
    expect(infosys).toHaveAttribute('data-rejected')
    expect(within(infosys).getAllByText(/location: Pune not in target cities/).length).toBeGreaterThan(0)
    await user.click(within(infosys).getByRole('button', { name: 'Restore Infosys' }))
    await waitFor(() => expect(screen.getByRole('row', { name: /Infosys/ })).not.toHaveAttribute('data-rejected'))
    expect(screen.queryByRole('button', { name: 'Restore Infosys' })).not.toBeInTheDocument()
  })

  it('shortlists, evaluates and skips from a row', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Chargebee')
    await user.click(screen.getByRole('button', { name: 'Shortlist Chargebee' }))
    await waitFor(() => expect(within(row(/Chargebee/)).getByText('Shortlisted')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Shortlist Chargebee' })).not.toBeInTheDocument()
    // evaluate queues a run and keeps the row
    await user.click(screen.getByRole('button', { name: 'Evaluate Chargebee' }))
    expect(row(/Chargebee/)).toBeInTheDocument()
  })

  it('bulk shortlists the selected rows', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('/api/leads/bulk', async ({ request }) => {
        bodies.push(await request.clone().json())
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Chargebee')
    expect(screen.queryByRole('toolbar', { name: 'Bulk actions' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /Select Chargebee/ }))
    await user.click(screen.getByRole('checkbox', { name: /Select Kissflow/ }))
    const bar = screen.getByRole('toolbar', { name: 'Bulk actions' })
    expect(within(bar).getByText('2 selected')).toBeInTheDocument()
    await user.click(within(bar).getByRole('button', { name: 'Shortlist' }))

    await waitFor(() => expect(within(row(/Kissflow/)).getByText('Shortlisted')).toBeInTheDocument())
    expect(within(row(/Chargebee/)).getByText('Shortlisted')).toBeInTheDocument()
    expect(bodies).toEqual([{ ids: [6, 7], action: 'shortlist' }])
    expect(screen.queryByRole('toolbar', { name: 'Bulk actions' })).not.toBeInTheDocument()
  })

  it('bulk skip needs a reason and sends it', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('/api/leads/bulk', async ({ request }) => {
        bodies.push(await request.clone().json())
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Chargebee')
    await user.click(screen.getByRole('checkbox', { name: /Select Chargebee/ }))
    await user.click(within(screen.getByRole('toolbar')).getByRole('button', { name: /Skip/ }))

    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Skip' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Reason'), 'stack mismatch')
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    await waitFor(() => expect(within(row(/Chargebee/)).getByText('Skipped')).toBeInTheDocument())
    expect(bodies).toEqual([{ ids: [6], action: 'skip', reason: 'stack mismatch' }])
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('select-all selects every row on the page and bulk evaluate/verify/restore are offered', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Chargebee')
    await user.click(screen.getByRole('checkbox', { name: 'Select all leads on this page' }))
    const bar = screen.getByRole('toolbar', { name: 'Bulk actions' })
    expect(within(bar).getByText('10 selected')).toBeInTheDocument()
    for (const name of ['Evaluate', 'Verify', 'Restore', 'Clear']) expect(within(bar).getByRole('button', { name })).toBeInTheDocument()
    await user.click(within(bar).getByRole('button', { name: 'Clear' }))
    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
  })

  it('pages with limit/offset', async () => {
    server.use(
      http.get('/api/leads', ({ request }) => {
        const u = new URL(request.url).searchParams
        return HttpResponse.json({ items: makeLeads().slice(0, 3), total: 120, limit: Number(u.get('limit')), offset: Number(u.get('offset')) })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('1–50 of 120')
    expect(leadRequests.at(-1)!.searchParams.get('limit')).toBe('50')
    expect(leadRequests.at(-1)!.searchParams.get('offset')).toBe('0')
    expect(screen.getByRole('button', { name: /Prev/ })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /Next/ }))
    expect(await screen.findByText('51–100 of 120')).toBeInTheDocument()
    expect(leadRequests.at(-1)!.searchParams.get('offset')).toBe('50')
    expect(screen.getByTestId('location')).toHaveTextContent('/leads?offset=50')

    await user.selectOptions(screen.getByRole('combobox', { name: 'Rows per page' }), '25')
    expect(await screen.findByText('1–25 of 120')).toBeInTheDocument() // changing the page size goes back to the first page
    expect(leadRequests.at(-1)!.searchParams.get('limit')).toBe('25')
    expect(leadRequests.at(-1)!.searchParams.get('offset')).toBe('0')
  })

  it('shows an error state', async () => {
    server.use(http.get('/api/leads', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    expect(await screen.findByRole('alert')).toHaveTextContent('500 boom')
  })
})

describe('Leads page on a phone', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows cards instead of a table, with the same selection and actions', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} }))
    const user = userEvent.setup()
    renderWithProviders(<LeadsPage />, { route: '/leads' })
    await screen.findByText('Chargebee')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    const cards = screen.getAllByRole('listitem')
    expect(cards).toHaveLength(10)
    expect(within(cards[0]).getByText('TalentCorp Consulting')).toBeInTheDocument()
    expect(within(cards[0]).getByText('Inbound')).toBeInTheDocument()
    expect(within(screen.getAllByRole('listitem').find((c) => within(c).queryByText('Zoho'))!).getByText('CTC unknown')).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /Select Chargebee/ }))
    expect(within(screen.getByRole('toolbar', { name: 'Bulk actions' })).getByText('1 selected')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Shortlist Kissflow' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Shortlist Kissflow' })).not.toBeInTheDocument())
  })
})

describe('Quick-apply view', () => {
  it('groups platform quick leads by source', async () => {
    renderWithProviders(<QuickApplyPage />, { route: '/leads/quick-apply' })
    const linkedin = await screen.findByRole('region', { name: 'LinkedIn quick-applies' })
    const naukri = screen.getByRole('region', { name: 'Naukri quick-applies' })
    expect(within(linkedin).getByText('Razorpay')).toBeInTheDocument()
    expect(within(linkedin).getByText('Postman')).toBeInTheDocument()
    expect(within(naukri).getByText('Zoho')).toBeInTheDocument()
    expect(screen.queryByText('Kissflow')).not.toBeInTheDocument() // New, not shortlisted
    expect(screen.queryByText('Okta')).not.toBeInTheDocument() // company ATS

    const open = within(naukri).getByRole('link', { name: 'Open apply link for Zoho' })
    expect(open).toHaveAttribute('href', 'https://example.com/jobs/2')
    expect(open).toHaveAttribute('target', '_blank')
    expect(open).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('only lets Ready leads be marked applied, with a hint otherwise', async () => {
    const user = userEvent.setup()
    renderWithProviders(<QuickApplyPage />, { route: '/leads/quick-apply' })
    const zoho = await screen.findByRole('button', { name: 'Mark applied for Zoho' })
    expect(zoho).toBeDisabled()
    expect(zoho).toHaveAccessibleDescription('Approve a CV first (status must be Ready).')

    const razorpay = screen.getByRole('button', { name: 'Mark applied for Razorpay' })
    expect(razorpay).toBeEnabled()
    await user.click(razorpay)
    await waitFor(() => expect(screen.queryByText('Razorpay')).not.toBeInTheDocument())
    expect(screen.getByText('Postman')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(http.get('/api/leads/quick-apply', () => HttpResponse.json([])))
    renderWithProviders(<QuickApplyPage />, { route: '/leads/quick-apply' })
    expect(await screen.findByText('No quick-applies waiting')).toBeInTheDocument()
  })
})
