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
  it('loads the stored values, including prefilter, schedules and follow-up rules', async () => {
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
    expect(within(screen.getByRole('list', { name: 'Career-page scan times list' })).getAllByRole('listitem').map((l) => l.textContent)).toEqual(['08:00', '17:00'])
    expect(screen.getByLabelText('Boards every (hours)')).toHaveValue(3)
    expect(screen.getByLabelText('Gmail every (minutes)')).toHaveValue(30)
    expect(within(screen.getByRole('list', { name: 'Accepted cities list' })).getByText('Chennai')).toBeInTheDocument()
    expect(screen.getByLabelText('Minimum CTC (LPA)')).toHaveValue(10)
    expect(screen.getByLabelText('First follow-up after (business days)')).toHaveValue(5)
    expect(screen.getByLabelText('Propose ghosted after (days)')).toHaveValue(21)
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
    const card = (await screen.findByText(/A source that keeps failing pauses itself/)).closest('[data-slot="card"]') as HTMLElement
    const table = await within(card).findByRole('table')
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

describe('Prefilter, schedules and follow-up rules', () => {
  it('saves edited follow-up rules, schedule times and prefilter in the full object', async () => {
    const user = userEvent.setup()
    const puts = capture('PUT', '/api/settings')
    setup()
    const first = await screen.findByLabelText('First follow-up after (business days)')
    await user.clear(first)
    await user.type(first, '3')
    const ghost = screen.getByLabelText('Propose ghosted after (days)')
    await user.clear(ghost)
    await user.type(ghost, '30')
    await user.type(screen.getByLabelText('Extra holidays'), '2026-12-25{Enter}')
    await user.type(screen.getByLabelText('Career-page scan times'), '12:30{Enter}')
    const ctc = screen.getByLabelText('Minimum CTC (LPA)')
    await user.clear(ctc)
    await user.type(ctc, '12')
    await user.click(screen.getByRole('button', { name: 'Remove php' }))

    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(puts).toHaveLength(1))
    const sent = puts[0] as Settings
    expect(sent.followups).toEqual({ ...SETTINGS.followups, follow_up_business_days: 3, ghosted_after_days: 30, extra_holidays: ['2026-12-25'] })
    expect(sent.schedules).toEqual({ ...SETTINGS.schedules, careerops_scan_times: ['08:00', '17:00', '12:30'] })
    expect(sent.prefilter).toEqual({ ...SETTINGS.prefilter, ctc_min_lpa: 12, stack_negative: ['frontend only', 'sales'] })
    expect(sent.targets).toEqual(SETTINGS.targets)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled())
    expect(screen.getByLabelText('First follow-up after (business days)')).toHaveValue(3)
  })

  it('blocks saving a bad time, a bad date or an inverted window', async () => {
    const user = userEvent.setup()
    setup()
    await user.type(await screen.findByLabelText('Remote boards times'), '25:99{Enter}')
    expect(screen.getByText(/25:99 is not valid/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Remove 25:99' }))

    await user.type(screen.getByLabelText('Extra holidays'), '25-12-2026{Enter}')
    expect(screen.getByText(/25-12-2026 is not valid/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Remove 25-12-2026' }))

    const start = screen.getByLabelText('Boards window start (hour)')
    await user.clear(start)
    await user.type(start, '23')
    expect(screen.getByText('The window must start before it ends.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
  })
})

describe('Setup', () => {
  it('shows the status checklist', async () => {
    setup()
    const list = await screen.findByRole('list', { name: 'Setup checklist' })
    expect(within(list).getByText(/CV variant A:/)).toHaveTextContent('done')
    expect(within(list).getByText(/CV variant B:/)).toHaveTextContent('missing')
    expect(within(list).getByText(/Gmail app password:/)).toHaveTextContent('missing')
    expect(screen.getByText('Incomplete')).toBeInTheDocument()
  })

  it('uploads CV variant B as markdown', async () => {
    const user = userEvent.setup()
    const puts = capture('PUT', '/api/setup/cv')
    setup()
    const input = await screen.findByLabelText(/CV variant B \(markdown\)/)
    await user.upload(input, new File(['# Dhanush\n\nJava'], 'cv_b.md', { type: 'text/markdown' }))
    await waitFor(() => expect(puts).toEqual([{ variant: 'B', markdown: '# Dhanush\n\nJava' }]))
    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Setup checklist' })).getByText(/CV variant B:/)).toHaveTextContent('done'))
  })

  it('saves Gmail secrets (password hidden, never shown back) and tests the login', async () => {
    const user = userEvent.setup()
    const addr = capture('PUT', '/api/secrets/gmail_address')
    const pw = capture('PUT', '/api/secrets/gmail_app_password')
    setup()
    const password = await screen.findByLabelText(/App password/)
    expect(password).toHaveAttribute('type', 'password')
    await waitFor(() => expect(screen.getAllByText('not set')).toHaveLength(2))

    // before anything is stored the test fails with the server's detail
    await user.click(screen.getByRole('button', { name: 'Test Gmail' }))
    expect(await screen.findByText(/Failed: Gmail address or app password missing/)).toBeInTheDocument()

    await user.type(screen.getByLabelText(/Gmail address/), 'me@gmail.com')
    await user.type(password, 'abcd efgh ijkl mnop')
    await user.click(screen.getByRole('button', { name: 'Save to Keychain' }))
    await waitFor(() => expect(addr).toEqual([{ value: 'me@gmail.com' }]))
    await waitFor(() => expect(pw).toEqual([{ value: 'abcdefghijklmnop' }])) // spaces from Google's display stripped
    await waitFor(() => expect(screen.getAllByText('saved')).toHaveLength(2))
    // inputs are cleared: the secret is not echoed back
    expect(screen.getByLabelText(/App password/)).toHaveValue('')
    expect(screen.getByLabelText(/Gmail address/)).toHaveValue('')

    await user.click(screen.getByRole('button', { name: 'Test Gmail' }))
    expect(await screen.findByText(/OK: IMAP login ok, INBOX readable/)).toBeInTheDocument()
    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Setup checklist' })).getByText(/Gmail app password:/)).toHaveTextContent('done'))
  })
})

describe('Companies', () => {
  const panel = async () => within((await screen.findByText(/Career pages scanned twice a day/)).closest('[data-slot="card"]') as HTMLElement)

  it('lists companies with an API or websearch badge and filters by search', async () => {
    const user = userEvent.setup()
    setup()
    const p = await panel()
    const fresh = await p.findByRole('row', { name: /Freshworks/ })
    expect(within(fresh).getByText('API')).toBeInTheDocument()
    expect(within(fresh).getByText('smartrecruiters')).toBeInTheDocument()
    expect(within(p.getByRole('row', { name: /Zoho/ })).getByText('websearch')).toBeInTheDocument()
    expect(p.getByText('4 of 4')).toBeInTheDocument()
    await user.type(p.getByRole('searchbox', { name: 'Search companies' }), 'zoh')
    expect(p.getByText('1 of 4')).toBeInTheDocument()
    expect(p.queryByRole('row', { name: /Freshworks/ })).not.toBeInTheDocument()
    await user.clear(p.getByRole('searchbox', { name: 'Search companies' }))
    await user.type(p.getByRole('searchbox', { name: 'Search companies' }), 'nope')
    expect(p.getByText('No company matches')).toBeInTheDocument()
  })

  it('adds a company', async () => {
    const user = userEvent.setup()
    const posts = capture('POST', '/api/companies')
    setup()
    const p = await panel()
    await p.findByRole('row', { name: /Freshworks/ })
    const add = p.getByRole('button', { name: /Add company/ })
    expect(add).toBeDisabled()
    await user.type(p.getByLabelText('Company name'), 'Postman')
    await user.type(p.getByLabelText('Careers URL'), 'not a url')
    expect(add).toBeDisabled()
    await user.clear(p.getByLabelText('Careers URL'))
    await user.type(p.getByLabelText('Careers URL'), 'https://www.postman.com/company/careers/')
    await user.click(add)
    await waitFor(() => expect(posts).toEqual([{ name: 'Postman', careers_url: 'https://www.postman.com/company/careers/' }]))
    expect(await p.findByRole('row', { name: /Postman/ })).toBeInTheDocument()
    expect(p.getByLabelText('Company name')).toHaveValue('')
  })

  it('shows the server error when the company already exists', async () => {
    const user = userEvent.setup()
    setup()
    const p = await panel()
    await p.findByRole('row', { name: /Zoho/ })
    await user.type(p.getByLabelText('Company name'), 'zoho')
    await user.type(p.getByLabelText('Careers URL'), 'https://zoho.com/careers')
    await user.click(p.getByRole('button', { name: /Add company/ }))
    expect(await p.findByText('409 company exists')).toBeInTheDocument()
  })

  it('toggles enabled', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/companies/Chargebee')
    setup()
    const p = await panel()
    const sw = await p.findByRole('switch', { name: 'Enable Chargebee' })
    expect(sw).not.toBeChecked()
    await user.click(sw)
    await waitFor(() => expect(patches).toEqual([{ enabled: true }]))
    await waitFor(() => expect(p.getByRole('switch', { name: 'Enable Chargebee' })).toBeChecked())
  })

  it('deletes only after confirming', async () => {
    const user = userEvent.setup()
    let deletes = 0
    server.events.on('request:start', ({ request }) => {
      if (request.method === 'DELETE') deletes++
    })
    setup()
    const p = await panel()
    await user.click(await p.findByRole('button', { name: 'Delete Zoho' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText('Delete Zoho?')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(deletes).toBe(0)
    expect(p.getByRole('row', { name: /Zoho/ })).toBeInTheDocument()

    await user.click(p.getByRole('button', { name: 'Delete Zoho' }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deletes).toBe(1))
    await waitFor(() => expect(p.queryByRole('row', { name: /Zoho/ })).not.toBeInTheDocument())
  })
})

describe('Run logs', () => {
  const panel = async () => within((await screen.findByText(/Open one to read its log/)).closest('[data-slot="card"]') as HTMLElement)

  it('opens a run log', async () => {
    const user = userEvent.setup()
    setup()
    const p = await panel()
    const row = await p.findByRole('row', { name: /intake boards #2/ })
    expect(within(row).getByText('184 fetched, 23 new, 141 duplicates, 20 dropped')).toBeInTheDocument()
    expect(within(p.getByRole('row', { name: /intake gmail #1/ })).getByText('Gmail app password not set')).toBeInTheDocument()
    await user.click(within(row).getByRole('button', { name: 'Show log of run 2' }))
    expect(await p.findByLabelText('Log of run 2')).toHaveTextContent('linkedin: 48 rows')
    await user.click(within(p.getByRole('row', { name: /intake boards #2/ })).getByRole('button', { name: 'Hide log of run 2' }))
    expect(p.queryByLabelText('Log of run 2')).not.toBeInTheDocument()
  })

  it('cancels only queued or running runs', async () => {
    const user = userEvent.setup()
    const posts = capture('POST', '/api/runs/3/cancel')
    setup()
    const p = await panel()
    expect(await p.findByRole('button', { name: 'Cancel run 3' })).toBeInTheDocument()
    expect(p.queryByRole('button', { name: 'Cancel run 2' })).not.toBeInTheDocument()
    expect(p.queryByRole('button', { name: 'Cancel run 1' })).not.toBeInTheDocument()
    await user.click(p.getByRole('button', { name: 'Cancel run 3' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    await waitFor(() => expect(p.queryByRole('button', { name: 'Cancel run 3' })).not.toBeInTheDocument())
  })
})
