// Turns raw email snippets (HTML entities, tracking URLs, separator lines, footers) into short readable text.

const ENTITIES: Record<string, string> = { nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", '#39': "'" }

/** Footer phrases after which the rest of an email is boilerplate. */
const FOOTERS = [/this email was intended for/i, /learn why we included this/i, /unsubscribe/i, /you are receiving this/i]

export function decodeEntities(s: string): string {
  return s.replace(/&(#?\w+);/g, (m, name: string) => {
    if (name in ENTITIES) return ENTITIES[name]
    if (name.startsWith('#')) {
      const code = name[1] === 'x' ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10)
      return Number.isFinite(code) ? String.fromCodePoint(code) : m
    }
    return m
  })
}

/** Readable body: entities decoded, URLs and template placeholders dropped, footer cut, whitespace collapsed. */
export function cleanEmail(raw: string | null | undefined): string {
  if (!raw) return ''
  let s = decodeEntities(raw)
  for (const f of FOOTERS) {
    const i = s.search(f)
    if (i > 0) s = s.slice(0, i)
  }
  return s
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\[\[[A-Z_]+\]\]/g, '')
    .replace(/-{4,}|={4,}|_{4,}/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, '\n')
    .trim()
}

/** First line of the email, usually its subject. */
export function emailHeadline(raw: string | null | undefined): string {
  return cleanEmail(raw).split('\n')[0] ?? ''
}

/** Everything after the first line. */
export function emailBody(raw: string | null | undefined): string {
  return cleanEmail(raw).split('\n').slice(1).join(' ').trim()
}
