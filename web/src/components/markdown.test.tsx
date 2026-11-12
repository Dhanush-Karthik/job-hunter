import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import '@/app/test-utils'
import { Markdown } from './markdown'

const SRC = `# Evaluation: Okta

**Score 4.6** and _strong_ with \`Java 17\`

## Match
- Spring Boot
- Keycloak

1. first
2. second

| Area | Verdict |
|---|---|
| Stack | **A** |
| Comp | B |

> careful here

\`\`\`yaml
score: 4.6
\`\`\`
`

describe('Markdown', () => {
  it('renders headings, emphasis, lists, tables, quotes and code', () => {
    const { container } = render(<Markdown source={SRC} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Evaluation: Okta' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Match' })).toBeInTheDocument()
    expect(container.querySelector('strong')).toHaveTextContent('Score 4.6')
    expect(container.querySelector('em')).toHaveTextContent('strong')
    expect(within(screen.getAllByRole('list')[0]).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getAllByRole('list')[1].tagName).toBe('OL')
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: 'Verdict' })).toBeInTheDocument()
    expect(within(table).getByRole('cell', { name: 'A' })).toBeInTheDocument()
    expect(screen.getByText('careful here')).toBeInTheDocument()
    expect(container.querySelector('pre')).toHaveTextContent('score: 4.6')
  })

  it('never injects raw HTML or unsafe links', () => {
    const { container } = render(
      <Markdown source={'<img src=x onerror=alert(1)> and <script>alert(2)</script>\n\n[bad](javascript:alert(3)) [ok](https://example.com/a)'} />,
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror=alert(1)>')
    const links = container.querySelectorAll('a')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', 'https://example.com/a')
    expect(links[0]).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(container).toHaveTextContent('bad')
  })
})
