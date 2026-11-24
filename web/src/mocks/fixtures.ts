// Deterministic sample data for MSW (lead-owned). Shapes follow contracts/openapi.json exactly.
import type {
  ApplicationOut,
  Company,
  EventOut,
  Insight,
  LeadDetail,
  LeadSummary,
  OutreachOut,
  ProfileOut,
  ProposalOut,
  RunOut,
  Settings,
  SourceOut,
} from '@/api/client'

const NOW = new Date('2026-11-13T09:00:00+05:30').getTime()
const ago = (h: number) => new Date(NOW - h * 3600_000).toISOString()
const ahead = (h: number) => new Date(NOW + h * 3600_000).toISOString()

type Seed = Partial<LeadSummary> & Pick<LeadSummary, 'company' | 'title' | 'source'>

const seeds: Seed[] = [
  { company: 'Freshworks', title: 'Senior Software Engineer - Java', source: 'linkedin', location: 'Chennai', work_mode: 'hybrid', exp_min: 3, exp_max: 6, quick_score: 0.92, eval_score: 4.4, eval_grade: 'A', is_live: true, apply_channel: 'company_ats', posted_at: ago(10) },
  { company: 'Zoho', title: 'Backend Developer (Java)', source: 'naukri', location: 'Chennai', work_mode: 'onsite', exp_min: 2, exp_max: 5, quick_score: 0.88, eval_score: 4.1, eval_grade: 'B', is_live: true, apply_channel: 'platform_quick', posted_at: ago(20) },
  { company: 'Okta', title: 'Software Engineer II, Identity Platform', source: 'careerops_scan', location: 'Bengaluru', work_mode: 'hybrid', exp_min: 2, exp_max: 5, quick_score: 0.9, eval_score: 4.6, eval_grade: 'A', is_live: true, apply_channel: 'company_ats', posted_at: ago(30), role_family: 'P1' },
  { company: 'Razorpay', title: 'SDE 2 - Payments Backend', source: 'linkedin', location: 'Bengaluru', work_mode: 'hybrid', exp_min: 3, exp_max: 5, ctc_min: 25, ctc_max: 40, quick_score: 0.85, apply_channel: 'platform_quick', posted_at: ago(5) },
  { company: 'Hashicorp Talent (via Uplers)', title: 'Remote Java Engineer', source: 'gmail_alert', source_detail: 'uplers', location: 'Remote India', work_mode: 'remote', exp_min: 3, exp_max: 7, quick_score: 0.71, apply_channel: 'email', posted_at: ago(40) },
  { company: 'Chargebee', title: 'Platform Engineer', source: 'google', location: 'Chennai', work_mode: 'hybrid', exp_min: 2, exp_max: 4, quick_score: 0.74, apply_channel: 'company_ats', posted_at: ago(70), role_family: 'P2' },
  { company: 'Kissflow', title: 'Java Developer', source: 'indeed', location: 'Chennai', work_mode: 'onsite', exp_min: 2, exp_max: 4, ctc_min: 8, ctc_max: 14, quick_score: 0.66, apply_channel: 'platform_quick', posted_at: ago(100) },
  { company: 'TalentCorp Consulting', title: 'Keycloak / IAM Engineer', source: 'gmail_inbound', location: 'Bengaluru', work_mode: 'hybrid', quick_score: 0.95, is_inbound: true, apply_channel: 'email', posted_at: ago(2), role_family: 'P1', call_chance: 'high', pick_reason: 'Recruiter-led Java backend role at 2-5 years; Keycloak and OIDC depth match the CV.' },
  { company: 'Atlassian', title: 'Backend Engineer, Jira Cloud', source: 'careerops_scan', location: 'Remote India', work_mode: 'remote', exp_min: 3, exp_max: 6, quick_score: 0.8, eval_score: 3.9, eval_grade: 'B', is_live: true, apply_channel: 'company_ats', posted_at: ago(50) },
  { company: 'Infosys', title: 'Java Developer', source: 'naukri', location: 'Pune', work_mode: 'onsite', exp_min: 3, exp_max: 5, quick_score: 0.2, prefilter_pass: false, prefilter_reasons: ['location: Pune not in target cities'], apply_channel: 'platform_quick', posted_at: ago(15) },
  { company: 'Acme Staffing', title: 'Principal Engineer', source: 'glassdoor', location: 'Bengaluru', work_mode: 'onsite', exp_min: 12, exp_max: 18, quick_score: 0.1, prefilter_pass: false, prefilter_reasons: ['experience: min 12 >= 6'], apply_channel: 'company_ats', posted_at: ago(80) },
  { company: 'Postman', title: 'Software Engineer - Java Services', source: 'linkedin', location: 'Bengaluru', work_mode: 'hybrid', exp_min: 2, exp_max: 4, quick_score: 0.83, apply_channel: 'platform_quick', posted_at: ago(26) },
]

/** Mirrors pipeline.experience.exp_fit for the owner's 2-4 year range. */
const expFit = (min: number | null | undefined): LeadSummary['exp_fit'] => (min == null ? 'unknown' : min <= 3 ? 'ok' : min <= 4 ? 'stretch' : 'above')

const STATUS_BY_INDEX: Record<number, LeadSummary['status']> = { 0: 'Applied', 1: 'Shortlisted', 2: 'Screening', 3: 'Ready', 8: 'Rejected', 11: 'Shortlisted' }

export function makeLeads(): LeadSummary[] {
  return seeds.map((s, i) => {
    const id = i + 1
    const posted = s.posted_at ?? ago(24)
    const status = STATUS_BY_INDEX[i] ?? 'New'
    return {
      id,
      source_detail: null,
      location: null,
      work_mode: 'unknown',
      apply_channel: 'unknown',
      apply_url: `https://example.com/jobs/${id}`,
      canonical_url: `https://example.com/jobs/${id}`,
      exp_min: null,
      exp_max: null,
      ctc_min: null,
      ctc_max: null,
      found_at: posted,
      is_fresh: NOW - new Date(posted).getTime() < 48 * 3600_000,
      role_family: 'P1',
      quick_score: 0.5,
      eval_score: null,
      eval_grade: null,
      is_live: null,
      is_inbound: false,
      prefilter_pass: true,
      prefilter_reasons: [],
      prefilter_tags: s.ctc_max == null ? ['CTC unknown'] : [],
      restored: false,
      duplicates: i === 1 ? 2 : 0,
      application_id: status === 'New' ? null : id,
      ...s,
      exp_fit: s.exp_fit ?? expFit(s.exp_min),
      posted_at: posted,
      status,
    }
  })
}

export function makeApplication(lead: LeadSummary): ApplicationOut {
  const applied = ['Applied', 'Screening', 'Rejected'].includes(lead.status)
  return {
    id: lead.application_id ?? lead.id,
    lead_id: lead.id,
    company: lead.company,
    title: lead.title,
    status: lead.status,
    resume_variant: applied || lead.status === 'Ready' ? 'A' : null,
    has_cv_pdf: applied || lead.status === 'Ready',
    cv_approved: applied || lead.status === 'Ready',
    applied_at: applied ? ago(72) : null,
    next_follow_up_at: lead.status === 'Applied' ? ahead(30) : null,
    referral_contact: null,
    recruiter: lead.status === 'Screening' ? 'Priya (Okta TA)' : null,
    notes: null,
    rejected_at_stage: lead.status === 'Rejected' ? 'Applied' : null,
    source: lead.source,
    apply_channel: lead.apply_channel,
    eval_score: lead.eval_score ?? null,
    created_at: ago(96),
    updated_at: ago(12),
  }
}

export function makeEvents(app: ApplicationOut): EventOut[] {
  const ev: EventOut[] = [{ id: app.id * 10, application_id: app.id, from_status: 'New', to_status: 'Shortlisted', at: ago(96), actor: 'owner', note: null }]
  if (app.applied_at) ev.push({ id: app.id * 10 + 1, application_id: app.id, from_status: 'Ready', to_status: 'Applied', at: app.applied_at, actor: 'owner', note: null })
  if (app.status === 'Screening') ev.push({ id: app.id * 10 + 2, application_id: app.id, from_status: 'Applied', to_status: 'Screening', at: ago(6), actor: 'proposal', note: 'Recruiter email: "Interview availability"' })
  return ev
}

export const REPORT_MD = `# Evaluation: Okta - Software Engineer II, Identity Platform

**Score 4.6 / 5 (A)** · Live: yes (verified today)

## Match
- Java 17, Spring Boot, Keycloak SPI work maps directly to the identity platform team.
- OAuth2/OIDC depth is a strong differentiator.

## Gaps
- Go is "nice to have"; mention willingness to ramp up.

## Recommendation
Apply with **variant A**; ask for a referral from the Bengaluru IAM team.
`

export function makeDetail(lead: LeadSummary): LeadDetail {
  const application = lead.application_id ? makeApplication(lead) : null
  return {
    ...lead,
    source_email_url: lead.source === 'gmail_inbound' ? 'https://mail.google.com/mail/u/0/#search/rfc822msgid:example%40mail' : null,
    jd_text: `## ${lead.title}\n\n${lead.company} is hiring a backend engineer with 2-5 years of Java, Spring Boot and microservices experience.\n\n- Build and run REST services\n- Kafka, PostgreSQL, Kubernetes\n- OAuth2 / OIDC a plus`,
    evaluation:
      lead.eval_score != null
        ? { id: lead.id, score: lead.eval_score, grade: lead.eval_grade ?? null, report_md: REPORT_MD, is_live: lead.is_live ?? null, live_verified_at: ago(3), created_at: ago(4) }
        : null,
    application,
    events: application ? makeEvents(application) : [],
    outreach: [],
    duplicate_ids: lead.duplicates ? [100 + lead.id, 200 + lead.id] : [],
  }
}

export function makeProposals(): ProposalOut[] {
  return [
    { id: 1, type: 'status_change', application_id: 1, lead_id: 1, company: 'Freshworks', title: 'Senior Software Engineer - Java', payload: { to_status: 'Screening' }, evidence: 'Subject: "Next steps for your application" - "...would like to schedule a 30 min call with our recruiter..."', confidence: 0.93, state: 'pending', created_at: ago(1), email_url: 'https://mail.google.com/mail/u/0/#search/rfc822msgid:status%40mail', apply_url: null },
    { id: 2, type: 'inbound', application_id: null, lead_id: 8, company: 'TalentCorp Consulting', title: 'Keycloak / IAM Engineer', payload: { recruiter: 'Arun K', phone_shared: false }, evidence: 'Subject: "Keycloak opening - Bengaluru - immediate" - "...found your profile on Naukri..."', confidence: 0.88, state: 'pending', created_at: ago(2), email_url: 'https://mail.google.com/mail/u/0/#search/rfc822msgid:inbound%40mail', apply_url: null },
    { id: 3, type: 'ghosted', application_id: 9, lead_id: 9, company: 'Atlassian', title: 'Backend Engineer, Jira Cloud', payload: { to_status: 'Ghosted' }, evidence: 'No reply in 21 days since Applied', confidence: 1, state: 'pending', created_at: ago(5), email_url: null, apply_url: null },
  ]
}

export function makeOutreach(): OutreachOut[] {
  return [
    { id: 1, application_id: 3, lead_id: 3, company: 'Okta', title: 'Software Engineer II, Identity Platform', kind: 'referral', contact: 'Rahul S - Staff Engineer, Identity (linkedin.com/in/example)', draft: 'Hi Rahul, I saw the SE II Identity Platform opening at Okta. I have 3 years building Keycloak extensions in Java...', due_at: null, snoozed_until: null, sent_at: null, created_at: ago(20) },
    { id: 2, application_id: 1, lead_id: 1, company: 'Freshworks', title: 'Senior Software Engineer - Java', kind: 'follow_up', contact: 'careers@freshworks.example', draft: 'Hello, following up on my application for Senior Software Engineer - Java submitted last week...', due_at: ago(2), snoozed_until: null, sent_at: null, created_at: ago(30) },
  ]
}

export function makeRuns(): RunOut[] {
  return [
    { id: 3, kind: 'evaluate', state: 'running', lead_id: 4, params: {}, started_at: ago(0.05), finished_at: null, summary: null, error: null, created_at: ago(0.06) },
    { id: 2, kind: 'intake_boards', state: 'succeeded', lead_id: null, params: { sites: ['linkedin', 'naukri'] }, started_at: ago(1), finished_at: ago(0.9), summary: '184 fetched, 23 new, 141 duplicates, 20 dropped', error: null, created_at: ago(1) },
    { id: 1, kind: 'intake_gmail', state: 'failed', lead_id: null, params: {}, started_at: ago(2), finished_at: ago(2), summary: null, error: 'Gmail app password not set', created_at: ago(2) },
  ]
}

export function makeSources(): SourceOut[] {
  const names = ['linkedin', 'naukri', 'indeed', 'glassdoor', 'google', 'careerops_scan', 'remotive', 'himalayas', 'remoteok', 'gmail_alert', 'gmail_inbound']
  return names.map((source, i) => ({
    source,
    enabled: true,
    paused_until: source === 'glassdoor' ? ahead(5) : null,
    last_run_at: ago(1 + i * 0.1),
    last_ok_at: source === 'glassdoor' ? ago(26) : ago(1 + i * 0.1),
    last_error: source === 'glassdoor' ? '429 Too Many Requests (3 in a row, paused 6 h)' : null,
    consecutive_failures: source === 'glassdoor' ? 3 : 0,
    last_count: [48, 61, 22, 0, 35, 140, 6, 9, 4, 17, 2][i],
  }))
}

export function makeProfiles(): ProfileOut[] {
  return [
    { platform: 'naukri', edit_url: 'https://www.naukri.com/mnjuser/profile', last_refreshed_at: ago(30), refresh_every_days: 1, refresh_due: true, checklist: { headline: true, keywords: true, resume_a: true, notice_period: true, preferred_cities: false } },
    { platform: 'linkedin', edit_url: 'https://www.linkedin.com/in/me/', last_refreshed_at: ago(200), refresh_every_days: 7, refresh_due: false, checklist: { open_to_work_recruiters: true, headline: true } },
    { platform: 'instahyre', edit_url: 'https://www.instahyre.com/candidate/profile/', last_refreshed_at: null, refresh_every_days: null, refresh_due: false, checklist: { profile_complete: false } },
    { platform: 'hirist', edit_url: 'https://www.hirist.tech/', last_refreshed_at: null, refresh_every_days: null, refresh_due: false, checklist: { profile_complete: true } },
  ]
}

export const SETTINGS: Settings = {
  auto_evaluate_top_n: 10,
  claude_concurrency: 2,
  notifications: true,
  naukri_profile_bot: false,
  query_matrix: {
    titles: ['Java Developer', 'Backend Engineer', 'Software Engineer Java', 'SDE 2', 'Spring Boot Developer', 'Microservices Engineer', 'Platform Engineer', 'Identity IAM Engineer', 'Keycloak'],
    locations: ['Chennai', 'Bengaluru', 'Remote India'],
    sites: ['linkedin', 'naukri', 'indeed', 'glassdoor', 'google'],
    hours_old: 72,
    results_wanted: 50,
  },
  prefilter: {
    cities: ['Chennai', 'Bengaluru', 'Bangalore'],
    remote_ok: true,
    exp_years: [2, 4],
    exp_drop_min_at_least: 6,
    ctc_min_lpa: 10,
    usd_inr: 85,
    max_age_days_pass: 14,
    max_age_days_drop: 30,
    stack_positive: ['java', 'spring', 'spring boot', 'microservices', 'keycloak'],
    stack_negative: ['frontend only', 'php', 'sales'],
  },
  schedules: { boards_every_hours: 3, boards_window: [7, 23], careerops_scan_times: ['08:00', '17:00'], remote_boards_times: ['08:30', '17:30'], gmail_every_minutes: 30 },
  targets: { applied_per_week: 60, referrals_per_week: 15, min_eval_score: 3.5 },
  followups: { follow_up_business_days: 5, second_follow_up_business_days: 7, ghosted_after_days: 21, quiet_hours: [23, 7], gmail_lookback_days: 14, extra_holidays: [] },
  source_weights: { gmail_inbound: 1.5, careerops_scan: 1.15 },
  evaluator: {
    mode: 'lean', engines: ['codex', 'claude'], codex_model: 'gpt-6.2-sol', codex_effort: 'low',
    claude_model: 'sonnet', claude_effort: 'low', timeout_seconds: 180, jd_max_chars: 7000,
  },
  nightly: {
    enabled: true, time: '00:00', candidates: 40, max_age_hours: 72, min_quick_score: 0.35,
    max_exp_min: 3, per_company: 2,
    pick_min_eval: 3.5, picks_max: 20, picks_window_hours: 48,
  },
  reachout: {
    enabled: true, daily_cap: 25, cooldown_days: 14, max_jobs: 8, default_attach: 'tailored', look_up_web: true,
    guess_addresses: true, guess_prefixes: ['careers', 'hr', 'jobs', 'talent', 'recruitment'],
    subject_one: 'Application for {title} (Job ID {job_id}) - {name}', subject_many: 'Applying for {count} roles at {company} - {name}',
    body: '{greeting}\n\n{opening}\n{jobs}\n\nRegards,\n{signature}',
    me: { name: '', phone: '', linkedin: '', github: '', headline: '' },
  },
}

export function makeCompanies(): Company[] {
  return [
    { name: 'Freshworks', careers_url: 'https://careers.smartrecruiters.com/Freshworks', enabled: true, provider: 'smartrecruiters', notes: null },
    { name: 'Zoho', careers_url: 'https://www.zoho.com/careers/', enabled: true, provider: null, notes: 'ATS unresolved; websearch fallback' },
    { name: 'Chargebee', careers_url: 'https://www.chargebee.com/careers/', enabled: false, provider: null, notes: null },
    { name: 'Razorpay', careers_url: 'https://jobs.lever.co/razorpay', enabled: true, provider: 'lever', notes: null },
  ]
}

export const INSIGHTS: Insight[] = [
  { kind: 'best_source', text: 'Naukri: 3 calls from 12 applies (25%), best source in the last 30 days', severity: 'good', metric: 0.25 },
  { kind: 'weak_source', text: 'Glassdoor: 0 calls from 9 applies; consider fewer applies there', severity: 'warn', metric: 0 },
  { kind: 'variant', text: 'CV variant B: 2 calls from 6 applies (33%) vs A 2 from 15 (13%)', severity: 'info', metric: 0.33 },
  { kind: 'pace', text: '34 of 60 applies this week with 2 days left', severity: 'warn', metric: 34 },
]

export { ago, ahead, NOW }
