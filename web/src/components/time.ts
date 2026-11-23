// Human time phrases ("3 days ago", "overdue by 2 days") so lists read at a glance.

const DAY = 86_400_000

/** Whole calendar days from `now` until `iso` (negative when `iso` is in the past). */
export function dayDiff(iso: string, now: Date = new Date()): number {
  const a = new Date(iso)
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  return Math.round((start(a) - start(now)) / DAY)
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`

/** "today", "yesterday", "3 days ago", "in 2 days". */
export function relativeDay(iso: string, now: Date = new Date()): string {
  const d = dayDiff(iso, now)
  if (d === 0) return 'today'
  if (d === -1) return 'yesterday'
  if (d === 1) return 'tomorrow'
  return d < 0 ? `${plural(-d, 'day')} ago` : `in ${plural(d, 'day')}`
}

/** Due-date phrase plus whether it is overdue. */
export function dueLabel(iso: string, now: Date = new Date()): { text: string; overdue: boolean } {
  const d = dayDiff(iso, now)
  if (d < 0) return { text: `Overdue by ${plural(-d, 'day')}`, overdue: true }
  if (d === 0) return { text: 'Due today', overdue: false }
  return { text: `Due ${relativeDay(iso, now)}`, overdue: false }
}

export const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
