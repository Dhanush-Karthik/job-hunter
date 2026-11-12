import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'

/** Pending counts shown on the sidebar: proposals to confirm, follow-ups due. */
export function useNavCounts() {
  const proposals = useQuery({
    queryKey: ['nav', 'proposals'],
    queryFn: async () => unwrap(await api.GET('/api/proposals', { params: { query: { state: 'pending' } } })).length,
  })
  const followUps = useQuery({
    queryKey: ['nav', 'follow-ups'],
    queryFn: async () => unwrap(await api.GET('/api/outreach', { params: { query: { due_only: true } } })).length,
  })
  return { proposals: proposals.data ?? 0, followUps: followUps.data ?? 0 }
}
