import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { OutreachCard } from './outreach-card'
import { useOutreach, useOutreachActions, type OutreachTab } from './use-outreach'

const EMPTY: Record<OutreachTab, { title: string; hint: string }> = {
  due: { title: 'No follow-ups due', hint: 'Follow-ups appear here five business days after you mark an application Applied.' },
  referrals: { title: 'No referral drafts waiting', hint: 'Find contacts from a job page and the referral draft shows up here.' },
  sent: { title: 'Nothing sent yet', hint: 'Messages you mark as sent are logged here.' },
}

function OutreachList({ tab, actions }: { tab: OutreachTab; actions: ReturnType<typeof useOutreachActions> }) {
  const q = useOutreach(tab)
  if (q.isPending)
    return (
      <div className="grid gap-3" role="status" aria-busy="true" aria-label="Loading outreach">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
    )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (q.data.length === 0) return <EmptyState {...EMPTY[tab]} />
  return (
    <ul className="grid gap-3">
      {q.data.map((o) => (
        <OutreachCard key={o.id} o={o} actions={actions} due={tab === 'due'} />
      ))}
    </ul>
  )
}

export function OutreachPage() {
  const actions = useOutreachActions()
  return (
    <>
      <PageHeader title="Outreach & Follow-ups" description="Copy, send it yourself, then Mark sent. This app never sends a message for you." />
      <Tabs defaultValue="due">
        <TabsList>
          <TabsTrigger value="due">Due follow-ups</TabsTrigger>
          <TabsTrigger value="referrals">Referrals</TabsTrigger>
          <TabsTrigger value="sent">Sent log</TabsTrigger>
        </TabsList>
        {(['due', 'referrals', 'sent'] as const).map((tab) => (
          <TabsContent key={tab} value={tab}>
            <OutreachList tab={tab} actions={actions} />
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}
