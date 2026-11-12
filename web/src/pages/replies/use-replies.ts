import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useInvalidateWork } from '@/app/lead-actions'

const path = (proposal_id: number) => ({ params: { path: { proposal_id } } })

export const usePendingProposals = () =>
  useQuery({
    queryKey: ['replies', 'pending'],
    queryFn: async () => unwrap(await api.GET('/api/proposals', { params: { query: { state: 'pending' } } })),
  })

/** Accept (optionally with an edited payload), dismiss, convert. All refresh the list, nav badge, tracker and Today. */
export function useProposalActions() {
  const invalidate = useInvalidateWork()
  const accept = useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload?: Record<string, unknown> }) =>
      unwrap(await api.POST('/api/proposals/{proposal_id}/accept', { ...path(id), body: { payload: payload ?? null } })),
    onSuccess: () => {
      toast.success('Accepted')
      return invalidate()
    },
  })
  const dismiss = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/proposals/{proposal_id}/dismiss', path(id))),
    onSuccess: () => {
      toast.success('Dismissed')
      return invalidate()
    },
  })
  const convert = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST('/api/proposals/{proposal_id}/convert', path(id))),
    onSuccess: () => {
      toast.success('Converted to an application')
      return invalidate()
    },
  })
  const busy = accept.isPending || dismiss.isPending || convert.isPending
  return { accept, dismiss, convert, busy }
}
