import { Building2, ListFilter, Mail, SlidersHorizontal, Activity, UserCircle2, type LucideIcon } from 'lucide-react'
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
import { ResumeCard } from './reachout-card'
import { RejectsCard } from './rejects-card'
import { RunLogsPanel } from './runs-panel'
import { SettingsForm, type Section } from './settings-form'
import { SetupPanel } from './setup-panel'
import { SourcesPanel } from './sources-panel'
import { useSettings } from './use-settings'

type Tab = 'search' | 'companies' | 'goals' | 'profiles' | 'account' | 'system'

const TABS: { value: Tab; label: string; hint: string; Icon: LucideIcon }[] = [
  { value: 'search', label: 'Job search', Icon: ListFilter, hint: 'What to search for and which jobs to filter out automatically.' },
  { value: 'companies', label: 'Companies', Icon: Building2, hint: 'Company career pages scanned twice a day.' },
  { value: 'goals', label: 'Goals & automation', Icon: SlidersHorizontal, hint: 'Weekly goals, AI evaluation budget, search schedule and quiet hours.' },
  { value: 'profiles', label: 'Profiles', Icon: UserCircle2, hint: 'Job-site profiles recruiters search. Keep them fresh.' },
  { value: 'account', label: 'CVs & email', Icon: Mail, hint: 'Your CVs, the Gmail connection and how Email HR works.' },
  { value: 'system', label: 'System', Icon: Activity, hint: 'Service health, job sources and background task logs.' },
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
      <Tabs orientation="vertical" value={tab} onValueChange={(v) => setParams(v === 'search' ? {} : { tab: v }, { replace: true })} className="gap-6 lg:flex-row lg:gap-10">
        <TabsList variant="line" className="h-auto w-full shrink-0 flex-row justify-start gap-1 overflow-x-auto p-0 lg:sticky lg:top-6 lg:w-52 lg:flex-col lg:items-stretch lg:self-start lg:overflow-visible">
          {TABS.map(({ value, label, Icon }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="h-9 flex-none justify-start gap-2.5 rounded-lg px-3 data-active:bg-muted data-active:font-semibold lg:flex-none group-data-[variant=line]/tabs-list:data-active:bg-muted dark:group-data-[variant=line]/tabs-list:data-active:bg-muted after:hidden"
            >
              <Icon aria-hidden />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="min-w-0 max-w-4xl flex-1">
          <TabsContent value="search" className="grid">
            <Form sections={['query', 'prefilter']} />
            <div className="pt-7">
              <RejectsCard />
            </div>
          </TabsContent>
          <TabsContent value="companies">
            <CompaniesPanel />
          </TabsContent>
          <TabsContent value="goals">
            <Form sections={['targets', 'evaluation', 'schedules', 'notifications']} />
          </TabsContent>
          <TabsContent value="profiles">
            <ProfilesPanel />
          </TabsContent>
          <TabsContent value="account" className="grid gap-6">
            <SetupPanel />
            <ResumeCard />
            <div className="-mt-7">
              <Form sections={['reachout']} />
            </div>
          </TabsContent>
          <TabsContent value="system" className="grid gap-6">
            <HealthCard />
            <SourcesPanel />
            <RunLogsPanel />
          </TabsContent>
        </div>
      </Tabs>
    </>
  )
}
