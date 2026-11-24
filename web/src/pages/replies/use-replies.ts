import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type ApplicationOut, type AppStatus } from '@/api/client'
import { useInvalidateWork } from '@/app/lead-actions'

const path = (proposal_id: number) => ({ params: { path: { proposal_id } } })

export const usePendingProposals = () =>
  useQuery({
    queryKey: ['replies', 'pending'],
    queryFn: async () => unwrap(await api.GET('/api/proposals', { params: { query: { state: 'pending' } } })),
  })

/** Accept (optionally with an edited payload), dismiss, convert, set status. All refresh the list, nav badge, tracker and Home. */
export function useProposalActions() {
  const invalidate = useInvalidateWork()
  const accept = useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload?: Record<string, unknown> }) =>
      unwrap(await api.POST('/api/proposals/{proposal_id}/accept', { ...path(id), body: { payload: payload ?? null } })),
    onSuccess: () => {
      toast.success('Done')
      return invalidate()
    },
  })
  const dismiss = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/proposals/{proposal_id}/dismiss', path(id))),
    onSuccess: () => {
      toast.success('Ignored')
      return invalidate()
    },
  })
  const convert = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/proposals/{proposal_id}/convert', path(id))),
    onSuccess: () => {
      toast.success('Added to your jobs (shortlisted)')
      return invalidate()
    },
  })
  // "Dismiss all" on a group: one call per email, then one refresh.
  const dismissMany = useMutation({
    mutationFn: async (ids: number[]) => Promise.all(ids.map(async (id) => unwrap(await api.POST('/api/proposals/{proposal_id}/dismiss', path(id))))),
    onSuccess: (done) => {
      toast.success(`Dismissed ${done.length}`)
      return invalidate()
    },
  })
  // needs_eyes: the server only acknowledges these on accept, so move the application first, then close the proposal.
  const setStatus = useMutation({
    mutationFn: async ({ id, app, to }: { id: number; app: ApplicationOut; to: AppStatus }) => {
      unwrap(
        await api.POST('/api/applications/{app_id}/transition', {
          params: { path: { app_id: app.id } },
          body: { to_status: to, rejected_at_stage: to === 'Rejected' ? app.status : null },
        }),
      )
      return unwrap(await api.POST('/api/proposals/{proposal_id}/accept', { ...path(id), body: { payload: null } }))
    },
    onSuccess: (_, v) => {
      toast.success(`${v.app.company}: moved to ${v.to}`)
      return invalidate()
    },
  })
  const busy = accept.isPending || dismiss.isPending || dismissMany.isPending || convert.isPending || setStatus.isPending
  return { accept, dismiss, dismissMany, convert, setStatus, busy }
}
