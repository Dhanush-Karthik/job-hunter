import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'

export const useToday = () =>
  useQuery({ queryKey: ['today'], queryFn: async () => unwrap(await api.GET('/api/today')) })
