// Placeholder shell; Wave 1 (builder2) replaces this with src/app/** (router, nav, pages).
import { useEffect, useState } from 'react'
import { api, type Health } from '@/api/client'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  useEffect(() => {
    api.GET('/api/health').then((r) => setHealth(r.data ?? null))
  }, [])
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">job-hunter</h1>
      <p className="text-muted-foreground mt-2">API: {health ? `ok (${health.version})` : 'unreachable'}</p>
    </main>
  )
}
