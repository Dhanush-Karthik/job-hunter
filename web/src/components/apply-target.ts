import type { LeadDetail } from '@/api/client'
import { SOURCE_LABEL } from './lead-format'

type Input = Pick<LeadDetail, 'source' | 'source_detail' | 'company' | 'title' | 'apply_url' | 'canonical_url' | 'source_email_url'>

export type ApplyTarget = {
  /** Where the lead came from, in words: "LinkedIn", "Recruiter email", "Hirist job alert". */
  source: string
  /** What the main button says and opens. null href: nothing stored, only the search fallback. */
  label: string
  href: string | null
  /** One sentence on where and how to apply, shown when the link is not a plain apply page. */
  note: string | null
  /** Always available: a web search for the role, for leads without a usable link. */
  searchHref: string
}

const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function sourceName(l: Pick<Input, 'source' | 'source_detail'>) {
  if (l.source === 'gmail_inbound') return 'Recruiter email'
  if (l.source === 'gmail_alert') return l.source_detail ? `${cap(l.source_detail)} job alert` : 'Job-alert email'
  return SOURCE_LABEL[l.source]
}

/** The one place to go to apply for this lead, and the words that explain it. */
export function applyTarget(l: Input): ApplyTarget {
  const source = sourceName(l)
  const searchHref = `https://www.google.com/search?q=${encodeURIComponent(`${l.company} ${l.title} apply`)}`
  if (l.apply_url) return { source, label: `Apply on ${host(l.apply_url)}`, href: l.apply_url, note: null, searchHref }
  if (l.canonical_url) {
    return {
      source,
      label: `Open the ${host(l.canonical_url)} posting`,
      href: l.canonical_url,
      note: `Found on ${source}. Apply from the posting page.`,
      searchHref,
    }
  }
  if (l.source_email_url) {
    return {
      source,
      label: "Open the recruiter's email",
      href: l.source_email_url,
      note: 'A recruiter emailed you this role and there is no job link in it. Apply with the button inside their email, or reply to them.',
      searchHref,
    }
  }
  return {
    source,
    label: 'Search for the posting',
    href: null,
    note: `Found via ${source} without a link. Search for it, or check the company's careers page.`,
    searchHref,
  }
}
