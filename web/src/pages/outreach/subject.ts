import type { OutreachOut } from '@/api/client'

export const subjectOf = (o: OutreachOut) => [o.company, o.title].filter(Boolean).join(' · ') || `Outreach #${o.id}`
