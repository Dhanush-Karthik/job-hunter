import { ExternalLink } from 'lucide-react'
import { ErrorState } from '@/components/query-states'
import { fmtDateTime } from '@/components/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { usePatchProfile, useProfiles } from './use-settings'

const title = (p: string) => p.charAt(0).toUpperCase() + p.slice(1)
const pretty = (k: string) => k.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())

/** Profile checklists. The app only reminds: you open the platform and edit it yourself, then mark it refreshed. */
export function ProfilesPanel() {
  const profiles = useProfiles()
  const patch = usePatchProfile()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Profiles</CardTitle>
        <CardDescription>Recruiters search these. Refresh Naukri daily so it ranks higher; the app never logs in for you.</CardDescription>
      </CardHeader>
      <CardContent>
        {profiles.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading profiles" />
        ) : profiles.isError ? (
          <ErrorState error={profiles.error} onRetry={() => profiles.refetch()} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {profiles.data.map((p) => (
              <section key={p.platform} aria-label={`${title(p.platform)} profile`} className="grid content-start gap-2 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium">{title(p.platform)}</h3>
                  {p.refresh_due && <Badge variant="destructive">Refresh due</Badge>}
                  <span className="text-xs text-muted-foreground">{p.last_refreshed_at ? `refreshed ${fmtDateTime(p.last_refreshed_at)}` : 'never refreshed'}</span>
                </div>
                <ul className="grid gap-1.5">
                  {Object.entries(p.checklist).map(([key, done]) => {
                    const id = `${p.platform}-${key}`
                    return (
                      <li key={key} className="flex items-center gap-2">
                        <Checkbox id={id} checked={done} disabled={patch.isPending} onCheckedChange={(v) => patch.mutate({ platform: p.platform, checklist: { [key]: v === true } })} />
                        <Label htmlFor={id} className="font-normal">
                          {pretty(key)}
                        </Label>
                      </li>
                    )
                  })}
                </ul>
                <div className="flex flex-wrap gap-2">
                  {p.edit_url && (
                    <Button asChild size="sm" variant="outline">
                      <a href={p.edit_url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${title(p.platform)} edit page`}>
                        <ExternalLink /> Open edit page
                      </a>
                    </Button>
                  )}
                  {p.refresh_every_days != null && (
                    <Button size="sm" disabled={patch.isPending} aria-label={`Mark ${title(p.platform)} refreshed`} onClick={() => patch.mutate({ platform: p.platform, refreshed_now: true })}>
                      Mark refreshed
                    </Button>
                  )}
                </div>
              </section>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
