import { Link, Route, Routes } from 'react-router-dom'
import { LeadsPage } from '@/pages/leads/leads-page'
import { QuickApplyPage } from '@/pages/leads/quick-apply-page'
import { JobDetailPlaceholder, Placeholder } from '@/pages/placeholder/placeholder'
import { TodayPage } from '@/pages/today/today-page'
import { AppLayout } from './layout'

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-2 inline-block text-sm underline">
        Back to Today
      </Link>
    </div>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<TodayPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="leads/quick-apply" element={<QuickApplyPage />} />
        <Route path="jobs/:id" element={<JobDetailPlaceholder />} />
        <Route path="tracker" element={<Placeholder title="Tracker" wave={2} />} />
        <Route path="replies" element={<Placeholder title="Replies & Inbound" wave={3} />} />
        <Route path="outreach" element={<Placeholder title="Outreach & Follow-ups" wave={3} />} />
        <Route path="analytics" element={<Placeholder title="Analytics" wave={3} />} />
        <Route path="settings" element={<Placeholder title="Settings" wave={2} />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
