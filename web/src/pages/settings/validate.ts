import type { FollowupRules, Settings } from '@/api/client'

type P = Settings['prefilter']
type S = Settings['schedules']

export const inRange = (n: number, min: number, max: number, integer = false) =>
  Number.isFinite(n) && n >= min && n <= max && (!integer || Number.isInteger(n))

export const validTime = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t)
export const validDate = (d: string) => /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(d) && !Number.isNaN(Date.parse(d))

export const prefilterValid = (p: P) =>
  p.cities.length > 0 &&
  inRange(p.exp_years[0], 0, 40) &&
  inRange(p.exp_years[1], 0, 40) &&
  p.exp_years[0] <= p.exp_years[1] &&
  inRange(p.exp_drop_min_at_least, 0, 40) &&
  inRange(p.ctc_min_lpa, 0, 500) &&
  inRange(p.usd_inr, 1, 500) &&
  inRange(p.max_age_days_pass, 1, 365, true) &&
  inRange(p.max_age_days_drop, 1, 365, true) &&
  p.max_age_days_pass <= p.max_age_days_drop

export const schedulesValid = (s: S) =>
  inRange(s.boards_every_hours, 1, 24, true) &&
  inRange(s.boards_window[0], 0, 23, true) &&
  inRange(s.boards_window[1], 1, 24, true) &&
  s.boards_window[0] < s.boards_window[1] &&
  inRange(s.gmail_every_minutes, 5, 240, true) &&
  s.careerops_scan_times.every(validTime) &&
  s.remote_boards_times.every(validTime)

export const followupsValid = (f: FollowupRules) =>
  inRange(f.follow_up_business_days, 1, 20, true) &&
  inRange(f.second_follow_up_business_days, 1, 30, true) &&
  inRange(f.ghosted_after_days, 7, 90, true) &&
  inRange(f.quiet_hours[0], 0, 23, true) &&
  inRange(f.quiet_hours[1], 0, 23, true) &&
  inRange(f.gmail_lookback_days, 1, 90, true) &&
  f.extra_holidays.every(validDate)

