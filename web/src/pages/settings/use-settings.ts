import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type Settings } from '@/api/client'

// openapi-fetch widens the schema's [number, number] tuples to number[] in response data; the wire shape is the schema's.
export const useSettings = () =>
  useQuery({ queryKey: ['settings'], queryFn: async () => unwrap(await api.GET('/api/settings')) as Settings })

export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: Settings) => unwrap(await api.PUT('/api/settings', { body })),
    onSuccess: (saved) => {
      qc.setQueryData(['settings'], saved)
      toast.success('Settings saved')
      return Promise.all([qc.invalidateQueries({ queryKey: ['settings'] }), qc.invalidateQueries({ queryKey: ['today'] })])
    },
  })
}

export const useSources = () => useQuery({ queryKey: ['sources'], queryFn: async () => unwrap(await api.GET('/api/sources')) })

export function usePatchSource() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ source, enabled, unpause }: { source: string; enabled?: boolean; unpause?: boolean }) =>
      unwrap(await api.PATCH('/api/sources/{source}', { params: { path: { source } }, body: { enabled: enabled ?? null, unpause: unpause ?? null } })),
    onSuccess: (s, v) => {
      toast.success(v.unpause ? `${s.source} unpaused` : `${s.source} ${s.enabled ? 'enabled' : 'disabled'}`)
      return Promise.all([qc.invalidateQueries({ queryKey: ['sources'] }), qc.invalidateQueries({ queryKey: ['today'] })])
    },
  })
}

export const useProfiles = () => useQuery({ queryKey: ['profiles'], queryFn: async () => unwrap(await api.GET('/api/profiles')) })

export function usePatchProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ platform, checklist, refreshed_now }: { platform: string; checklist?: Record<string, boolean>; refreshed_now?: boolean }) =>
      unwrap(await api.PATCH('/api/profiles/{platform}', { params: { path: { platform } }, body: { checklist: checklist ?? null, refreshed_now: refreshed_now ?? null } })),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['profiles'] }), qc.invalidateQueries({ queryKey: ['today'] })]),
  })
}
