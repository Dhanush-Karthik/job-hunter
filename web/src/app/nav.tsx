import { BarChart3, Briefcase, Home, Inbox, KanbanSquare, Settings, type LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useNavCounts, type NavCounts } from './nav-counts'

type Item = { to: string; label: string; hint: string; Icon: LucideIcon; end?: boolean; count?: keyof NavCounts }
type Group = { label?: string; items: Item[] }

// Grouped by what the owner is doing: daily work, then the bigger picture, then configuration.
const NAV: Group[] = [
  { items: [{ to: '/', label: 'Home', hint: "Today's to-do list", Icon: Home, end: true }] },
  {
    label: 'Daily work',
    items: [
      { to: '/leads', label: 'Jobs', hint: 'Review new matches and apply', Icon: Briefcase, count: 'toApply' },
      { to: '/replies', label: 'Inbox', hint: 'Recruiter mail and status updates to confirm', Icon: Inbox, count: 'proposals' },
    ],
  },
  {
    label: 'Progress',
    items: [
      { to: '/tracker', label: 'Applications', hint: 'Every application by stage', Icon: KanbanSquare },
      { to: '/analytics', label: 'Insights', hint: 'What is working', Icon: BarChart3 },
    ],
  },
]
const SETTINGS: Item = { to: '/settings', label: 'Settings', hint: 'Search rules, companies, account, system', Icon: Settings, count: 'problems' }

function NavItem({ item: { to, label, hint, Icon, end, count }, counts, onNavigate }: { item: Item; counts: NavCounts; onNavigate?: () => void }) {
  const n = count ? counts[count] : 0
  const alert = count === 'problems'
  return (
    <NavLink
      to={to}
      end={end}
      title={hint}
      data-tour={`nav-${to}`}
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
        <span
          className={cn(
            'rounded-full px-1.5 text-xs font-semibold tabular-nums',
            alert ? 'bg-destructive text-white' : 'bg-primary text-primary-foreground',
          )}
        >
          {n}
          <span className="sr-only">{alert ? ' problems' : ' pending'}</span>
        </span>
      )}
    </NavLink>
  )
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const counts = useNavCounts()
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-4">
      {NAV.map((g, i) => (
        <div key={g.label ?? i} className="grid gap-1">
          {g.label && <div className="px-2.5 pb-0.5 text-xs font-medium text-muted-foreground">{g.label}</div>}
          {g.items.map((item) => (
            <NavItem key={item.to} item={item} counts={counts} onNavigate={onNavigate} />
          ))}
        </div>
      ))}
      <div className="mt-auto grid gap-1">
        <NavItem item={SETTINGS} counts={counts} onNavigate={onNavigate} />
      </div>
    </nav>
  )
}
