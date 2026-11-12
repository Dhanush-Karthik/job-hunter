import type { Funnel } from '@/api/client'

export const pct = (r: number | null | undefined) => (r == null ? '—' : `${Math.round(r * 1000) / 10}%`)

/** Interview calls = anything that reached Screening (plan section 6). */
export const callsOf = (f: Funnel | undefined) => f?.stages.find((s) => s.status === 'Screening')?.count
