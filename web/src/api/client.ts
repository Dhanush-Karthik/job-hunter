// Typed API client (lead-owned). Types are generated from contracts/openapi.json: `npm run gen:api`.
import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

// Absolute origin: Request() rejects relative URLs outside a browser page (vitest/jsdom).
// fetch is late-bound so MSW (tests, dev:mock) can patch globalThis.fetch after import.
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? 'http://localhost',
  fetch: (req) => globalThis.fetch(req),
})

type S = components['schemas']
export type LeadSummary = S['LeadSummary']
export type LeadDetail = S['LeadDetail']
export type LeadPage = S['Page_LeadSummary_']
export type Evaluation = S['Evaluation']
export type ApplicationOut = S['ApplicationOut']
export type EventOut = S['EventOut']
export type ProposalOut = S['ProposalOut']
export type OutreachOut = S['OutreachOut']
export type RunOut = S['RunOut']
export type RunLog = S['RunLog']
export type TodaySummary = S['TodaySummary']
export type ActionItem = S['ActionItem']
export type ServiceHealth = S['ServiceHealth']
export type Funnel = S['Funnel']
export type Breakdown = S['Breakdown']
export type WeeklyPoint = S['WeeklyPoint']
export type ResponseTimes = S['ResponseTimes']
export type RejectAuditRow = S['RejectAuditRow']
export type Insight = S['Insight']
export type Company = S['Company']
export type CheckResult = S['CheckResult']
export type FollowupRules = S['FollowupRules']
export type SourceOut = S['SourceOut']
export type Settings = S['Settings']
export type SecretName = S['SecretName']
export type ProfileOut = S['ProfileOut']
export type SetupStatus = S['SetupStatus']
export type Health = S['Health']
export type AppStatus = S['AppStatus']
export type Source = S['Source']
export type ApplyChannel = S['ApplyChannel']

/** Unwraps an openapi-fetch result: returns data or throws with the server's detail. */
export function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.error !== undefined || r.data === undefined) {
    const detail =
      typeof r.error === 'object' && r.error && 'detail' in r.error ? String((r.error as { detail: unknown }).detail) : ''
    throw new Error(`${r.response.status} ${detail || r.response.statusText}`)
  }
  return r.data
}

/** Status order for kanban columns and funnel. */
export const PIPELINE: AppStatus[] = ['Shortlisted', 'Ready', 'Applied', 'Screening', 'Technical', 'Final', 'Offer']
export const CLOSED: AppStatus[] = ['Accepted', 'Declined', 'Rejected', 'Ghosted', 'Withdrawn', 'Skipped', 'Expired']

/** Mirrors models.TRANSITIONS; the server is authoritative (409 on a bad move). */
export const TRANSITIONS: Record<AppStatus, AppStatus[]> = {
  New: ['Shortlisted', 'Skipped', 'Expired'],
  Shortlisted: ['Ready', 'Skipped'],
  Ready: ['Applied'],
  Applied: ['Screening', 'Rejected', 'Ghosted', 'Withdrawn'],
  Screening: ['Technical', 'Rejected', 'Withdrawn'],
  Technical: ['Final', 'Rejected', 'Withdrawn'],
  Final: ['Offer', 'Rejected'],
  Offer: ['Accepted', 'Declined'],
  Ghosted: ['Screening'],
  Accepted: [],
  Declined: [],
  Rejected: [],
  Withdrawn: [],
  Skipped: [],
  Expired: [],
}
