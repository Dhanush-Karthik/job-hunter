import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'

export type OutreachTab = 'due' | 'referrals' | 'sent'

const QUERY: Record<OutreachTab, { kind?: 'follow_up' | 'referral'; due_only?: boolean; sent?: boolean }> = {
  due: { kind: 'follow_up', due_only: true },
  referrals: { kind: 'referral', sent: false },
  sent: { sent: true },
}

export const useOutreach = (tab: OutreachTab) =>
  useQuery({
    queryKey: ['outreach', tab],
    queryFn: async () => unwrap(await api.GET('/api/outreach', { params: { query: QUERY[tab] } })),
  })

const path = (outreach_id: number) => ({ params: { path: { outreach_id } } })

/** Edit, mark sent, snooze. Nothing here sends a message; "sent" only records that the owner did. */
export function useOutreachActions() {
  const qc = useQueryClient()
  const invalidate = useCallback(
    () => Promise.all(['outreach', 'nav', 'today', 'job'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
    [qc],
  )
  const edit = useMutation({
    mutationFn: async ({ id, draft, contact }: { id: number; draft: string; contact: string }) =>
      unwrap(await api.PATCH('/api/outreach/{outreach_id}', { ...path(id), body: { draft, contact: contact || null } })),
    onSuccess: () => {
      toast.success('Draft saved')
      return invalidate()
    },
  })
  const markSent = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/outreach/{outreach_id}/mark-sent', path(id))),
    onSuccess: () => {
      toast.success('Marked sent')
      return invalidate()
    },
  })
  const snooze = useMutation({
    mutationFn: async ({ id, days }: { id: number; days: number }) =>
      unwrap(await api.POST('/api/outreach/{outreach_id}/snooze', { ...path(id), body: { days } })),
    onSuccess: (_, v) => {
      toast.success(`Snoozed ${v.days} day${v.days === 1 ? '' : 's'}`)
      return invalidate()
    },
  })
  const busy = edit.isPending || markSent.isPending || snooze.isPending
  return { edit, markSent, snooze, busy }
}
