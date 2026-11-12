import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

/** Switch between the ranked table and the quick-apply batch view. */
export function LeadsTabs() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    cn('rounded-lg px-3 py-1.5 text-sm font-medium', isActive ? 'bg-secondary text-secondary-foreground' : 'text-muted-foreground hover:bg-muted')
  return (
    <nav aria-label="Leads views" className="mb-4 flex gap-1">
      <NavLink to="/leads" end className={cls}>
        All leads
      </NavLink>
      <NavLink to="/leads/quick-apply" className={cls}>
        Quick apply
      </NavLink>
    </nav>
  )
}
