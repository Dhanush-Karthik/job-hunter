import type { ReactNode } from 'react'

/** A settings group: what it is on the left, the fields on the right. Stacks on narrow screens. */
export function SettingsSection({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-b py-7 first:pt-0 last:border-b-0 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10" aria-label={title}>
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      <div className="grid gap-5 rounded-xl border bg-card p-5 shadow-xs">{children}</div>
    </section>
  )
}
