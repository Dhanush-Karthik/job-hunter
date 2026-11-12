import { Link, useParams } from 'react-router-dom'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'

export function Placeholder({ title, wave, children }: { title: string; wave: 2 | 3; children?: React.ReactNode }) {
  return (
    <>
      <PageHeader title={title} description={`Coming in Wave ${wave}.`} />
      <div className="rounded-xl border border-dashed p-8 text-sm text-muted-foreground">
        <p>This page is not built yet. The API and mocks for it already exist.</p>
        {children}
        <Button asChild variant="outline" size="sm" className="mt-4">
          <Link to="/">Back to Today</Link>
        </Button>
      </div>
    </>
  )
}

export function JobDetailPlaceholder() {
  const { id } = useParams()
  return (
    <Placeholder title="Job detail" wave={2}>
      <p className="mt-2 font-medium text-foreground">Lead #{id}</p>
    </Placeholder>
  )
}
