import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type ApplicationOut, type AppStatus } from '@/api/client'
import { useInvalidateWork } from '@/app/lead-actions'

const KEY = ['tracker', 'apps'] as const

export const useApplications = () =>
  useQuery({ queryKey: KEY, queryFn: async () => unwrap(await api.GET('/api/applications')) })

export type Move = { app: ApplicationOut; to: AppStatus; rejected_at_stage?: AppStatus }

/** Optimistic move: the card jumps at once and snaps back if the server refuses (409). The global handler toasts the detail. */
export function useMoveApplication() {
  const qc = useQueryClient()
  const invalidate = useInvalidateWork()
  return useMutation({
    mutationFn: async ({ app, to, rejected_at_stage }: Move) =>
      unwrap(
        await api.POST('/api/applications/{app_id}/transition', {
          params: { path: { app_id: app.id } },
          body: { to_status: to, rejected_at_stage: rejected_at_stage ?? null },
        }),
      ),
    onMutate: async ({ app, to }) => {
      await qc.cancelQueries({ queryKey: KEY })
      const previous = qc.getQueryData<ApplicationOut[]>(KEY)
      qc.setQueryData<ApplicationOut[]>(KEY, (old) => old?.map((a) => (a.id === app.id ? { ...a, status: to } : a)))
      return { previous }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(KEY, ctx.previous)
    },
    onSuccess: (_d, { app, to }) => {
      toast.success(`${app.company}: moved to ${to}`)
    },
    onSettled: () => invalidate(),
  })
}

export type TrackerFilter = { q: string; status: AppStatus | '' }

export function useFiltered(apps: ApplicationOut[] | undefined, f: TrackerFilter) {
  return useMemo(() => {
    const q = f.q.trim().toLowerCase()
    return (apps ?? []).filter(
      (a) => (!f.status || a.status === f.status) && (!q || `${a.company} ${a.title}`.toLowerCase().includes(q)),
    )
  }, [apps, f.q, f.status])
}
