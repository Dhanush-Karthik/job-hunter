import { MutationCache, QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

/** Mutations surface the server's detail (unwrap throws "<status> <detail>") as a toast. */
export function makeQueryClient({ retry = 1 }: { retry?: number | false } = {}) {
  return new QueryClient({
    mutationCache: new MutationCache({
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Request failed'),
    }),
    defaultOptions: { queries: { staleTime: 15_000, retry, refetchOnWindowFocus: false } },
  })
}
