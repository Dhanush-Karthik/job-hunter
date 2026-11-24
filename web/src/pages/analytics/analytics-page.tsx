import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { NativeSelect } from '@/components/native-select'
import { Label } from '@/components/ui/label'
import { InsightsCard } from './insights-card'
import { KpiRow } from './kpi-row'
import { OutcomeCard } from './outcome-card'
import { PipelineCard } from './pipeline-card'
import { RANGES, useFunnel, type Range } from './use-analytics'
import { WeeklyCard } from './weekly-card'

export function AnalyticsPage() {
  const [range, setRange] = useState<Range>('30')
  const funnel = useFunnel(range)
  return (
    <>
      <PageHeader
        title="Insights"
        description="How jobs flow from shortlist to interview call, and which sources, channels, titles and CVs get you there."
        actions={
          <div className="flex items-center gap-2">
            <Label htmlFor="analytics-range" className="text-muted-foreground">
              Date range
            </Label>
            <NativeSelect id="analytics-range" className="w-32" value={range} onChange={(e) => setRange(e.target.value as Range)}>
              {RANGES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </NativeSelect>
          </div>
        }
      />
      <div className="grid gap-6">
        <KpiRow funnel={funnel} />
        <PipelineCard funnel={funnel} />
        <OutcomeCard range={range} />
        <InsightsCard range={range} />
        <WeeklyCard />
      </div>
    </>
  )
}
