import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { OutreachCard } from './outreach-card'
import { useOutreach, useOutreachActions, type OutreachTab } from './use-outreach'

const TABS: { value: OutreachTab; label: string }[] = [
  { value: 'due', label: 'Due now' },
  { value: 'referrals', label: 'Referral requests' },
  { value: 'sent', label: 'Sent' },
]

const EMPTY: Record<OutreachTab, { title: string; hint: string }> = {
  due: { title: 'No follow-ups due', hint: 'A follow-up is drafted five business days after you mark an application Applied.' },
  referrals: { title: 'No referral requests waiting', hint: 'Open a job and press Find contacts; the referral draft shows up here.' },
  sent: { title: 'Nothing sent yet', hint: 'Messages you mark as sent are kept here.' },
}

function OutreachList({ tab, actions }: { tab: OutreachTab; actions: ReturnType<typeof useOutreachActions> }) {
  const q = useOutreach(tab)
  if (q.isPending)
    return (
      <div className="grid gap-3" role="status" aria-busy="true" aria-label="Loading outreach">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (q.data.length === 0) return <EmptyState {...EMPTY[tab]} />
  // Most overdue first.
  const items = tab === 'sent' ? q.data : [...q.data].sort((a, b) => (a.due_at ?? a.created_at).localeCompare(b.due_at ?? b.created_at))
  return (
    <ul className="divide-y rounded-xl border">
      {items.map((o) => (
        <OutreachCard key={o.id} o={o} actions={actions} due={tab === 'due'} />
      ))}
    </ul>
  )
}

export function OutreachPage() {
  const actions = useOutreachActions()
  const [params, setParams] = useSearchParams()
  const tab = TABS.some((t) => t.value === params.get('tab')) ? (params.get('tab') as OutreachTab) : 'due'
  return (
    <>
      <PageHeader title="Follow-ups" description="Messages drafted for you. Copy one, send it yourself (email or LinkedIn), then mark it sent. The app never sends anything." />
      <Tabs value={tab} onValueChange={(v) => setParams(v === 'due' ? {} : { tab: v }, { replace: true })}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.value} value={t.value} className="mt-3">
            <OutreachList tab={t.value} actions={actions} />
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}
