import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'

const KEY = ['reachout', 'status']

const b64 = (buf: ArrayBuffer) => {
  let s = ''
  const bytes = new Uint8Array(buf)
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(s)
}

/** The resume PDF that "Email HR" attaches, plus Gmail and send counters. */
export const useResumeStatus = () => useQuery({ queryKey: KEY, queryFn: async () => unwrap(await api.GET('/api/reachout/status')) })

export function useResume() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['reachout'] })
  const upload = useMutation({
    mutationFn: async (file: File) => unwrap(await api.PUT('/api/reachout/resume', { body: { filename: file.name, data_base64: b64(await file.arrayBuffer()) } })),
    onSuccess: () => {
      toast.success('Resume saved')
      return refresh()
    },
  })
  const remove = useMutation({
    mutationFn: async () => {
      await api.DELETE('/api/reachout/resume')
    },
    onSuccess: refresh,
  })
  return { upload, remove }
}
