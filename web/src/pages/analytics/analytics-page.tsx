import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { NativeSelect } from '@/components/native-select'
import { Label } from '@/components/ui/label'
import { BreakdownCard } from './breakdown-card'
import { FunnelCard, KpiRow } from './funnel-card'
import { InsightsCard } from './insights-card'
import { RANGES, useFunnel, type Range } from './use-analytics'
import { WeeklyCard } from './weekly-card'

export function AnalyticsPage() {
  const [range, setRange] = useState<Range>('30')
  const funnel = useFunnel(range)
  return (
    <>
      <PageHeader
        title="Insights"
        description="Which channels, titles and CVs turn applications into interview calls, so you can do more of what works."
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
        <InsightsCard range={range} />
        <FunnelCard funnel={funnel} />
        <BreakdownCard range={range} />
        <WeeklyCard />
      </div>
    </>
  )
}
