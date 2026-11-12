import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import type { Settings } from '@/api/client'
import { SETTINGS } from '@/mocks/fixtures'
import { server } from '@/mocks/node'
import { SettingsPage } from './settings-page'

afterEach(() => server.events.removeAllListeners())

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

const setup = () => renderWithProviders(<SettingsPage />, { route: '/settings' })

describe('Settings form', () => {
  it('loads the stored values and shows schedules read-only', async () => {
    setup()
    expect(await screen.findByLabelText('Auto-evaluate top N per day')).toHaveValue(10)
    expect(screen.getByLabelText('Claude concurrency')).toHaveValue(2)
    expect(screen.getByLabelText('Applications per week')).toHaveValue(60)
    expect(screen.getByLabelText('Referrals per week')).toHaveValue(15)
    expect(screen.getByLabelText('Minimum eval score')).toHaveValue(3.5)
    const titles = screen.getByRole('list', { name: 'Titles list' })
    expect(within(titles).getAllByRole('listitem')).toHaveLength(9)
    expect(within(screen.getByRole('list', { name: 'Locations list' })).getByText('Remote India')).toBeInTheDocument()
    for (const [site, on] of [['LinkedIn', true], ['Naukri', true], ['Indeed', true], ['Glassdoor', true], ['Google Jobs', true]] as const) {
      expect(screen.getByRole('checkbox', { name: site })).toHaveProperty('ariaChecked', String(on))
    }
    expect(screen.getByText('08:00, 17:00')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled() // nothing changed
  })

  it('saves edits with PUT and keeps the fields it does not show', async () => {
    const user = userEvent.setup()
    const puts = capture('PUT', '/api/settings')
    setup()
    const n = await screen.findByLabelText('Auto-evaluate top N per day')
    await user.clear(n)
    await user.type(n, '5')
    await user.clear(screen.getByLabelText('Applications per week'))
    await user.type(screen.getByLabelText('Applications per week'), '40')

    // chips: add a title (Enter), add a location (button), remove one title
    await user.type(screen.getByLabelText('Titles'), 'Kotlin Developer{Enter}')
    await user.type(screen.getByLabelText('Locations'), 'Hyderabad')
    await user.click(screen.getByRole('button', { name: 'Add to Locations' }))
    await user.click(screen.getByRole('button', { name: 'Remove Keycloak' }))
    // sites: untick Glassdoor and Google
    await user.click(screen.getByRole('checkbox', { name: 'Glassdoor' }))
    await user.click(screen.getByRole('checkbox', { name: 'Google Jobs' }))

    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(puts).toHaveLength(1))
    const sent = puts[0] as Settings
    expect(sent.auto_evaluate_top_n).toBe(5)
    expect(sent.targets).toEqual({ ...SETTINGS.targets, applied_per_week: 40 })
    expect(sent.query_matrix.titles).toEqual([...SETTINGS.query_matrix.titles.filter((t) => t !== 'Keycloak'), 'Kotlin Developer'])
    expect(sent.query_matrix.locations).toEqual([...SETTINGS.query_matrix.locations, 'Hyderabad'])
    expect(sent.query_matrix.sites).toEqual(['linkedin', 'naukri', 'indeed'])
    expect(sent.query_matrix.hours_old).toBe(72) // untouched
    expect(sent.prefilter).toEqual(SETTINGS.prefilter)
    expect(sent.schedules).toEqual(SETTINGS.schedules)
    expect(sent.source_weights).toEqual(SETTINGS.source_weights)

    // after the save the form reloads from the server and is clean again
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled())
    expect(screen.getByLabelText('Auto-evaluate top N per day')).toHaveValue(5)
  })

  it('ignores duplicate chips and blocks saving invalid numbers', async () => {
    const user = userEvent.setup()
    setup()
    await user.type(await screen.findByLabelText('Titles'), 'java developer{Enter}')
    expect(within(screen.getByRole('list', { name: 'Titles list' })).getAllByRole('listitem')).toHaveLength(9)

    const conc = screen.getByLabelText('Claude concurrency')
    await user.clear(conc)
    await user.type(conc, '9')
    expect(screen.getByText('Between 1 and 4.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
    await user.clear(conc)
    await user.type(conc, '3')
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeEnabled()
  })
})

describe('Sources', () => {
  it('shows health and toggles a source', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/sources/indeed')
    setup()
    const table = await screen.findByRole('table')
    const indeed = within(table).getByRole('row', { name: /Indeed/ })
    expect(within(indeed).getByText('22')).toBeInTheDocument()
    expect(within(indeed).getByText('OK')).toBeInTheDocument()
    const glass = within(table).getByRole('row', { name: /Glassdoor/ })
    expect(within(glass).getByText(/Paused until/)).toBeInTheDocument()
    expect(within(glass).getByText(/429 Too Many Requests/)).toBeInTheDocument()

    const toggle = within(indeed).getByRole('switch', { name: 'Enable Indeed' })
    expect(toggle).toBeChecked()
    await user.click(toggle)
    await waitFor(() => expect(patches).toEqual([{ enabled: false, unpause: null }]))
    await waitFor(() => expect(within(screen.getByRole('row', { name: /Indeed/ })).getByRole('switch')).not.toBeChecked())
  })

  it('unpauses a paused source', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/sources/glassdoor')
    setup()
    await user.click(await screen.findByRole('button', { name: 'Unpause Glassdoor' }))
    await waitFor(() => expect(patches).toEqual([{ enabled: null, unpause: true }]))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Unpause Glassdoor' })).not.toBeInTheDocument())
  })

  it('runs intake now', async () => {
    const user = userEvent.setup()
    const posts = capture('POST', '/api/intake/run')
    setup()
    await user.click(await screen.findByRole('button', { name: /Run intake now/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
  })

  it('shows an error state when sources fail to load', async () => {
    server.use(http.get('/api/sources', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setup()
    expect(await screen.findByText('500 boom')).toBeInTheDocument()
  })
})

describe('Profiles', () => {
  it('ticks checklist items', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/profiles/naukri')
    setup()
    const naukri = await screen.findByRole('region', { name: 'Naukri profile' })
    expect(within(naukri).getByText('Refresh due')).toBeInTheDocument()
    const cities = within(naukri).getByRole('checkbox', { name: 'Preferred cities' })
    expect(cities).not.toBeChecked()
    await user.click(cities)
    await waitFor(() => expect(patches).toEqual([{ checklist: { preferred_cities: true }, refreshed_now: null }]))
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Naukri profile' })).getByRole('checkbox', { name: 'Preferred cities' })).toBeChecked())
  })

  it('opens the edit page in a new tab and marks Naukri refreshed', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/profiles/naukri')
    setup()
    const naukri = await screen.findByRole('region', { name: 'Naukri profile' })
    const edit = within(naukri).getByRole('link', { name: 'Open Naukri edit page' })
    expect(edit).toHaveAttribute('href', 'https://www.naukri.com/mnjuser/profile')
    expect(edit).toHaveAttribute('target', '_blank')
    expect(edit).toHaveAttribute('rel', expect.stringContaining('noopener'))

    await user.click(within(naukri).getByRole('button', { name: 'Mark Naukri refreshed' }))
    await waitFor(() => expect(patches).toEqual([{ checklist: null, refreshed_now: true }]))
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Naukri profile' })).queryByText('Refresh due')).not.toBeInTheDocument())
    // platforms without a refresh cadence get no Mark refreshed button
    expect(screen.queryByRole('button', { name: 'Mark Hirist refreshed' })).not.toBeInTheDocument()
  })
})
