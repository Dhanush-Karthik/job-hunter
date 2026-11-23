import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { useToday } from '@/pages/today/use-today'
import { CompaniesPanel } from './companies-panel'
import { ProfilesPanel } from './profiles-panel'
import { RejectsCard } from './rejects-card'
import { RunLogsPanel } from './runs-panel'
import { SettingsForm, type Section } from './settings-form'
import { SetupPanel } from './setup-panel'
import { SourcesPanel } from './sources-panel'
import { useSettings } from './use-settings'

type Tab = 'search' | 'companies' | 'goals' | 'profiles' | 'account' | 'system'

const TABS: { value: Tab; label: string; hint: string }[] = [
  { value: 'search', label: 'Job search', hint: 'What to search for and which jobs to filter out automatically.' },
  { value: 'companies', label: 'Companies', hint: 'Company career pages scanned twice a day.' },
  { value: 'goals', label: 'Goals & automation', hint: 'Weekly goals, AI evaluation budget, search schedule and follow-up timing.' },
  { value: 'profiles', label: 'Profiles', hint: 'Job-site profiles recruiters search. Keep them fresh.' },
  { value: 'account', label: 'CVs & Gmail', hint: 'Your CVs and the Gmail connection.' },
  { value: 'system', label: 'System', hint: 'Service health, job sources and background task logs.' },
]

function Form({ sections }: { sections: Section[] }) {
  const settings = useSettings()
  if (settings.isPending)
    return (
      <div className="grid gap-4" role="status" aria-busy="true" aria-label="Loading settings">
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    )
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
  // keyed on the fetch time so a refetch after saving resets the form to what the server stored
  return <SettingsForm key={settings.dataUpdatedAt} initial={settings.data} sections={sections} />
}

function HealthCard() {
  const today = useToday()
  const health = today.data?.health ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle>Service health</CardTitle>
        <CardDescription>Everything the app relies on. Problems also show as a banner on Home.</CardDescription>
      </CardHeader>
      <CardContent>
        {today.isPending ? (
          <Skeleton className="h-10" />
        ) : (
          <ul className="flex flex-wrap gap-2" aria-label="Service health">
            {health.map((h) => (
              <li
                key={h.name}
                title={h.detail ?? (h.ok ? 'ok' : 'down')}
                className={cn(
                  'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
                  h.ok ? 'text-foreground' : 'border-destructive/40 bg-destructive/5 text-destructive',
                )}
              >
                <span className={cn('size-2 rounded-full', h.ok ? 'bg-emerald-500' : 'bg-destructive')} aria-hidden />
                {h.name}
                <span className="sr-only">{h.ok ? 'ok' : 'problem'}</span>
                {!h.ok && h.detail && <span className="font-normal text-muted-foreground">· {h.detail}</span>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.some((t) => t.value === params.get('tab')) ? params.get('tab') : 'search') as Tab
  return (
    <>
      <PageHeader title="Settings" description={TABS.find((t) => t.value === tab)!.hint} />
      <Tabs value={tab} onValueChange={(v) => setParams(v === 'search' ? {} : { tab: v }, { replace: true })}>
        <TabsList className="h-auto flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="search" className="mt-4 grid gap-6">
          <Form sections={['query', 'prefilter']} />
          <RejectsCard />
        </TabsContent>
        <TabsContent value="companies" className="mt-4">
          <CompaniesPanel />
        </TabsContent>
        <TabsContent value="goals" className="mt-4">
          <Form sections={['targets', 'evaluation', 'schedules', 'followups']} />
        </TabsContent>
        <TabsContent value="profiles" className="mt-4">
          <ProfilesPanel />
        </TabsContent>
        <TabsContent value="account" className="mt-4">
          <SetupPanel />
        </TabsContent>
        <TabsContent value="system" className="mt-4 grid gap-6">
          <HealthCard />
          <SourcesPanel />
          <RunLogsPanel />
        </TabsContent>
      </Tabs>
    </>
  )
}
