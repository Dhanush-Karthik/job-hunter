import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { Skeleton } from '@/components/ui/skeleton'
import { CompaniesPanel } from './companies-panel'
import { ProfilesPanel } from './profiles-panel'
import { RunLogsPanel } from './runs-panel'
import { SettingsForm } from './settings-form'
import { SetupPanel } from './setup-panel'
import { SourcesPanel } from './sources-panel'
import { useSettings } from './use-settings'

export function SettingsPage() {
  const settings = useSettings()
  return (
    <>
      <PageHeader title="Settings" description="Setup, intake, evaluation budget, targets, rules, schedules, sources and run logs." />
      <div className="grid gap-6">
        <SetupPanel />
        {settings.isPending ? (
          <div className="grid gap-4" role="status" aria-busy="true" aria-label="Loading settings">
            <Skeleton className="h-32" />
            <Skeleton className="h-48" />
          </div>
        ) : settings.isError ? (
          <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
        ) : (
          // keyed on the fetch time so a refetch after saving resets the form to what the server stored
          <SettingsForm key={settings.dataUpdatedAt} initial={settings.data} />
        )}
        <CompaniesPanel />
        <SourcesPanel />
        <ProfilesPanel />
        <RunLogsPanel />
      </div>
    </>
  )
}
