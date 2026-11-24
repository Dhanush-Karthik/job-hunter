import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap, type JobReachout } from '@/api/client'

const KEY = 'reachout'
const path = (lead_id: number) => ({ params: { path: { lead_id } } })

export type Attach = 'tailored' | 'base' | 'none'

/** The "Email HR" card's data for one job: candidate addresses, the written email, attachments, history. */
export const useJobReachout = (leadId: number) =>
  useQuery({ queryKey: [KEY, 'job', leadId], queryFn: async () => unwrap(await api.GET('/api/reachout/jobs/{lead_id}', path(leadId))) })

/** Looks the HR address up on the web (job page, company site, common addresses). Runs once per job, on its own. */
export function useFindHr(leadId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/reachout/jobs/{lead_id}/find', path(leadId))),
    onSuccess: (data: JobReachout) => qc.setQueryData([KEY, 'job', leadId], data),
  })
}

/** The email text for a recipient name and extra jobs. Pure: nothing is sent or stored. */
export const useEmailDraft = (leadId: number, toName: string | null, extra: number[], enabled: boolean) =>
  useQuery({
    queryKey: [KEY, 'draft', leadId, toName, extra],
    enabled,
    placeholderData: keepPreviousData,
    queryFn: async () => unwrap(await api.POST('/api/reachout/jobs/{lead_id}/draft', { ...path(leadId), body: { to_name: toName, extra_lead_ids: extra } })),
  })

export type SendInput = {
  to_email: string
  to_name: string | null
  extra_lead_ids: number[]
  subject: string
  body: string
  attach: Attach
  mode: 'send' | 'draft'
  force: boolean
}

/** The only call that can send mail. `confirm: true` is set here because it is only reached from the Send button. */
export function useSendEmail(leadId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: SendInput) => unwrap(await api.POST('/api/reachout/jobs/{lead_id}/send', { ...path(leadId), body: { ...v, confirm: true } })),
    onSuccess: (r) => {
      toast.success(r.state === 'sent' ? `Email sent to ${r.to_email}` : 'Saved to your Gmail drafts')
      return qc.invalidateQueries({ queryKey: [KEY] })
    },
  })
}
