import { useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type RunOut } from '@/api/client'
import { useInvalidateWork } from '@/app/lead-actions'
import type { components } from '@/api/schema'

export type ApplicationPatch = components['schemas']['ApplicationPatch']
export type Variant = components['schemas']['ResumeVariant']

/** Run polling interval; an object so tests can shorten it. */
export const polling = { ms: 2000 }
export const isActive = (r: Pick<RunOut, 'state'>) => r.state === 'queued' || r.state === 'running'

export const RUN_LABEL: Record<RunOut['kind'], string> = {
  intake_boards: 'Board intake',
  intake_remote: 'Remote boards',
  intake_gmail: 'Gmail intake',
  careerops_scan: 'Career-page scan',
  evaluate: 'Evaluate',
  verify: 'Verify',
  cv: 'CV',
  assist_apply: 'Assist apply',
  contacts: 'Find contacts',
  followups: 'Follow-ups',
}

const path = (lead_id: number) => ({ params: { path: { lead_id } } })

export function useJob(id: number) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: async () => unwrap(await api.GET('/api/leads/{lead_id}', path(id))),
    enabled: id > 0,
  })
}

/**
 * Runs for this lead, newest first. Polls every 2 s while one is queued/running, and refreshes the job detail
 * (report, CV, contacts) once a run settles so the result shows up without a reload.
 */
export function useLeadRuns(id: number) {
  const invalidate = useInvalidateWork()
  const query = useQuery({
    queryKey: ['job', id, 'runs'],
    queryFn: async () => unwrap(await api.GET('/api/runs', { params: { query: { lead_id: id, limit: 10 } } })),
    enabled: id > 0,
    refetchInterval: (q) => (q.state.data?.some(isActive) ? polling.ms : false),
  })
  const seen = useRef(new Map<number, RunOut['state']>())
  useEffect(() => {
    let settled = false
    for (const r of query.data ?? []) {
      const prev = seen.current.get(r.id)
      if (prev && (prev === 'queued' || prev === 'running') && !isActive(r)) settled = true
      seen.current.set(r.id, r.state)
    }
    if (settled) void invalidate()
  }, [query.data, invalidate])
  return query
}

export function useRunLog(runId: number, live: boolean, enabled: boolean) {
  return useQuery({
    queryKey: ['run-log', runId],
    queryFn: async () => unwrap(await api.GET('/api/runs/{run_id}/log', { params: { path: { run_id: runId } } })),
    enabled,
    refetchInterval: live ? polling.ms : false,
  })
}

/** Mutations on the job page. Run-starting ones refetch the run list so the progress panel appears at once. */
export function useJobMutations(leadId: number, appId: number | null | undefined) {
  const invalidate = useInvalidateWork()
  const started = (what: string) => (run: RunOut) => {
    toast.success(`${what} queued (run #${run.id})`)
    return invalidate()
  }
  const verify = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/leads/{lead_id}/verify', path(leadId))),
    onSuccess: started('Live check'),
  })
  const cv = useMutation({
    mutationFn: async (variant: Variant) => unwrap(await api.POST('/api/leads/{lead_id}/cv', { ...path(leadId), body: { variant } })),
    onSuccess: (run, variant) => started(`CV ${variant}`)(run),
  })
  const assist = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/leads/{lead_id}/assist-apply', path(leadId))),
    onSuccess: started('Assist apply'),
  })
  const contacts = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/leads/{lead_id}/contacts', path(leadId))),
    onSuccess: started('Contact search'),
  })
  const patch = useMutation({
    mutationFn: async (body: ApplicationPatch) => {
      if (appId == null) throw new Error('No application yet. Shortlist the lead first.')
      return unwrap(await api.PATCH('/api/applications/{app_id}', { params: { path: { app_id: appId } }, body }))
    },
    onSuccess: () => invalidate(),
  })
  return { verify, cv, assist, contacts, patch }
}
