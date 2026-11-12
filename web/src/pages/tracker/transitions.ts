import { TRANSITIONS, type AppStatus } from '@/api/client'

/** Closed column, in display order. */
export const CLOSED_COLUMN: AppStatus[] = ['Rejected', 'Ghosted', 'Withdrawn', 'Declined', 'Accepted', 'Skipped', 'Expired']

/** Stages a rejection can happen at (the statuses TRANSITIONS lets move to Rejected). */
export const REJECT_STAGES = (Object.keys(TRANSITIONS) as AppStatus[]).filter((s) => TRANSITIONS[s].includes('Rejected'))

/**
 * Moves the board offers. models.TRANSITIONS plus the API's main-line walk: Applied is accepted from Shortlisted too
 * (the server adds the Ready step). The server stays authoritative and answers 409 to anything else.
 */
export function allowedTargets(status: AppStatus): AppStatus[] {
  const base = TRANSITIONS[status]
  return status === 'Shortlisted' ? [...base, 'Applied'] : base
}
