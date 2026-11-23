import type { RejectAuditRow } from '@/api/client'

/**
 * The server reports one reason per exact value ("stale: 44 days", "stale: 45 days"...). Group those into the rule
 * that fired so the list reads as a handful of rules, not hundreds of numbers.
 */
export function reasonGroup(reason: string): string {
  if (/^stale\b/i.test(reason)) return 'Too old (posted long ago)'
  if (/^ctc:/i.test(reason)) return 'Salary below your minimum'
  if (/^experience: min /i.test(reason)) return 'Asks for too many years of experience'
  if (/^location: (?!remote)/i.test(reason)) return 'Location: a city you did not pick'
  return reason.charAt(0).toUpperCase() + reason.slice(1)
}

export function groupReasons(rows: RejectAuditRow[]): RejectAuditRow[] {
  const by = new Map<string, RejectAuditRow>()
  for (const r of rows) {
    const key = reasonGroup(r.reason)
    const g = by.get(key) ?? { reason: key, count: 0, sample_lead_ids: [] }
    g.count += r.count
    g.sample_lead_ids = [...g.sample_lead_ids, ...r.sample_lead_ids].slice(0, 5)
    by.set(key, g)
  }
  return [...by.values()].sort((a, b) => b.count - a.count)
}
