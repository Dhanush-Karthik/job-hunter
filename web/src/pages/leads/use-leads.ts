import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, unwrap, type AppStatus, type ApplyChannel, type Source } from '@/api/client'
import type { operations } from '@/api/schema'

type Query = NonNullable<operations['listLeads']['parameters']['query']>
export type Sort = NonNullable<Query['sort']>

export const SORTS: { value: Sort; label: string }[] = [
  { value: 'score', label: 'Best match' },
  { value: 'eval_score', label: 'AI fit score' },
  { value: 'posted_at', label: 'Newest posted' },
  { value: 'found_at', label: 'Newest found' },
]
export const STATUSES: AppStatus[] = [
  'New', 'Shortlisted', 'Ready', 'Applied', 'Screening', 'Technical', 'Final', 'Offer',
  'Accepted', 'Declined', 'Rejected', 'Ghosted', 'Withdrawn', 'Skipped', 'Expired',
]
export const SOURCES: Source[] = [
  'linkedin', 'naukri', 'indeed', 'glassdoor', 'google', 'careerops_scan', 'remotive', 'weworkremotely',
  'yc', 'himalayas', 'remoteok', 'gmail_alert', 'gmail_inbound', 'manual',
]
export const CHANNELS: ApplyChannel[] = ['platform_quick', 'company_ats', 'email', 'unknown']
/** quick_score is 0..1 on the wire; the UI shows it as 0..100. */
export const MIN_SCORES = [0.5, 0.6, 0.7, 0.8, 0.9]
export const DEFAULT_LIMIT = 50
export const PAGE_SIZES = [25, 50, 100]

/** Jobs page tabs: new matches to triage, shortlisted ones to apply to, everything. */
export type LeadsTab = 'review' | 'apply' | 'all'
export const TAB_STATUS: Record<LeadsTab, AppStatus[] | null> = { review: ['New'], apply: ['Shortlisted', 'Ready'], all: null }

export type Filters = {
  tab: LeadsTab
  q: string
  status: AppStatus[]
  source: Source[]
  channel: ApplyChannel[]
  min_score: number | null
  fresh_only: boolean
  inbound_only: boolean
  include_rejected: boolean
  sort: Sort
  limit: number
  offset: number
}

const only = <T extends string>(values: string[], allowed: readonly T[]) => values.filter((v): v is T => (allowed as readonly string[]).includes(v))

export function parseFilters(sp: URLSearchParams): Filters {
  const min = Number(sp.get('min_score'))
  const sort = sp.get('sort')
  const limit = Number(sp.get('limit'))
  const offset = Number(sp.get('offset'))
  const tab = sp.get('tab')
  return {
    tab: tab === 'apply' || tab === 'all' ? tab : 'review',
    q: sp.get('q') ?? '',
    status: only(sp.getAll('status'), STATUSES),
    source: only(sp.getAll('source'), SOURCES),
    channel: only(sp.getAll('channel'), CHANNELS),
    min_score: sp.get('min_score') && Number.isFinite(min) ? min : null,
    fresh_only: sp.get('fresh_only') === 'true',
    inbound_only: sp.get('inbound_only') === 'true',
    include_rejected: sp.get('include_rejected') === 'true',
    sort: SORTS.some((s) => s.value === sort) ? (sort as Sort) : 'score',
    limit: limit > 0 ? limit : DEFAULT_LIMIT,
    offset: offset > 0 ? offset : 0,
  }
}

export function toQuery(f: Filters): Query {
  return {
    q: f.q || undefined,
    // The review/apply tabs pin the status; the All tab lets the owner pick one.
    status: TAB_STATUS[f.tab] ?? (f.status.length ? f.status : undefined),
    source: f.source.length ? f.source : undefined,
    channel: f.channel.length ? f.channel : undefined,
    min_score: f.min_score ?? undefined,
    fresh_only: f.fresh_only || undefined,
    inbound_only: f.inbound_only || undefined,
    include_rejected: (f.tab === 'all' && f.include_rejected) || undefined,
    sort: f.sort,
    limit: f.limit,
    offset: f.offset,
  }
}

export function useLeads(filters: Filters) {
  const query = toQuery(filters)
  return useQuery({
    queryKey: ['leads', 'list', query],
    queryFn: async () => unwrap(await api.GET('/api/leads', { params: { query } })),
    placeholderData: keepPreviousData,
  })
}

/** Total per tab for the tab labels (one tiny request each). */
export function useTabCount(tab: LeadsTab) {
  return useQuery({
    queryKey: ['leads', 'count', tab],
    queryFn: async () => unwrap(await api.GET('/api/leads', { params: { query: { status: TAB_STATUS[tab] ?? undefined, limit: 1 } } })).total,
  })
}
