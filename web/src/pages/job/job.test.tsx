import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/app/test-utils'
import { api, type RunOut } from '@/api/client'
import { makeDetail, makeLeads, makeRuns } from '@/mocks/fixtures'
import { resetMockDb } from '@/mocks/handlers'
import { server } from '@/mocks/node'
import { JobDetailPage } from './job-page'
import { polling } from './use-job'

// react-pdf needs a canvas and a worker; the panel's job is to hand it the right URL.
vi.mock('./pdf-preview', () => ({ default: ({ url }: { url: string }) => <div data-testid="pdf" data-url={url} /> }))

beforeEach(() => {
  polling.ms = 40
  // The shared mock ignores ?lead_id= (the real API filters), which would leak other leads' runs in here.
  server.use(
    http.get('/api/runs', ({ request }) => {
      const id = Number(new URL(request.url).searchParams.get('lead_id'))
      return HttpResponse.json(makeRuns().filter((r) => r.lead_id === id))
    }),
  )
})
afterEach(() => {
  polling.ms = 2000
})

const show = (id: number) =>
  renderWithProviders(
    <Routes>
      <Route path="/jobs/:id" element={<JobDetailPage />} />
    </Routes>,
    { route: `/jobs/${id}` },
  )

/** Records the JSON bodies of non-GET requests to `pathname`. */
function capture(method: 'POST' | 'PATCH', pathname: string) {
  const bodies: unknown[] = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === method && new URL(request.url).pathname === pathname) {
      const text = await request.clone().text()
      bodies.push(text ? JSON.parse(text) : null)
    }
  })
  return bodies
}
afterEach(() => server.events.removeAllListeners())

const detail = (patch: Record<string, unknown>) => {
  const base = makeDetail(makeLeads()[7]) // the inbound recruiter lead
  server.use(http.get('/api/leads/:id', () => HttpResponse.json({ ...base, ...patch })))
}

describe('Where to apply', () => {
  it('points an inbound lead with no job link at the recruiter email in Gmail', async () => {
    detail({ apply_url: null, canonical_url: null, source_email_url: 'https://mail.google.com/mail/u/0/#search/rfc822msgid:a%40b' })
    show(8)
    const region = await screen.findByRole('region', { name: 'Where to apply' })
    expect(within(region).getByText('Recruiter email')).toBeInTheDocument()
    const open = within(region).getByRole('link', { name: /recruiter's email/ })
    expect(open).toHaveAttribute('href', expect.stringContaining('mail.google.com'))
    expect(within(region).getByText(/no job link in it/)).toBeInTheDocument()
    expect(within(region).getByRole('link', { name: /Search for it/ })).toHaveAttribute('href', expect.stringContaining('google.com/search'))
  })

  it('falls back to a search when nothing is stored, and flags postings above the experience range', async () => {
    detail({ apply_url: null, canonical_url: null, source_email_url: null, source: 'linkedin', is_inbound: false, exp_fit: 'above' })
    show(8)
    const region = await screen.findByRole('region', { name: 'Where to apply' })
    expect(within(region).getByText('LinkedIn')).toBeInTheDocument()
    expect(within(region).getByRole('link', { name: 'Search for it' })).toBeInTheDocument()
    expect(screen.getByText('Above your range')).toBeInTheDocument()
  })

  it('shows the apply page first and keeps the original posting one click away', async () => {
    detail({ apply_url: 'https://careers.hcl.example/apply/9', canonical_url: 'https://in.indeed.com/viewjob?jk=1' })
    show(8)
    const region = await screen.findByRole('region', { name: 'Where to apply' })
    expect(within(region).getByRole('link', { name: 'Apply on careers.hcl.example' })).toHaveAttribute('href', 'https://careers.hcl.example/apply/9')
    expect(within(region).getByRole('link', { name: /View original posting/ })).toHaveAttribute('href', 'https://in.indeed.com/viewjob?jk=1')
  })
})

describe('Job detail', () => {
  it('shows the header, the rendered report, the JD and the timeline', async () => {
    const user = userEvent.setup()
    show(3)
    expect(screen.getByLabelText('Loading job')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 1, name: 'Software Engineer II, Identity Platform' })).toBeInTheDocument()
    expect(screen.getByText('Okta')).toBeInTheDocument()
    expect(screen.getByText('A 4.6/5')).toBeInTheDocument()
    expect(screen.getByText('Screening')).toBeInTheDocument()
    expect(screen.getByText('Posting is live')).toBeInTheDocument()
    expect(screen.getByText('Company ATS')).toBeInTheDocument()
    expect(screen.getByText('Career pages')).toBeInTheDocument()

    const apply = screen.getByRole('link', { name: /Apply on example\.com/ })
    expect(apply).toHaveAttribute('href', 'https://example.com/jobs/3')
    expect(apply).toHaveAttribute('target', '_blank')
    expect(apply).toHaveAttribute('rel', expect.stringContaining('noopener'))

    // report markdown: headings, list items, bold
    expect(screen.getByRole('heading', { name: 'Match' })).toBeInTheDocument()
    expect(screen.getByText(/Java 17, Spring Boot, Keycloak SPI/)).toBeInTheDocument()
    expect(screen.getByText('variant A')).toContainHTML('strong')

    await user.click(screen.getByRole('tab', { name: 'Job description' }))
    expect(await screen.findByText(/hiring a backend engineer/)).toBeInTheDocument()

    const timeline = screen.getByRole('list', { name: 'Application timeline' })
    expect(within(timeline).getByText('New → Shortlisted')).toBeInTheDocument()
    expect(within(timeline).getByText('Applied → Screening')).toBeInTheDocument()
  })

  it('asks for an evaluation when there is no report, and queues one', async () => {
    const user = userEvent.setup()
    const evals = capture('POST', '/api/leads/7/evaluate')
    show(7)
    // no report yet, so the page opens on the job description
    expect(await screen.findByText(/hiring a backend engineer/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'AI evaluation' }))
    expect(await screen.findByText('Not evaluated yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Evaluate/ }))
    await waitFor(() => expect(evals).toHaveLength(1))
  })

  it('shortlists, then skips with a reason', async () => {
    const user = userEvent.setup()
    const skips = capture('POST', '/api/leads/7/skip')
    show(7)
    await user.click(await screen.findByRole('button', { name: /Shortlist/ }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Shortlist/ })).not.toBeInTheDocument())
    expect(screen.getAllByText('Shortlisted').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /Skip/ }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Skip' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Reason'), 'stack mismatch')
    await user.click(confirm)
    await waitFor(() => expect(skips).toEqual([{ reason: 'stack mismatch' }]))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('verifies the live status', async () => {
    const user = userEvent.setup()
    const verifies = capture('POST', '/api/leads/3/verify')
    show(3)
    await user.click(await screen.findByRole('button', { name: /Verify/ }))
    await waitFor(() => expect(verifies).toHaveLength(1))
  })

  it('only offers Assist apply once a CV is approved, and says you press Submit', async () => {
    show(2) // Shortlisted, no CV
    const disabled = await screen.findByRole('button', { name: /Assist apply/ })
    expect(disabled).toBeDisabled()
    expect(screen.getByText(/you review and press Submit yourself/)).toBeInTheDocument()
    expect(screen.getByText(/Approve a CV first/)).toBeInTheDocument()
  })

  it('has no button that submits or sends anything', async () => {
    show(4)
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('button', { name: /submit application|send|email/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Assist apply/ })).toBeEnabled() // Ready lead with an approved CV
  })

  it('assist apply starts a run', async () => {
    const user = userEvent.setup()
    const assists = capture('POST', '/api/leads/4/assist-apply')
    show(4)
    await user.click(await screen.findByRole('button', { name: /Assist apply/ }))
    await waitFor(() => expect(assists).toHaveLength(1))
  })

  it('marks a Ready lead applied and shows it on the timeline', async () => {
    const user = userEvent.setup()
    show(4)
    await user.click(await screen.findByRole('button', { name: /Mark applied/ }))
    const timeline = await screen.findByRole('list', { name: 'Application timeline' })
    expect(await within(timeline).findByText('Ready → Applied')).toBeInTheDocument()
    // once applied, the apply steps give way to the status picker
    await waitFor(() => expect(screen.queryByRole('button', { name: /Mark applied/ })).not.toBeInTheDocument())
    expect(screen.getByText('Waiting on the company')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'New status' })).toBeInTheDocument()
  })

  it('says what to do next for a new lead, and updates the status after applying', async () => {
    const user = userEvent.setup()
    const moves = capture('POST', '/api/applications/1/transition')
    const { unmount } = show(7)
    expect(await screen.findByText('Worth applying?')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Steps to apply' })).not.toBeInTheDocument()
    unmount()

    show(1) // Freshworks, Applied
    expect(await screen.findByText('Waiting on the company')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'New status' }), 'Rejected')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(moves).toEqual([{ to_status: 'Rejected', rejected_at_stage: 'Applied' }]))
  })

  it('walks a shortlisted lead through the four apply steps', async () => {
    show(2) // Zoho, Shortlisted, no CV yet
    const steps = await screen.findByRole('list', { name: 'Steps to apply' })
    expect(within(steps).getAllByRole('listitem')).toHaveLength(4)
    expect(within(steps).getByText('Generate a tailored CV')).toBeInTheDocument()
    expect(within(steps).getByRole('button', { name: /Mark applied/ })).toBeEnabled()
  })

  it('lists contact drafts with copy buttons and finds contacts', async () => {
    const user = userEvent.setup()
    const finds = capture('POST', '/api/leads/3/contacts')
    show(3)
    const list = await screen.findByRole('list', { name: 'Outreach drafts' })
    expect(within(list).getByText(/Rahul S/)).toBeInTheDocument()
    await user.click(within(list).getByRole('button', { name: /Copy referral draft/ }))
    expect(await navigator.clipboard.readText()).toMatch(/^Hi Rahul, I saw the SE II Identity Platform/)

    await user.click(screen.getByRole('button', { name: 'Find contacts' }))
    await waitFor(() => expect(finds).toHaveLength(1))
  })

  it('saves notes', async () => {
    const user = userEvent.setup()
    const patches = capture('PATCH', '/api/applications/2')
    show(2)
    const save = await screen.findByRole('button', { name: 'Save notes' })
    expect(save).toBeDisabled()
    await user.type(screen.getByRole('textbox', { name: 'Notes' }), 'ask Priya for a referral')
    await user.click(save)
    await waitFor(() => expect(patches).toEqual([{ notes: 'ask Priya for a referral' }]))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save notes' })).toBeDisabled())
    expect(screen.getByRole('textbox', { name: 'Notes' })).toHaveValue('ask Priya for a referral')
  })

  it('shows an error state for an unknown lead', async () => {
    show(999)
    expect(await screen.findByRole('alert')).toHaveTextContent('404')
  })

  describe('CV flow', () => {
    // Zoho (lead 2): Shortlisted with no CV. The run moves queued -> running -> succeeded over three polls,
    // after which the application has a PDF.
    function cvScenario() {
      const state = { run: null as RunOut | null, polls: 0, pdf: false, approved: false, cvBodies: [] as unknown[], patches: [] as unknown[] }
      const lead = makeLeads()[1]
      server.use(
        http.get('/api/leads/2', () => {
          const d = makeDetail(lead)
          Object.assign(d.application!, { has_cv_pdf: state.pdf, resume_variant: state.pdf ? 'B' : null, cv_approved: state.approved })
          return HttpResponse.json(d)
        }),
        http.post('/api/leads/2/cv', async ({ request }) => {
          const body = (await request.json()) as { variant: 'A' | 'B' }
          state.cvBodies.push(body)
          state.run = { id: 500, kind: 'cv', state: 'queued', lead_id: 2, params: body, started_at: null, finished_at: null, summary: null, error: null, created_at: new Date().toISOString() }
          return HttpResponse.json(state.run, { status: 202 })
        }),
        http.get('/api/runs', ({ request }) => {
          expect(new URL(request.url).searchParams.get('lead_id')).toBe('2')
          if (!state.run) return HttpResponse.json([])
          state.polls++
          state.run.state = state.polls < 2 ? 'queued' : state.polls < 4 ? 'running' : 'succeeded'
          if (state.run.state === 'succeeded') state.pdf = true
          return HttpResponse.json([state.run])
        }),
        http.patch('/api/applications/2', async ({ request }) => {
          const body = (await request.json()) as { cv_approved?: boolean }
          state.patches.push(body)
          if (body.cv_approved) state.approved = true
          return HttpResponse.json({ ...makeDetail(lead).application, has_cv_pdf: true, cv_approved: state.approved })
        }),
      )
      return state
    }

    it('generates a variant, shows run progress and the log, then previews and approves the PDF', async () => {
      const user = userEvent.setup()
      const state = cvScenario()
      show(2)
      const generateB = await screen.findByRole('button', { name: 'Generate CV B' })
      expect(screen.queryByTestId('pdf')).not.toBeInTheDocument()
      await user.click(generateB)
      await waitFor(() => expect(state.cvBodies).toEqual([{ variant: 'B' }]))

      // progress while the run is queued / running, with the generate buttons locked
      expect(await screen.findByText(/Generating CV/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Generate CV A' })).toBeDisabled()
      const runs = await screen.findByRole('list', { name: 'Runs for this lead' })
      expect(within(runs).getByText('CV B')).toBeInTheDocument()

      // the log tail opens on demand
      await user.click(within(runs).getByText('Log'))
      expect(await screen.findByLabelText('Log of run 500')).toHaveTextContent('linkedin: 48 rows')

      // the run settles -> the job refetches -> the preview appears with the PDF url
      const pdf = await screen.findByTestId('pdf', {}, { timeout: 4000 })
      expect(pdf.dataset.url).toMatch(/^\/api\/applications\/2\/cv\.pdf\?v=/)
      expect(screen.queryByText(/Generating CV/)).not.toBeInTheDocument()
      expect(within(runs).getByText(/succeeded/)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /Open PDF/ })).toHaveAttribute('target', '_blank')
      expect(screen.getByText('Variant B')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Approve CV' }))
      await waitFor(() => expect(state.patches).toEqual([{ cv_approved: true }]))
      expect(await screen.findByText('Approved')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Approve CV' })).not.toBeInTheDocument()
      // an approved CV unlocks Assist apply
      expect(screen.getByRole('button', { name: /Assist apply/ })).toBeEnabled()
    })

    it('shows a failed run with its error', async () => {
      const user = userEvent.setup()
      server.use(
        http.post('/api/leads/2/cv', () =>
          HttpResponse.json({ id: 501, kind: 'cv', state: 'queued', lead_id: 2, params: { variant: 'A' }, started_at: null, finished_at: null, summary: null, error: null, created_at: new Date().toISOString() }, { status: 202 }),
        ),
        http.get('/api/runs', () =>
          HttpResponse.json([{ id: 501, kind: 'cv', state: 'failed', lead_id: 2, params: { variant: 'A' }, started_at: null, finished_at: null, summary: null, error: 'fact-check failed: invented employer', created_at: new Date().toISOString() }]),
        ),
      )
      show(2)
      await user.click(await screen.findByRole('button', { name: 'Generate CV A' }))
      expect(await screen.findByText('fact-check failed: invented employer')).toBeInTheDocument()
      expect(screen.queryByTestId('pdf')).not.toBeInTheDocument()
    })
  })
})


describe('Email HR', () => {
  const connectGmail = async () => {
    await api.PUT('/api/secrets/{name}', { params: { path: { name: 'gmail_address' } }, body: { value: 'me@example.com' } })
    await api.PUT('/api/secrets/{name}', { params: { path: { name: 'gmail_app_password' } }, body: { value: 'abcdabcdabcdabcd' } })
  }
  beforeEach(resetMockDb)

  it('finds the HR address by itself and sends the filled-in email with one click', async () => {
    await connectGmail()
    const user = userEvent.setup()
    const sends = capture('POST', '/api/reachout/jobs/1/send')
    show(1)
    const card = await screen.findByRole('region', { name: 'Email HR' }, { timeout: 3000 })
    // the lookup ran without a click and the best address is already chosen
    const found = await within(card).findByRole('radio', { name: /jobs@freshworks\.com/ })
    expect(found).toBeChecked()
    expect(within(card).getByRole('radio', { name: /careers@freshworks\.com/ })).not.toBeChecked() // unverified guesses are never preselected
    const preview = within(card).getByLabelText('Email preview')
    expect(within(preview).getByText(/Application for Senior Software Engineer - Java/)).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Send to jobs@freshworks.com' }))
    await waitFor(() => expect(sends).toHaveLength(1))
    expect(sends[0]).toMatchObject({ to_email: 'jobs@freshworks.com', mode: 'send', confirm: true, attach: 'base', extra_lead_ids: [] })
    expect(await within(card).findByText(/You emailed jobs@freshworks\.com on/)).toBeInTheDocument()
    expect(within(card).getByText(/less than 14 days ago/)).toBeInTheDocument() // a second email to the same address needs "Send anyway"
  })

  it('lets you type an address by hand and greets the name you give', async () => {
    await connectGmail()
    const user = userEvent.setup()
    const sends = capture('POST', '/api/reachout/jobs/2/send')
    show(2)
    const card = await screen.findByRole('region', { name: 'Email HR' }, { timeout: 3000 })
    await within(card).findByRole('radio', { name: /jobs@zoho\.com/ })
    await user.click(within(card).getByRole('radio', { name: 'Type an address' }))
    const send = within(card).getByRole('button', { name: 'Send email' })
    expect(send).toBeDisabled()
    await user.type(within(card).getByLabelText('HR email'), 'asha@zoho.com')
    await user.type(within(card).getByLabelText('Their name (optional)'), 'Asha Rao')
    await waitFor(() => expect(within(card).getByText(/Hi Asha,/)).toBeInTheDocument())
    await user.click(within(card).getByRole('button', { name: 'Send to asha@zoho.com' }))
    await waitFor(() => expect(sends).toHaveLength(1))
    expect(sends[0]).toMatchObject({ to_email: 'asha@zoho.com', to_name: 'Asha Rao' })
  })

  it('does not offer to send until Gmail is connected, and can save a Gmail draft instead', async () => {
    const user = userEvent.setup()
    show(1)
    const card = await screen.findByRole('region', { name: 'Email HR' }, { timeout: 3000 })
    await within(card).findByRole('radio', { name: /jobs@freshworks\.com/ })
    expect(within(card).getByText(/Gmail is not connected/)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Send to/ })).toBeDisabled()
    expect(within(card).getByRole('button', { name: /Save as Gmail draft/ })).toBeDisabled()
    await connectGmail()
    await user.click(within(card).getByRole('button', { name: 'Search again' })) // refetches the card data
    await waitFor(() => expect(within(card).getByRole('button', { name: /Save as Gmail draft/ })).toBeEnabled())
  })
})
