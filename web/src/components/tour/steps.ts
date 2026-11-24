export type TourStep = {
  id: string
  /** CSS selector of the thing to point at. Missing or hidden (small screens): the step is shown in the middle. */
  target?: string
  title: string
  body: string
  /** Optional button on the step that takes you somewhere. */
  cta?: { label: string; to: string }
}

/** The first-visit tour. Edit the text here; `data-tour` attributes in nav.tsx are the targets. */
export const TOUR_STEPS: TourStep[] = [
  {
    id: 'welcome',
    title: 'Welcome to job-hunter',
    body: 'It finds jobs for you every day, scores them against your CV, writes a tailored CV and an email to HR, and keeps track of every application. This one-minute tour shows where things are. You can replay it any time from the sidebar.',
  },
  { id: 'home', target: '[data-tour="nav-/"]', title: 'Home: your day in one list', body: 'Fresh matches worth your time, recruiter mail to confirm and follow-ups that are due. Start every day here and work from the top.' },
  { id: 'jobs', target: '[data-tour="nav-/leads"]', title: 'Jobs: everything it found', body: 'Every job, best match first. The score says how well it fits your CV. Shortlist the good ones, skip the rest, or open a job to apply.' },
  { id: 'inbox', target: '[data-tour="nav-/replies"]', title: 'Inbox: what companies told you', body: 'Recruiters who wrote to you and status changes read from your Gmail. Confirm each with one click and your applications update themselves.' },
  { id: 'tracker', target: '[data-tour="nav-/tracker"]', title: 'Applications: every one, by stage', body: 'Drag a card when something happens (a call, an interview, an offer). It is also how the app learns what works for you.' },
  { id: 'insights', target: '[data-tour="nav-/analytics"]', title: 'Insights: what is working', body: 'Which job sites, CV versions and titles lead to interview calls, and how fast companies reply.' },
  { id: 'settings', target: '[data-tour="nav-/settings"]', title: 'Settings: set these up first', body: 'Connect Gmail, upload your CV and resume, choose the titles and locations to search, add target companies, and change how the HR email is worded. Problems show as a red number here.' },
  {
    id: 'job',
    title: 'Inside a job: apply in four steps',
    body: 'Open any job for the AI fit report, a tailored CV, and a short checklist to apply. Below it sits the “Email HR” card: it finds the recruiter or HR address (from the job post, the job page or the company site, or you can type one), writes the email with the job ID, attaches your CV, and sends it when you press Send. Nothing is ever sent on its own.',
  },
  {
    id: 'start',
    title: 'Two things before your first send',
    body: 'Connect Gmail with an app password, and upload your resume PDF. Both are in Settings under “CVs & email”. After that, open your best-scoring job and press Send.',
    cta: { label: 'Open Settings', to: '/settings?tab=account' },
  },
]
