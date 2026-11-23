import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'

export type NavCounts = { proposals: number; followUps: number; toApply: number; problems: number }

/** Sidebar badges: inbox items to confirm, follow-ups due, jobs waiting to be applied to, services that are down. */
export function useNavCounts(): NavCounts {
  const proposals = useQuery({
    queryKey: ['nav', 'proposals'],
    queryFn: async () => unwrap(await api.GET('/api/proposals', { params: { query: { state: 'pending' } } })).length,
  })
  const followUps = useQuery({
    queryKey: ['nav', 'follow-ups'],
    queryFn: async () => unwrap(await api.GET('/api/outreach', { params: { query: { due_only: true } } })).length,
  })
  const toApply = useQuery({
    queryKey: ['nav', 'to-apply'],
    queryFn: async () => unwrap(await api.GET('/api/leads', { params: { query: { status: ['Shortlisted', 'Ready'], limit: 1 } } })).total,
  })
  // Shares the Home page's cache entry, so it costs nothing extra there.
  const today = useQuery({ queryKey: ['today'], queryFn: async () => unwrap(await api.GET('/api/today')) })
  return {
    proposals: proposals.data ?? 0,
    followUps: followUps.data ?? 0,
    toApply: toApply.data ?? 0,
    problems: today.data?.health.filter((h) => !h.ok).length ?? 0,
  }
}
