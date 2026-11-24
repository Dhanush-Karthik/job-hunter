import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { server } from '@/mocks/node'
import { AnalyticsPage } from './analytics-page'

afterEach(() => server.events.removeAllListeners())

function capture(method: string, pathname: string) {
  const reqs: { search: string; body: unknown }[] = []
  server.events.on('request:start', async ({ request }) => {
    const u = new URL(request.url)
    if (request.method === method && u.pathname === pathname) {
      const t = method === 'GET' ? '' : await request.clone().text()
      reqs.push({ search: u.search, body: t ? JSON.parse(t) : null })
    }
  })
  return reqs
}

const setup = () => renderWithProviders(<AnalyticsPage />, { route: '/analytics' })

describe('Insights', () => {
  it('shows the headline numbers, the funnel with conversion, and reply times', async () => {
    setup()
    expect(await screen.findByLabelText('9 interview calls')).toBeInTheDocument()
    expect(screen.getByText('Call rate', { selector: 'dt' }).nextElementSibling).toHaveTextContent('10.7%') // 9 of 84
    expect(await screen.findByText('4.5 d')).toBeInTheDocument()
    expect(screen.getByText(/90% within 11 d, 14 replies/)).toBeInTheDocument()
    const flow = await screen.findByRole('list', { name: 'Pipeline flow: numbers' })
    expect(within(flow).getByText('Applied: 84, 84 · 70%')).toBeInTheDocument()
    expect(within(flow).getByText('Screening: 9, 9 · 10.7%')).toBeInTheDocument()
    expect(within(flow).getAllByText(/^Stopped here: /).length).toBeGreaterThan(0)
  })

  it('draws the pipeline as a flow diagram with a ribbon for every hop', async () => {
    setup()
    const diagram = await screen.findByRole('group', { name: 'Pipeline flow' })
    expect(diagram.querySelectorAll('[data-node]').length).toBeGreaterThanOrEqual(8)
    expect(diagram.querySelectorAll('path').length).toBeGreaterThanOrEqual(7)
    expect(diagram.querySelector('title')).toHaveTextContent(/→/)
  })

  it('renders insights with severity styling', async () => {
    setup()
    const list = await screen.findByRole('list', { name: 'Insights' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveAttribute('data-severity', 'good')
    expect(items[0]).toHaveTextContent('Naukri: 3 calls from 12 applies')
    expect(items[1]).toHaveAttribute('data-severity', 'warn')
    expect(items[2]).toHaveAttribute('data-severity', 'info')
  })

  it('flows calls from source, channel, title and variant into interview calls', async () => {
    const user = userEvent.setup()
    setup()
    const list = await screen.findByRole('list', { name: 'Calls by source: numbers' })
    expect(within(list).getByText('Naukri: 26, 26 applied · 11.5%')).toBeInTheDocument()
    expect(within(list).getByText(/^Interview call: /)).toBeInTheDocument()
    expect(within(list).getByText(/^No call yet: /)).toBeInTheDocument()

    for (const [tab, by, text] of [['Channel', 'channel', 'Company ATS'], ['Title', 'title', 'Backend Engineer'], ['CV variant', 'variant', 'Variant B']] as const) {
      await user.click(screen.getByRole('tab', { name: tab }))
      const rows = await screen.findByRole('list', { name: `Calls by ${by}: numbers` })
      expect(within(rows).getByText(new RegExp(`^${text}: `))).toBeInTheDocument()
    }
  })

  it('shows weekly pace against targets', async () => {
    setup()
    const weeks = within(await screen.findByRole('list', { name: 'Weekly pace' })).getAllByRole('listitem')
    expect(weeks).toHaveLength(8)
    expect(weeks.at(-1)).toHaveAccessibleName(/52 of 60 applications, 9 of 15 referrals/)
  })

  it('sends the chosen date range with the queries', async () => {
    const user = userEvent.setup()
    const funnels = capture('GET', '/api/analytics/funnel')
    const insights = capture('GET', '/api/analytics/insights')
    setup()
    await waitFor(() => expect(funnels.at(-1)?.search).toMatch(/^\?date_from=\d{4}-\d{2}-\d{2}$/)) // 30 days by default
    await user.selectOptions(screen.getByLabelText('Date range'), '7')
    await waitFor(() => expect(insights.at(-1)?.search).toBe('?days=7'))
    await user.selectOptions(screen.getByLabelText('Date range'), 'all')
    await waitFor(() => expect(funnels.at(-1)?.search).toBe(''))
    const from7 = new Date(Date.now() - 7 * 86400_000)
    expect(funnels.some((f) => f.search.includes(`date_from=${from7.getFullYear()}-`))).toBe(true)
  })

  it('shows an error state when a section fails', async () => {
    server.use(http.get('/api/analytics/insights', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByText('500 boom')).toBeInTheDocument()
  })
})
