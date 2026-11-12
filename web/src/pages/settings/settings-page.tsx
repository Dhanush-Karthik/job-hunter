import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { Skeleton } from '@/components/ui/skeleton'
import { ProfilesPanel } from './profiles-panel'
import { SettingsForm } from './settings-form'
import { SourcesPanel } from './sources-panel'
import { useSettings } from './use-settings'

export function SettingsPage() {
  const settings = useSettings()
  return (
    <>
      <PageHeader title="Settings" description="Intake, evaluation budget, targets, sources and profile reminders." />
      <div className="grid gap-6">
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
        <SourcesPanel />
        <ProfilesPanel />
      </div>
    </>
  )
}
