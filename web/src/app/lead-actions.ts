// Shared lead mutations for Today, Leads and Quick-apply. Every success invalidates the lists that show leads.
import { useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type BulkBody = components['schemas']['BulkAction']
type BulkActionName = BulkBody['action']

const DONE: Record<BulkActionName, string> = {
  shortlist: 'Shortlisted',
  skip: 'Skipped',
  evaluate: 'Evaluation queued for',
  verify: 'Live check queued for',
  restore: 'Restored',
}

export function useInvalidateWork() {
  const qc = useQueryClient()
  return useCallback(
    () => Promise.all(['leads', 'today', 'nav'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
    [qc],
  )
}

const path = (lead_id: number) => ({ params: { path: { lead_id } } })

export function useLeadActions() {
  const invalidate = useInvalidateWork()

  const shortlist = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/leads/{lead_id}/shortlist', path(id))),
    onSuccess: () => {
      toast.success('Shortlisted')
      return invalidate()
    },
  })
  const skip = useMutation({
    mutationFn: async ({ id, reason }: { id: number; reason: string }) =>
      unwrap(await api.POST('/api/leads/{lead_id}/skip', { ...path(id), body: { reason } })),
    onSuccess: () => {
      toast.success('Skipped')
      return invalidate()
    },
  })
  const evaluate = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/leads/{lead_id}/evaluate', path(id))),
    onSuccess: () => {
      toast.success('Evaluation queued')
      return invalidate()
    },
  })
  const restore = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/leads/{lead_id}/restore', path(id))),
    onSuccess: () => {
      toast.success('Restored')
      return invalidate()
    },
  })
  const bulk = useMutation({
    mutationFn: async (body: BulkBody) => ({ body, result: unwrap(await api.POST('/api/leads/bulk', { body })) }),
    onSuccess: ({ body, result }) => {
      if (result.ok.length) toast.success(`${DONE[body.action]} ${result.ok.length} lead${result.ok.length === 1 ? '' : 's'}`)
      const failed = Object.entries(result.failed ?? {})
      if (failed.length) toast.error(`${failed.length} failed: ${failed.map(([id, why]) => `#${id} ${why}`).join(', ')}`)
      return invalidate()
    },
  })
  const markApplied = useMutation({
    mutationFn: async (app_id: number) =>
      unwrap(await api.POST('/api/applications/{app_id}/transition', { params: { path: { app_id } }, body: { to_status: 'Applied' } })),
    onSuccess: () => {
      toast.success('Marked applied')
      return invalidate()
    },
  })

  const busy = [shortlist, skip, evaluate, restore, bulk, markApplied].some((m) => m.isPending)
  return { shortlist, skip, evaluate, restore, bulk, markApplied, busy }
}

export function useRunIntake() {
  const invalidate = useInvalidateWork()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/intake/run', { body: {} })),
    onSuccess: (runs) => {
      toast.success(`Intake started: ${runs.length} run${runs.length === 1 ? '' : 's'} (${runs.map((r) => r.kind.replace('intake_', '')).join(', ')})`)
      return invalidate()
    },
  })
}
