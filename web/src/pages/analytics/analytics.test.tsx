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

describe('Analytics', () => {
  it('shows the headline calls, funnel with conversion, and response times', async () => {
    setup()
    expect(await screen.findByLabelText('9 interview calls')).toBeInTheDocument()
    const funnel = await screen.findByRole('list', { name: 'Funnel stages' })
    const applied = within(funnel).getByRole('listitem', { name: 'Applied' })
    expect(within(applied).getByText('84')).toBeInTheDocument()
    expect(within(applied).getByText('70% of prev')).toBeInTheDocument()
    expect(within(within(funnel).getByRole('listitem', { name: 'Screening' })).getByText('10.7% of prev')).toBeInTheDocument()
    expect(await screen.findByText('4.5 days')).toBeInTheDocument()
    expect(screen.getByText('11 days')).toBeInTheDocument()
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

  it('breaks calls down by source, channel, title and variant', async () => {
    const user = userEvent.setup()
    setup()
    const naukri = await screen.findByRole('row', { name: /^Naukri/ })
    expect(within(naukri).getAllByRole('cell').map((c) => c.textContent)).toEqual(['Naukri', '26', '3', '', '11.5%'])

    for (const [tab, text] of [['Channel', 'Company ATS'], ['Title', 'Backend Engineer'], ['CV variant', 'Variant B']] as const) {
      await user.click(screen.getByRole('tab', { name: tab }))
      expect(await screen.findByText(text)).toBeInTheDocument()
    }
  })

  it('shows weekly pace against targets', async () => {
    setup()
    const heading = await screen.findByText('Weekly pace')
    const card = heading.closest('[data-slot="card"]') as HTMLElement
    const rows = await waitFor(() => {
      const r = within(card).getAllByRole('row')
      expect(r.length).toBe(9)
      return r
    })
    expect(rows.at(-1)).toHaveTextContent('52 / 60')
    expect(rows.at(-1)).toHaveTextContent('9 / 15')
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

  it('lists reject reasons with sample links and restores a lead', async () => {
    const user = userEvent.setup()
    const restores = capture('POST', '/api/leads/10/restore')
    setup()
    const location = await screen.findByRole('row', { name: /location/i })
    expect(within(location).getByText('312')).toBeInTheDocument()
    expect(within(location).getByRole('link', { name: 'Lead #10' })).toHaveAttribute('href', '/jobs/10')
    await user.click(within(location).getByRole('button', { name: 'Restore lead #10' }))
    await waitFor(() => expect(restores).toHaveLength(1))
    expect(await within(screen.getByRole('row', { name: /location/i })).findByText('Restored')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Restore lead #10' })).not.toBeInTheDocument()
    // reasons with no samples have nothing to restore
    expect(within(screen.getByRole('row', { name: /stack/i })).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows an error state when a section fails', async () => {
    server.use(http.get('/api/analytics/rejects', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByText('500 boom')).toBeInTheDocument()
  })
})
