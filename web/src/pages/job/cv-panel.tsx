import { lazy, Suspense } from 'react'
import { BadgeCheck, ExternalLink, FileText } from 'lucide-react'
import type { ApplicationOut, RunOut } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { isActive, type Variant, type useJobMutations } from './use-job'

const PdfPreview = lazy(() => import('./pdf-preview'))

type Props = {
  application: ApplicationOut | null | undefined
  runs: RunOut[]
  mutations: ReturnType<typeof useJobMutations>
}

const cvUrl = (a: ApplicationOut) => `/api/applications/${a.id}/cv.pdf?v=${encodeURIComponent(a.updated_at)}`

/** Generate CV A or B, preview the PDF, approve it. Approving a Shortlisted application moves it to Ready (server rule). */
export function CvPanel({ application: app, runs, mutations: m }: Props) {
  const cvRun = runs.find((r) => r.kind === 'cv' && isActive(r))
  const generating = !!cvRun || m.cv.isPending
  const variants: Variant[] = ['A', 'B']
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden /> Tailored CV
          {app?.resume_variant && <Badge variant="secondary">Variant {app.resume_variant}</Badge>}
          {app?.cv_approved && (
            <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" variant="secondary">
              <BadgeCheck aria-hidden /> Approved
            </Badge>
          )}
        </CardTitle>
        <CardDescription>A is the master CV reordered; B adds the AI developer tooling section. Nothing is Ready until you approve it.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap gap-2">
          {variants.map((v) => (
            <Button key={v} size="sm" variant="outline" disabled={!app || generating} onClick={() => m.cv.mutate(v)}>
              Generate CV {v}
            </Button>
          ))}
        </div>
        {!app && <p className="text-sm text-muted-foreground">Shortlist this lead first; the CV hangs off the application.</p>}
        {generating && (
          <p role="status" className="text-sm text-muted-foreground">
            Generating CV{cvRun ? ` (run #${cvRun.id}, ${cvRun.state})` : ''}…
          </p>
        )}
        {app?.has_cv_pdf && (
          <>
            <Suspense fallback={<Skeleton className="h-96" />}>
              <PdfPreview url={cvUrl(app)} />
            </Suspense>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="ghost">
                <a href={cvUrl(app)} target="_blank" rel="noopener noreferrer">
                  <ExternalLink /> Open PDF
                </a>
              </Button>
              {!app.cv_approved && (
                <Button size="sm" disabled={m.patch.isPending} onClick={() => m.patch.mutate({ cv_approved: true })}>
                  Approve CV
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
