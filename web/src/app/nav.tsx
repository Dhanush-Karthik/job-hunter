import { BarChart3, CalendarCheck, Inbox, ListChecks, Send, Settings, Target, Zap, type LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useNavCounts } from './nav-counts'

type Item = { to: string; label: string; Icon: LucideIcon; end?: boolean; count?: 'proposals' | 'followUps' }

const NAV_ITEMS: Item[] = [
  { to: '/', label: 'Today', Icon: CalendarCheck, end: true },
  { to: '/leads', label: 'Leads', Icon: Target, end: true },
  { to: '/leads/quick-apply', label: 'Quick apply', Icon: Zap },
  { to: '/tracker', label: 'Tracker', Icon: ListChecks },
  { to: '/replies', label: 'Replies & Inbound', Icon: Inbox, count: 'proposals' },
  { to: '/outreach', label: 'Outreach & Follow-ups', Icon: Send, count: 'followUps' },
  { to: '/analytics', label: 'Analytics', Icon: BarChart3 },
  { to: '/settings', label: 'Settings', Icon: Settings },
]

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const counts = useNavCounts()
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV_ITEMS.map(({ to, label, Icon, end, count }) => {
        const n = count ? counts[count] : 0
        return (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                isActive ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/80',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            <span className="flex-1 truncate">{label}</span>
            {n > 0 && (
              <span className="rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground tabular-nums">
                {n}
                <span className="sr-only"> pending</span>
              </span>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
