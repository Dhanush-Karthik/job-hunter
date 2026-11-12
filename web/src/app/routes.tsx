import { lazy } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { Placeholder } from '@/pages/placeholder/placeholder'
import { AppLayout } from './layout'

// One chunk per page; AppLayout wraps the outlet in Suspense with the PageLoading fallback.
const TodayPage = lazy(() => import('@/pages/today/today-page').then((m) => ({ default: m.TodayPage })))
const LeadsPage = lazy(() => import('@/pages/leads/leads-page').then((m) => ({ default: m.LeadsPage })))
const JobDetailPage = lazy(() => import('@/pages/job/job-page').then((m) => ({ default: m.JobDetailPage })))
const TrackerPage = lazy(() => import('@/pages/tracker/tracker-page').then((m) => ({ default: m.TrackerPage })))
const RepliesPage = lazy(() => import('@/pages/replies/replies-page').then((m) => ({ default: m.RepliesPage })))
const SettingsPage = lazy(() => import('@/pages/settings/settings-page').then((m) => ({ default: m.SettingsPage })))
const QuickApplyPage = lazy(() => import('@/pages/leads/quick-apply-page').then((m) => ({ default: m.QuickApplyPage })))

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
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="tracker" element={<TrackerPage />} />
        <Route path="replies" element={<RepliesPage />} />
        <Route path="outreach" element={<Placeholder title="Outreach & Follow-ups" wave={3} />} />
        <Route path="analytics" element={<Placeholder title="Analytics" wave={3} />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
