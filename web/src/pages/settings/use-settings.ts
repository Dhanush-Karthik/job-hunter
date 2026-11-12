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

/** For 204 responses, which have no body for unwrap to return. */
function assertOk(r: { error?: unknown; response: Response }) {
  if (r.error !== undefined) unwrap({ error: r.error, response: r.response })
}

// ---- setup wizard

export const useSetup = () => useQuery({ queryKey: ['setup'], queryFn: async () => unwrap(await api.GET('/api/setup')) })

/** Which secrets exist. The values are write-only: the API never returns them. */
export const useSecrets = () => useQuery({ queryKey: ['secrets'], queryFn: async () => unwrap(await api.GET('/api/secrets')) })

export function useSaveGmailSecrets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { gmail_address?: string; gmail_app_password?: string }) => {
      for (const [name, value] of Object.entries(v)) {
        if (value) assertOk(await api.PUT('/api/secrets/{name}', { params: { path: { name } }, body: { value } }))
      }
    },
    onSuccess: () => {
      toast.success('Saved to the macOS Keychain')
      return Promise.all([qc.invalidateQueries({ queryKey: ['secrets'] }), qc.invalidateQueries({ queryKey: ['setup'] }), qc.invalidateQueries({ queryKey: ['today'] })])
    },
  })
}

export const useTestGmail = () => useMutation({ mutationFn: async () => unwrap(await api.POST('/api/setup/gmail-test')) })

export function useUploadCv() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ variant, markdown }: { variant: 'A' | 'B'; markdown: string }) => unwrap(await api.PUT('/api/setup/cv', { body: { variant, markdown } })),
    onSuccess: (_, v) => {
      toast.success(`CV variant ${v.variant} saved`)
      return qc.invalidateQueries({ queryKey: ['setup'] })
    },
  })
}

// ---- companies

export const useCompanies = () => useQuery({ queryKey: ['companies'], queryFn: async () => unwrap(await api.GET('/api/companies')) })

export function useCompanyActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['companies'] })
  const add = useMutation({
    mutationFn: async (body: { name: string; careers_url: string }) => unwrap(await api.POST('/api/companies', { body })),
    onSuccess: (c) => {
      toast.success(`${c.name} added`)
      return refresh()
    },
  })
  const toggle = useMutation({
    mutationFn: async ({ name, enabled }: { name: string; enabled: boolean }) =>
      unwrap(await api.PATCH('/api/companies/{name}', { params: { path: { name } }, body: { enabled } })),
    onSuccess: (c) => {
      toast.success(`${c.name} ${c.enabled ? 'enabled' : 'disabled'}`)
      return refresh()
    },
  })
  const remove = useMutation({
    mutationFn: async (name: string) => {
      assertOk(await api.DELETE('/api/companies/{name}', { params: { path: { name } } }))
    },
    onSuccess: (_, name) => {
      toast.success(`${name} removed`)
      return refresh()
    },
  })
  return { add, toggle, remove, busy: add.isPending || toggle.isPending || remove.isPending }
}

// ---- run logs

export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: async () => unwrap(await api.GET('/api/runs')), refetchInterval: 15_000 })

export const useRunLog = (id: number | null) =>
  useQuery({
    queryKey: ['runs', id, 'log'],
    enabled: id != null,
    queryFn: async () => unwrap(await api.GET('/api/runs/{run_id}/log', { params: { path: { run_id: id! } } })),
  })

export function useCancelRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (run_id: number) => unwrap(await api.POST('/api/runs/{run_id}/cancel', { params: { path: { run_id } } })),
    onSuccess: () => {
      toast.success('Run cancelled')
      return qc.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}
