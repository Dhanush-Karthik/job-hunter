import type { ApplyChannel, LeadSummary, Source } from '@/api/client'

export const SOURCE_LABEL: Record<Source, string> = {
  linkedin: 'LinkedIn',
  naukri: 'Naukri',
  indeed: 'Indeed',
  glassdoor: 'Glassdoor',
  google: 'Google Jobs',
  careerops_scan: 'Career pages',
  remotive: 'Remotive',
  weworkremotely: 'We Work Remotely',
  yc: 'YC',
  himalayas: 'Himalayas',
  remoteok: 'RemoteOK',
  gmail_alert: 'Email alert',
  gmail_inbound: 'Inbound recruiter',
  manual: 'Manual',
}

export const CHANNEL_LABEL: Record<ApplyChannel, string> = {
  platform_quick: 'Quick apply',
  company_ats: 'Company ATS',
  email: 'Email',
  unknown: 'Unknown',
}

const range = (min: number | null | undefined, max: number | null | undefined, unit: string) => {
  if (min != null && max != null) return min === max ? `${min} ${unit}` : `${min}–${max} ${unit}`
  if (min != null) return `${min}+ ${unit}`
  if (max != null) return `up to ${max} ${unit}`
  return null
}

export const formatExp = (l: Pick<LeadSummary, 'exp_min' | 'exp_max'>) => range(l.exp_min, l.exp_max, 'yrs')
/** CTC is in LPA; null means the post hides it. */
export const formatCtc = (l: Pick<LeadSummary, 'ctc_min' | 'ctc_max'>) => range(l.ctc_min, l.ctc_max, 'LPA')

export function formatPlace(l: Pick<LeadSummary, 'location' | 'work_mode'>) {
  const mode = l.work_mode === 'unknown' ? null : l.work_mode
  return [l.location, mode].filter(Boolean).join(' · ') || '—'
}

export const quickScorePct = (l: Pick<LeadSummary, 'quick_score'>) => Math.round(l.quick_score * 100)

/** Dropped by the prefilter and not restored by the owner. */
export const isRejected = (l: Pick<LeadSummary, 'prefilter_pass' | 'restored'>) => !l.prefilter_pass && !l.restored
