import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { NativeSelect } from '@/components/native-select'
import { Label } from '@/components/ui/label'
import { BreakdownCard } from './breakdown-card'
import { CallsHeadline, FunnelCard } from './funnel-card'
import { InsightsCard } from './insights-card'
import { RejectsCard } from './rejects-card'
import { RANGES, useFunnel, type Range } from './use-analytics'
import { ResponseTimeCard, WeeklyCard } from './weekly-card'

export function AnalyticsPage() {
  const [range, setRange] = useState<Range>('30')
  const funnel = useFunnel(range)
  return (
    <>
      <PageHeader
        title="Analytics"
        description="What turns applications into interview calls, and what to change."
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
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <CallsHeadline funnel={funnel} />
          <ResponseTimeCard />
        </div>
        <InsightsCard range={range} />
        <FunnelCard funnel={funnel} />
        <BreakdownCard range={range} />
        <WeeklyCard />
        <RejectsCard range={range} />
      </div>
    </>
  )
}
