// Small, safe markdown renderer for evaluation reports and JD text. Builds React elements only: raw HTML in the source
// is shown as text and never injected. Supports headings, paragraphs, lists, tables, code fences, quotes, rules,
// and inline bold / italic / code / links (http, https, mailto only).
import { Fragment, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

const SAFE_HREF = /^(https?:\/\/|mailto:)/i
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(_[^_\n]+_)|(\[[^\]\n]+\]\([^)\s]+\))/g

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let i = 0
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0
    if (at > last) out.push(text.slice(last, at))
    const tok = m[0]
    const key = `${keyBase}-${i++}`
    if (tok.startsWith('`')) out.push(<code key={key} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{tok.slice(1, -1)}</code>)
    else if (tok.startsWith('**')) out.push(<strong key={key}>{inline(tok.slice(2, -2), key)}</strong>)
    else if (tok.startsWith('[')) {
      const [, label, href] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!
      out.push(
        SAFE_HREF.test(href) ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
            {label}
          </a>
        ) : (
          label
        ),
      )
    } else out.push(<em key={key}>{inline(tok.slice(1, -1), key)}</em>)
    last = at + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

type Block =
  | { t: 'h'; level: number; text: string }
  | { t: 'p'; text: string }
  | { t: 'ul' | 'ol'; items: string[] }
  | { t: 'code'; text: string }
  | { t: 'quote'; text: string }
  | { t: 'hr' }
  | { t: 'table'; head: string[]; rows: string[][] }

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())
const isTableSep = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line) && line.includes('-')
const isBlockStart = (line: string) => /^(#{1,6}\s|```|>\s?|[-*+]\s|\d+[.)]\s|(-{3,}|\*{3,})\s*$)/.test(line)

function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
      continue
    }
    if (line.startsWith('```')) {
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) body.push(lines[i++])
      i++
      blocks.push({ t: 'code', text: body.join('\n') })
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      blocks.push({ t: 'h', level: h[1].length, text: h[2].replace(/\s+#+\s*$/, '') })
      i++
      continue
    }
    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push({ t: 'hr' })
      i++
      continue
    }
    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) rows.push(cells(lines[i++]))
      blocks.push({ t: 'table', head, rows })
      continue
    }
    if (/^>\s?/.test(line)) {
      const body: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ''))
      blocks.push({ t: 'quote', text: body.join(' ') })
      continue
    }
    const list = /^([-*+]|\d+[.)])\s+/.exec(line)
    if (list) {
      const ordered = /\d/.test(list[1])
      const items: string[] = []
      while (i < lines.length) {
        const m = /^([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i])
        if (m && /\d/.test(m[1]) === ordered) items.push(m[2])
        else if (/^\s{2,}\S/.test(lines[i]) && items.length) items[items.length - 1] += ` ${lines[i].trim()}`
        else break
        i++
      }
      blocks.push({ t: ordered ? 'ol' : 'ul', items })
      continue
    }
    const para: string[] = [line]
    i++
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) para.push(lines[i++])
    blocks.push({ t: 'p', text: para.join(' ') })
  }
  return blocks
}

const HEADING = ['text-xl font-semibold', 'text-lg font-semibold', 'text-base font-semibold', 'text-sm font-semibold', 'text-sm font-medium', 'text-sm font-medium']

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = parseMarkdown(source)
  return (
    <div className={cn('grid gap-3 text-sm leading-relaxed', className)}>
      {blocks.map((b, n) => {
        const key = `b${n}`
        switch (b.t) {
          case 'h': {
            const Tag = `h${Math.min(b.level + 1, 6)}` as 'h2'
            return (
              <Tag key={key} className={cn('mt-2 first:mt-0', HEADING[b.level - 1])}>
                {inline(b.text, key)}
              </Tag>
            )
          }
          case 'p':
            return <p key={key}>{inline(b.text, key)}</p>
          case 'ul':
          case 'ol': {
            const Tag = b.t
            return (
              <Tag key={key} className={cn('grid gap-1 pl-5', b.t === 'ul' ? 'list-disc' : 'list-decimal')}>
                {b.items.map((it, j) => (
                  <li key={j}>{inline(it, `${key}-${j}`)}</li>
                ))}
              </Tag>
            )
          }
          case 'code':
            return (
              <pre key={key} className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">
                {b.text}
              </pre>
            )
          case 'quote':
            return (
              <blockquote key={key} className="border-l-2 pl-3 text-muted-foreground">
                {inline(b.text, key)}
              </blockquote>
            )
          case 'hr':
            return <hr key={key} />
          case 'table':
            return (
              <div key={key} className="overflow-x-auto rounded-lg border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j} className="px-3 py-1.5 font-medium">
                          {inline(c, `${key}-h${j}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {b.head.map((_, k) => (
                          <Fragment key={k}>
                            <td className="px-3 py-1.5 align-top">{inline(r[k] ?? '', `${key}-${j}-${k}`)}</td>
                          </Fragment>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        }
      })}
    </div>
  )
}
