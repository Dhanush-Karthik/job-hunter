// MSW handlers covering every contract route (lead-owned). Stateful in memory; resetMockDb() between tests.
import { http, HttpResponse } from 'msw'
import { TRANSITIONS, type AppStatus, type ApplicationOut, type LeadSummary, type RunOut } from '@/api/client'
import {
  ago,
  makeApplication,
  makeDetail,
  makeEvents,
  makeLeads,
  makeOutreach,
  makeProfiles,
  makeProposals,
  makeRuns,
  makeSources,
  SETTINGS,
} from './fixtures'

function fresh() {
  const leads = makeLeads()
  const apps = new Map<number, ApplicationOut>()
  for (const l of leads) if (l.application_id) apps.set(l.application_id, makeApplication(l))
  return {
    leads,
    apps,
    events: new Map([...apps.values()].map((a) => [a.id, makeEvents(a)])),
    proposals: makeProposals(),
    outreach: makeOutreach(),
    runs: makeRuns(),
    sources: makeSources(),
    profiles: makeProfiles(),
    settings: structuredClone(SETTINGS),
    secrets: { gmail_address: false, gmail_app_password: false } as Record<string, boolean>,
    cv: { A: true, B: false } as Record<string, boolean>,
    nextRun: 100,
    nextEvent: 1000,
  }
}

let db = fresh()
export function resetMockDb() {
  db = fresh()
}

const notFound = () => HttpResponse.json({ detail: 'not found' }, { status: 404 })
const lead = (id: string | readonly string[] | undefined) => db.leads.find((l) => l.id === Number(id))
const detail = (l: LeadSummary) => {
  const d = makeDetail(l)
  if (l.application_id) {
    d.application = db.apps.get(l.application_id) ?? null
    d.events = db.events.get(l.application_id) ?? []
  }
  d.outreach = db.outreach.filter((o) => o.lead_id === l.id)
  return d
}

function newRun(kind: RunOut['kind'], lead_id: number | null = null, params: Record<string, unknown> = {}): RunOut {
  const r: RunOut = { id: db.nextRun++, kind, state: 'queued', lead_id, params, started_at: null, finished_at: null, summary: null, error: null, created_at: new Date().toISOString() }
  db.runs.unshift(r)
  return r
}

function setStatus(l: LeadSummary, to: AppStatus, note: string | null = null, rejected_at_stage: AppStatus | null = null) {
  const from = l.status
  if (!l.application_id) {
    l.application_id = l.id
    db.apps.set(l.id, makeApplication({ ...l, status: 'New' }))
  }
  const app = db.apps.get(l.application_id)!
  Object.assign(app, { status: to, updated_at: new Date().toISOString() })
  if (to === 'Applied') app.applied_at = new Date().toISOString()
  if (to === 'Rejected') app.rejected_at_stage = rejected_at_stage
  l.status = to
  const ev = db.events.get(app.id) ?? []
  ev.push({ id: db.nextEvent++, application_id: app.id, from_status: from, to_status: to, at: new Date().toISOString(), actor: 'owner', note })
  db.events.set(app.id, ev)
  return app
}

const csv = (rows: ApplicationOut[]) =>
  ['id,company,title,status,applied_at,source', ...rows.map((a) => [a.id, a.company, a.title, a.status, a.applied_at ?? '', a.source].map((v) => `"${String(v).replaceAll('"', '""')}"`).join(','))].join('\n')

export const handlers = [
  http.get('/api/health', () =>
    HttpResponse.json({ ok: true, version: '0.1.0-mock', db: true, scheduler: true, services: [{ name: 'claude CLI', ok: true, detail: null }, { name: 'gmail', ok: false, detail: 'app password not set' }] }),
  ),

  // ---- leads
  http.get('/api/leads', ({ request }) => {
    const u = new URL(request.url).searchParams
    let items = db.leads.filter((l) => u.get('include_rejected') === 'true' || l.prefilter_pass || l.restored)
    const q = u.get('q')?.toLowerCase()
    if (q) items = items.filter((l) => `${l.company} ${l.title}`.toLowerCase().includes(q))
    const status = u.getAll('status')
    if (status.length) items = items.filter((l) => status.includes(l.status))
    const source = u.getAll('source')
    if (source.length) items = items.filter((l) => source.includes(l.source))
    const channel = u.getAll('channel')
    if (channel.length) items = items.filter((l) => channel.includes(l.apply_channel))
    if (u.get('min_score')) items = items.filter((l) => l.quick_score >= Number(u.get('min_score')))
    if (u.get('fresh_only') === 'true') items = items.filter((l) => l.is_fresh)
    if (u.get('inbound_only') === 'true') items = items.filter((l) => l.is_inbound)
    const sort = u.get('sort') ?? 'score'
    const key = (l: LeadSummary) =>
      sort === 'found_at' ? l.found_at : sort === 'posted_at' ? (l.posted_at ?? '') : sort === 'eval_score' ? (l.eval_score ?? -1) : l.quick_score
    items = [...items].sort((a, b) => (key(a) < key(b) ? 1 : -1))
    const limit = Number(u.get('limit') ?? 50)
    const offset = Number(u.get('offset') ?? 0)
    return HttpResponse.json({ items: items.slice(offset, offset + limit), total: items.length, limit, offset })
  }),
  http.get('/api/leads/quick-apply', () =>
    HttpResponse.json(db.leads.filter((l) => l.apply_channel === 'platform_quick' && ['Shortlisted', 'Ready'].includes(l.status))),
  ),
  http.post('/api/leads', async ({ request }) => {
    const b = (await request.json()) as { company: string; title: string; url?: string; location?: string }
    const base = makeLeads()[0]
    const l: LeadSummary = { ...base, id: Math.max(...db.leads.map((x) => x.id)) + 1, source: 'manual', company: b.company, title: b.title, location: b.location ?? null, apply_url: b.url ?? null, canonical_url: b.url ?? null, status: 'New', application_id: null, eval_score: null, eval_grade: null, found_at: new Date().toISOString() }
    db.leads.push(l)
    return HttpResponse.json(detail(l), { status: 201 })
  }),
  http.post('/api/leads/bulk', async ({ request }) => {
    const b = (await request.json()) as { ids: number[]; action: string; reason?: string }
    const ok: number[] = []
    const failed: Record<string, string> = {}
    const run_ids: number[] = []
    for (const id of b.ids) {
      const l = lead(String(id))
      if (!l) { failed[id] = 'not found'; continue }
      if (b.action === 'shortlist') setStatus(l, 'Shortlisted')
      else if (b.action === 'skip') setStatus(l, 'Skipped', b.reason ?? null)
      else if (b.action === 'restore') l.restored = true
      else run_ids.push(newRun(b.action === 'evaluate' ? 'evaluate' : 'verify', id).id)
      ok.push(id)
    }
    return HttpResponse.json({ ok, failed, run_ids })
  }),
  http.get('/api/leads/:id', ({ params }) => {
    const l = lead(params.id)
    return l ? HttpResponse.json(detail(l)) : notFound()
  }),
  http.post('/api/leads/:id/shortlist', ({ params }) => {
    const l = lead(params.id)
    if (!l) return notFound()
    setStatus(l, 'Shortlisted')
    return HttpResponse.json(detail(l))
  }),
  http.post('/api/leads/:id/skip', async ({ params, request }) => {
    const l = lead(params.id)
    if (!l) return notFound()
    const b = (await request.json()) as { reason: string }
    setStatus(l, 'Skipped', b.reason)
    return HttpResponse.json(detail(l))
  }),
  http.post('/api/leads/:id/restore', ({ params }) => {
    const l = lead(params.id)
    if (!l) return notFound()
    l.restored = true
    return HttpResponse.json(detail(l))
  }),
  ...(['evaluate', 'verify', 'contacts', 'assist-apply'] as const).map((action) =>
    http.post(`/api/leads/:id/${action}`, ({ params }) => {
      const l = lead(params.id)
      if (!l) return notFound()
      const kind = action === 'assist-apply' ? 'assist_apply' : action
      return HttpResponse.json(newRun(kind, l.id), { status: 202 })
    }),
  ),
  http.post('/api/leads/:id/cv', async ({ params, request }) => {
    const l = lead(params.id)
    if (!l) return notFound()
    const b = (await request.json()) as { variant: 'A' | 'B' }
    return HttpResponse.json(newRun('cv', l.id, { variant: b.variant }), { status: 202 })
  }),
  http.get('/api/leads/:id/outreach', ({ params }) => HttpResponse.json(db.outreach.filter((o) => o.lead_id === Number(params.id)))),

  // ---- applications
  http.get('/api/applications', ({ request }) => {
    const u = new URL(request.url).searchParams
    let items = [...db.apps.values()]
    const status = u.getAll('status')
    if (status.length) items = items.filter((a) => status.includes(a.status))
    const q = u.get('q')?.toLowerCase()
    if (q) items = items.filter((a) => `${a.company} ${a.title}`.toLowerCase().includes(q))
    return HttpResponse.json(items)
  }),
  http.get('/api/applications/export.csv', () => new HttpResponse(csv([...db.apps.values()]), { headers: { 'Content-Type': 'text/csv' } })),
  http.get('/api/applications/:id', ({ params }) => {
    const a = db.apps.get(Number(params.id))
    return a ? HttpResponse.json(a) : notFound()
  }),
  http.patch('/api/applications/:id', async ({ params, request }) => {
    const a = db.apps.get(Number(params.id))
    if (!a) return notFound()
    const b = (await request.json()) as Partial<ApplicationOut>
    for (const [k, v] of Object.entries(b)) if (v !== null && v !== undefined) (a as Record<string, unknown>)[k] = v
    a.updated_at = new Date().toISOString()
    return HttpResponse.json(a)
  }),
  http.post('/api/applications/:id/transition', async ({ params, request }) => {
    const a = db.apps.get(Number(params.id))
    if (!a) return notFound()
    const b = (await request.json()) as { to_status: AppStatus; rejected_at_stage?: AppStatus; note?: string }
    if (!TRANSITIONS[a.status].includes(b.to_status)) return HttpResponse.json({ detail: `cannot move ${a.status} -> ${b.to_status}` }, { status: 409 })
    if (b.to_status === 'Rejected' && !b.rejected_at_stage) return HttpResponse.json({ detail: 'rejected_at_stage required' }, { status: 422 })
    const l = db.leads.find((x) => x.id === a.lead_id)!
    return HttpResponse.json(setStatus(l, b.to_status, b.note ?? null, b.rejected_at_stage ?? null))
  }),
  http.get('/api/applications/:id/events', ({ params }) => HttpResponse.json(db.events.get(Number(params.id)) ?? [])),
  http.get('/api/applications/:id/cv.pdf', () => notFound()),

  // ---- proposals
  http.get('/api/proposals', ({ request }) => {
    const state = new URL(request.url).searchParams.get('state') ?? 'pending'
    return HttpResponse.json(db.proposals.filter((p) => p.state === state))
  }),
  http.post('/api/proposals/:id/accept', async ({ params, request }) => {
    const p = db.proposals.find((x) => x.id === Number(params.id))
    if (!p) return notFound()
    const b = (await request.json()) as { payload?: Record<string, unknown> | null }
    if (b.payload) p.payload = b.payload
    p.state = 'accepted'
    const to = p.payload.to_status as AppStatus | undefined
    const l = db.leads.find((x) => x.id === p.lead_id)
    if (to && l) setStatus(l, to, `accepted proposal #${p.id}`)
    return HttpResponse.json(p)
  }),
  http.post('/api/proposals/:id/dismiss', ({ params }) => {
    const p = db.proposals.find((x) => x.id === Number(params.id))
    if (!p) return notFound()
    p.state = 'dismissed'
    return HttpResponse.json(p)
  }),
  http.post('/api/proposals/:id/convert', ({ params }) => {
    const p = db.proposals.find((x) => x.id === Number(params.id))
    const l = p && db.leads.find((x) => x.id === p.lead_id)
    if (!p || !l) return notFound()
    p.state = 'accepted'
    return HttpResponse.json(setStatus(l, 'Shortlisted', 'inbound converted'))
  }),

  // ---- outreach
  http.get('/api/outreach', ({ request }) => {
    const u = new URL(request.url).searchParams
    let items = db.outreach
    if (u.get('kind')) items = items.filter((o) => o.kind === u.get('kind'))
    if (u.get('due_only') === 'true') items = items.filter((o) => !o.sent_at && o.due_at && o.due_at <= new Date().toISOString())
    if (u.get('sent') === 'true') items = items.filter((o) => o.sent_at)
    if (u.get('sent') === 'false') items = items.filter((o) => !o.sent_at)
    return HttpResponse.json(items)
  }),
  http.patch('/api/outreach/:id', async ({ params, request }) => {
    const o = db.outreach.find((x) => x.id === Number(params.id))
    if (!o) return notFound()
    Object.assign(o, Object.fromEntries(Object.entries((await request.json()) as object).filter(([, v]) => v != null)))
    return HttpResponse.json(o)
  }),
  http.post('/api/outreach/:id/mark-sent', ({ params }) => {
    const o = db.outreach.find((x) => x.id === Number(params.id))
    if (!o) return notFound()
    o.sent_at = new Date().toISOString()
    return HttpResponse.json(o)
  }),
  http.post('/api/outreach/:id/snooze', async ({ params, request }) => {
    const o = db.outreach.find((x) => x.id === Number(params.id))
    if (!o) return notFound()
    const { days } = (await request.json()) as { days: number }
    o.snoozed_until = new Date(Date.now() + days * 86400_000).toISOString()
    return HttpResponse.json(o)
  }),

  // ---- runs
  http.get('/api/runs', () => HttpResponse.json(db.runs)),
  http.get('/api/runs/stream', () => new HttpResponse(': mock stream\n\n', { headers: { 'Content-Type': 'text/event-stream' } })),
  http.get('/api/runs/:id', ({ params }) => {
    const r = db.runs.find((x) => x.id === Number(params.id))
    return r ? HttpResponse.json(r) : notFound()
  }),
  http.get('/api/runs/:id/log', ({ params }) =>
    HttpResponse.json({ run_id: Number(params.id), text: '[09:00:01] start\n[09:00:04] linkedin: 48 rows\n[09:00:09] naukri: 61 rows\n[09:00:10] done', truncated: false }),
  ),
  http.post('/api/runs/:id/cancel', ({ params }) => {
    const r = db.runs.find((x) => x.id === Number(params.id))
    if (!r) return notFound()
    r.state = 'cancelled'
    return HttpResponse.json(r)
  }),
  http.post('/api/intake/run', () => HttpResponse.json([newRun('intake_boards'), newRun('intake_remote'), newRun('intake_gmail')], { status: 202 })),

  // ---- today / analytics
  http.get('/api/today', () => {
    const live = db.leads.filter((l) => l.prefilter_pass)
    return HttpResponse.json({
      interview_calls_week: 2,
      interview_calls_prev_week: 1,
      applied_week: 23,
      applied_target: db.settings.targets.applied_per_week,
      referrals_week: 6,
      referrals_target: db.settings.targets.referrals_per_week,
      fresh_hot_leads: live.filter((l) => l.is_fresh && l.status === 'New').sort((a, b) => b.quick_score - a.quick_score).slice(0, 5),
      actions: [
        { kind: 'inbound', title: 'TalentCorp Consulting: Keycloak / IAM Engineer', subtitle: 'Recruiter reached out 2 h ago', lead_id: 8, proposal_id: 2 },
        { kind: 'proposal', title: 'Freshworks replied: move to Screening?', subtitle: 'confidence 93%', application_id: 1, proposal_id: 1 },
        { kind: 'follow_up', title: 'Follow up with Freshworks', subtitle: 'due 2 h ago', application_id: 1, outreach_id: 2, due_at: ago(2) },
        { kind: 'quick_apply', title: '2 quick-applies waiting', subtitle: 'Zoho, Postman', lead_id: null },
        { kind: 'profile_refresh', title: 'Refresh Naukri profile', subtitle: 'last refreshed 30 h ago', platform: 'naukri' },
        { kind: 'cv_review', title: 'Approve CV for Razorpay SDE 2', subtitle: 'variant A generated', lead_id: 4, application_id: 4 },
      ],
      health: [
        { name: 'scheduler', ok: true, detail: null },
        { name: 'claude CLI', ok: true, detail: null },
        { name: 'gmail', ok: false, detail: 'app password not set' },
        { name: 'glassdoor', ok: false, detail: 'paused after 3x 429' },
      ],
    })
  }),
  http.get('/api/analytics/funnel', () =>
    HttpResponse.json({
      stages: [
        { status: 'Shortlisted', count: 120, conversion_from_prev: null },
        { status: 'Applied', count: 84, conversion_from_prev: 0.7 },
        { status: 'Screening', count: 9, conversion_from_prev: 0.107 },
        { status: 'Technical', count: 4, conversion_from_prev: 0.444 },
        { status: 'Final', count: 1, conversion_from_prev: 0.25 },
        { status: 'Offer', count: 0, conversion_from_prev: 0 },
      ],
      date_from: null,
      date_to: null,
    }),
  ),
  http.get('/api/analytics/breakdown', ({ request }) => {
    const by = new URL(request.url).searchParams.get('by') ?? 'source'
    const keys: Record<string, string[]> = {
      source: ['linkedin', 'naukri', 'careerops_scan', 'gmail_inbound', 'google', 'indeed'],
      channel: ['platform_quick', 'company_ats', 'email'],
      title: ['Java Developer', 'Backend Engineer', 'SDE 2', 'Platform Engineer'],
      variant: ['A', 'B'],
      role_family: ['P1', 'P2', 'other'],
    }
    return HttpResponse.json({ by, rows: keys[by].map((key, i) => { const applied = 30 - i * 4; const calls = Math.max(0, 4 - i); return { key, applied, calls, rate: applied ? calls / applied : null } }) })
  }),
  http.get('/api/analytics/weekly', () =>
    HttpResponse.json(Array.from({ length: 8 }, (_, i) => ({ week_start: ago((7 - i) * 168), applied: 10 + i * 6, calls: Math.floor(i / 2), referrals: 2 + i, applied_target: 60, referrals_target: 15 }))),
  ),
  http.get('/api/analytics/response-times', () => HttpResponse.json({ median_days_to_first_response: 4.5, p90_days_to_first_response: 11, samples: 14 })),
  http.get('/api/analytics/rejects', () =>
    HttpResponse.json([
      { reason: 'location', count: 312, sample_lead_ids: [10] },
      { reason: 'experience', count: 120, sample_lead_ids: [11] },
      { reason: 'stack', count: 88, sample_lead_ids: [] },
      { reason: 'ctc', count: 14, sample_lead_ids: [] },
      { reason: 'stale', count: 40, sample_lead_ids: [] },
    ]),
  ),

  // ---- config
  http.get('/api/sources', () => HttpResponse.json(db.sources)),
  http.patch('/api/sources/:source', async ({ params, request }) => {
    const s = db.sources.find((x) => x.source === params.source)
    if (!s) return notFound()
    const b = (await request.json()) as { enabled?: boolean; unpause?: boolean }
    if (b.enabled != null) s.enabled = b.enabled
    if (b.unpause) Object.assign(s, { paused_until: null, consecutive_failures: 0 })
    return HttpResponse.json(s)
  }),
  http.get('/api/settings', () => HttpResponse.json(db.settings)),
  http.put('/api/settings', async ({ request }) => {
    db.settings = (await request.json()) as typeof db.settings
    return HttpResponse.json(db.settings)
  }),
  http.get('/api/secrets', () => HttpResponse.json(Object.entries(db.secrets).map(([name, present]) => ({ name, present })))),
  http.put('/api/secrets/:name', ({ params }) => {
    db.secrets[String(params.name)] = true
    return new HttpResponse(null, { status: 204 })
  }),
  http.get('/api/profiles', () => HttpResponse.json(db.profiles)),
  http.patch('/api/profiles/:platform', async ({ params, request }) => {
    const p = db.profiles.find((x) => x.platform === params.platform)
    if (!p) return notFound()
    const b = (await request.json()) as { checklist?: Record<string, boolean>; refreshed_now?: boolean }
    if (b.checklist) p.checklist = { ...p.checklist, ...b.checklist }
    if (b.refreshed_now) Object.assign(p, { last_refreshed_at: new Date().toISOString(), refresh_due: false })
    return HttpResponse.json(p)
  }),
  http.get('/api/setup', () => {
    const gmail = db.secrets.gmail_address && db.secrets.gmail_app_password
    return HttpResponse.json({ cv_a: db.cv.A, cv_b: db.cv.B, gmail, claude_cli: true, careerops: true, playwright: true, complete: db.cv.A && gmail })
  }),
  http.put('/api/setup/cv', async ({ request }) => {
    const b = (await request.json()) as { variant: 'A' | 'B' }
    db.cv[b.variant] = true
    const gmail = db.secrets.gmail_address && db.secrets.gmail_app_password
    return HttpResponse.json({ cv_a: db.cv.A, cv_b: db.cv.B, gmail, claude_cli: true, careerops: true, playwright: true, complete: db.cv.A && gmail })
  }),
]
