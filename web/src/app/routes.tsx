import { lazy } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layout'

// One chunk per page; AppLayout wraps the outlet in Suspense with the PageLoading fallback.
const TodayPage = lazy(() => import('@/pages/today/today-page').then((m) => ({ default: m.TodayPage })))
const LeadsPage = lazy(() => import('@/pages/leads/leads-page').then((m) => ({ default: m.LeadsPage })))
const JobDetailPage = lazy(() => import('@/pages/job/job-page').then((m) => ({ default: m.JobDetailPage })))
const TrackerPage = lazy(() => import('@/pages/tracker/tracker-page').then((m) => ({ default: m.TrackerPage })))
const RepliesPage = lazy(() => import('@/pages/replies/replies-page').then((m) => ({ default: m.RepliesPage })))
const SettingsPage = lazy(() => import('@/pages/settings/settings-page').then((m) => ({ default: m.SettingsPage })))
const OutreachPage = lazy(() => import('@/pages/outreach/outreach-page').then((m) => ({ default: m.OutreachPage })))
const AnalyticsPage = lazy(() => import('@/pages/analytics/analytics-page').then((m) => ({ default: m.AnalyticsPage })))

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-2 inline-block text-sm underline">
        Back to Home
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
        {/* Old Quick apply page: now the "To apply" tab of Jobs. */}
        <Route path="leads/quick-apply" element={<Navigate to="/leads?tab=apply" replace />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="tracker" element={<TrackerPage />} />
        <Route path="replies" element={<RepliesPage />} />
        <Route path="outreach" element={<OutreachPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
