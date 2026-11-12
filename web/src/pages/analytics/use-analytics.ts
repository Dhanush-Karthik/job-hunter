import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type Breakdown } from '@/api/client'

export type Range = '7' | '30' | '90' | 'all'
export const RANGES: { value: Range; label: string }[] = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: 'all', label: 'All time' },
]

const isoDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
/** Query params for a range; "all" sends none so the server returns everything. */
export function rangeQuery(range: Range): { date_from?: string } {
  if (range === 'all') return {}
  const from = new Date()
  from.setDate(from.getDate() - Number(range))
  return { date_from: isoDate(from) }
}

export const useFunnel = (range: Range) =>
  useQuery({ queryKey: ['analytics', 'funnel', range], queryFn: async () => unwrap(await api.GET('/api/analytics/funnel', { params: { query: rangeQuery(range) } })) })

export const useBreakdown = (by: Breakdown['by'], range: Range) =>
  useQuery({
    queryKey: ['analytics', 'breakdown', by, range],
    queryFn: async () => unwrap(await api.GET('/api/analytics/breakdown', { params: { query: { by, ...rangeQuery(range) } } })),
  })

export const useWeekly = () => useQuery({ queryKey: ['analytics', 'weekly'], queryFn: async () => unwrap(await api.GET('/api/analytics/weekly')) })

export const useResponseTimes = () =>
  useQuery({ queryKey: ['analytics', 'response-times'], queryFn: async () => unwrap(await api.GET('/api/analytics/response-times')) })

export const useInsights = (range: Range) =>
  useQuery({
    queryKey: ['analytics', 'insights', range],
    queryFn: async () => unwrap(await api.GET('/api/analytics/insights', { params: { query: range === 'all' ? {} : { days: Number(range) } } })),
  })

export const useRejects = (range: Range) =>
  useQuery({ queryKey: ['analytics', 'rejects', range], queryFn: async () => unwrap(await api.GET('/api/analytics/rejects', { params: { query: rangeQuery(range) } })) })

/** Brings a prefilter-dropped lead back into the Leads list. */
export function useRestoreLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (lead_id: number) => unwrap(await api.POST('/api/leads/{lead_id}/restore', { params: { path: { lead_id } } })),
    onSuccess: () => {
      toast.success('Restored to Leads')
      return Promise.all(['analytics', 'leads', 'today'].map((k) => qc.invalidateQueries({ queryKey: [k] })))
    },
  })
}
