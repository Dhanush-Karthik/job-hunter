import { useParams } from 'react-router-dom'
import { isRejected } from '@/components/lead-format'
import { Markdown } from '@/components/markdown'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ActionsCard } from './actions-card'
import { CvPanel } from './cv-panel'
import { EmailHrCard } from './email-hr-card'
import { JobHeader } from './job-header'
import { RunsPanel } from './runs-panel'
import { NotesCard, OutreachCard, Timeline } from './side-cards'
import { isActive, useJob, useJobMutations, useLeadRuns } from './use-job'

function JobSkeleton() {
  return (
    <div className="grid gap-4" role="status" aria-busy="true" aria-label="Loading job">
      <Skeleton className="h-8 w-72" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <Skeleton className="h-96" />
    </div>
  )
}

export function JobDetailPage() {
  const rawId = useParams().id
  const id = Number(rawId)
  const valid = Number.isInteger(id) && id > 0
  const job = useJob(valid ? id : 0)
  const runs = useLeadRuns(valid ? id : 0)
  const lead = job.data
  const mutations = useJobMutations(id, lead?.application?.id)

  if (!valid) return <ErrorState title="Not a valid job id" error={new Error(`"${rawId}" is not a lead id`)} />
  if (job.isPending) return <JobSkeleton />
  if (job.isError) return <ErrorState error={job.error} onRetry={() => job.refetch()} />

  const runList = runs.data ?? []
  const report = lead!.evaluation?.report_md
  return (
    <>
      <JobHeader lead={lead!} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0">
          <Tabs defaultValue={report ? 'report' : 'jd'}>
            <TabsList>
              <TabsTrigger value="report">AI evaluation</TabsTrigger>
              <TabsTrigger value="jd">Job description</TabsTrigger>
            </TabsList>
            <TabsContent value="report" className="mt-4 rounded-xl border p-4">
              {report ? (
                <Markdown source={report} />
              ) : (
                <EmptyState
                  title="Not evaluated yet"
                  hint={runList.some((r) => r.kind === 'evaluate' && isActive(r)) ? 'Evaluation is running (about 3 minutes)…' : 'Press Evaluate with AI for a fit report: what matches your CV, the gaps, and how to pitch it.'}
                />
              )}
            </TabsContent>
            <TabsContent value="jd" className="mt-4 rounded-xl border p-4">
              {lead!.jd_text ? <Markdown source={lead!.jd_text} /> : <EmptyState title="No description stored" hint="Open the posting to read it." />}
            </TabsContent>
          </Tabs>
        </div>
        <div className="grid min-w-0 content-start gap-4">
          <ActionsCard lead={lead!} runs={runList} mutations={mutations} />
          {!isRejected(lead!) && <EmailHrCard lead={lead!} />}
          {lead!.application && <CvPanel application={lead!.application} runs={runList} mutations={mutations} />}
          {lead!.application && (
            <OutreachCard items={lead!.outreach} searching={mutations.contacts.isPending || runList.some((r) => r.kind === 'contacts' && isActive(r))} onFind={() => mutations.contacts.mutate()} />
          )}
          {lead!.application && <NotesCard key={lead!.application.id} app={lead!.application} mutations={mutations} />}
          {lead!.events.length > 0 && <Timeline events={lead!.events} />}
          <RunsPanel runs={runList} />
        </div>
      </div>
    </>
  )
}
