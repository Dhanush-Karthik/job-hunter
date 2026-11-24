import { useRef } from 'react'
import { FileText, Trash2, Upload } from 'lucide-react'
import type { Settings } from '@/api/client'
import { NativeSelect } from '@/components/native-select'
import { fmtDateTime } from '@/components/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'
import { SettingsSection } from './settings-section'
import { useResume, useResumeStatus } from './use-resume'

type Reachout = Settings['reachout']

/** Every {placeholder} the email templates understand. Kept in step with `_TEMPLATE_FIELDS` in schemas.py. */
export const PLACEHOLDERS = ['greeting', 'opening', 'jobs', 'role', 'company', 'title', 'job_id', 'count', 'name', 'phone', 'linkedin', 'github', 'signature', 'location', 'url']

/** `{name}` style placeholders in a template that the server would reject. */
export const unknownPlaceholders = (template: string) =>
  [...template.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1]).filter((n) => !PLACEHOLDERS.includes(n))

export const reachoutValid = (r: Reachout) =>
  r.daily_cap >= 1 && r.daily_cap <= 200 && Number.isInteger(r.daily_cap) &&
  r.cooldown_days >= 0 && r.cooldown_days <= 180 && Number.isInteger(r.cooldown_days) &&
  r.max_jobs >= 1 && r.max_jobs <= 8 && Number.isInteger(r.max_jobs) &&
  [r.subject_one, r.subject_many, r.body].every((t) => t.trim() !== '' && unknownPlaceholders(t).length === 0) &&
  r.guess_prefixes.every((p) => /^[a-z0-9._+-]{1,40}$/i.test(p))

function TemplateField({ id, label, value, rows, onChange }: { id: string; label: string; value: string; rows?: number; onChange: (v: string) => void }) {
  const bad = unknownPlaceholders(value)
  const props = { id, value, 'aria-invalid': bad.length > 0, onChange: (e: { target: { value: string } }) => onChange(e.target.value) }
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {rows ? <Textarea rows={rows} className="font-mono text-[0.8rem]" {...props} /> : <Input {...props} />}
      {bad.length > 0 && <p className="text-xs text-destructive">Unknown placeholder {bad.map((b) => `{${b}}`).join(', ')}.</p>}
    </div>
  )
}

/** Settings > Email HR: the switch, limits, how addresses are found, who signs, and the wording of the email. */
export function ReachoutCard({ value: r, onChange }: { value: Reachout; onChange: (r: Reachout) => void }) {
  const set = (p: Partial<Reachout>) => onChange({ ...r, ...p })
  const me = (p: Partial<Reachout['me']>) => set({ me: { ...r.me, ...p } })
  return (
    <>
      <SettingsSection title="Email HR" description="The “Email HR” card on every job page: it finds the HR address, writes the email and sends it when you press Send. Nothing is ever sent on its own.">
        <div className="flex items-center gap-2">
          <Checkbox id="reachout-enabled" checked={r.enabled} onCheckedChange={(v) => set({ enabled: v === true })} />
          <Label htmlFor="reachout-enabled" className="font-normal">
            Show the Email HR card on job pages
          </Label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <NumberField label="Emails per day (max)" value={r.daily_cap} min={1} max={200} integer onChange={(n) => set({ daily_cap: n })} />
          <NumberField label="Days before emailing the same address again" value={r.cooldown_days} min={0} max={180} integer onChange={(n) => set({ cooldown_days: n })} />
          <NumberField label="Jobs listed in one email (max)" value={r.max_jobs} min={1} max={8} integer onChange={(n) => set({ max_jobs: n })} />
        </div>
        <div className="grid gap-1.5 sm:max-w-xs">
          <Label htmlFor="reachout-attach">Attach by default</Label>
          <NativeSelect id="reachout-attach" value={r.default_attach} onChange={(e) => set({ default_attach: e.target.value as Reachout['default_attach'] })}>
            <option value="tailored">The job&apos;s tailored CV (else my resume)</option>
            <option value="base">My uploaded resume</option>
            <option value="none">Nothing</option>
          </NativeSelect>
        </div>
      </SettingsSection>

      <SettingsSection title="Finding the HR address" description="Order of trust: the job description, the sender of a recruiter email, the job page, saved contacts, the company website, then common addresses.">
        <div className="flex items-center gap-2">
          <Checkbox id="reachout-web" checked={r.look_up_web} onCheckedChange={(v) => set({ look_up_web: v === true })} />
          <Label htmlFor="reachout-web" className="font-normal">
            Open the job page and the company&apos;s careers / contact pages to look for an email
          </Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox id="reachout-guess" checked={r.guess_addresses} onCheckedChange={(v) => set({ guess_addresses: v === true })} />
          <Label htmlFor="reachout-guess" className="font-normal">
            Suggest common addresses (never chosen for you)
          </Label>
        </div>
        {r.guess_addresses && <ChipInput label="Mailbox names to suggest at the company domain" values={r.guess_prefixes} onChange={(guess_prefixes) => set({ guess_prefixes })} placeholder="e.g. careers" />}
      </SettingsSection>

      <SettingsSection title="Who signs the email" description="Blank fields use your career-ops profile (data/careerops/config/profile.yml).">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="me-name">Your name</Label>
            <Input id="me-name" value={r.me.name} onChange={(e) => me({ name: e.target.value })} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="me-phone">Phone</Label>
            <Input id="me-phone" value={r.me.phone} onChange={(e) => me({ phone: e.target.value })} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="me-linkedin">LinkedIn</Label>
            <Input id="me-linkedin" value={r.me.linkedin} placeholder="linkedin.com/in/you" onChange={(e) => me({ linkedin: e.target.value })} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="me-github">GitHub</Label>
            <Input id="me-github" value={r.me.github} placeholder="github.com/you" onChange={(e) => me({ github: e.target.value })} />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="me-headline">One-line headline (used as “I am a …”)</Label>
            <Input id="me-headline" value={r.me.headline} placeholder="Java backend engineer" onChange={(e) => me({ headline: e.target.value })} />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Email wording"
        description={
          <>
            Plain text with placeholders in braces: {PLACEHOLDERS.map((p) => `{${p}}`).join(' ')}. Unknown ones are refused on save.
          </>
        }
      >
        <TemplateField id="tpl-subject-one" label="Subject for one job" value={r.subject_one} onChange={(subject_one) => set({ subject_one })} />
        <TemplateField id="tpl-subject-many" label="Subject for several jobs of one company" value={r.subject_many} onChange={(subject_many) => set({ subject_many })} />
        <TemplateField id="tpl-body" label="Message" rows={12} value={r.body} onChange={(body) => set({ body })} />
        <div>
          <Button type="button" variant="ghost" size="sm" onClick={() => set({ subject_one: DEFAULTS.subject_one, subject_many: DEFAULTS.subject_many, body: DEFAULTS.body })}>
            Reset wording to the default
          </Button>
        </div>
      </SettingsSection>
    </>
  )
}

/** Keep in step with DEFAULT_SUBJECT_ONE / DEFAULT_SUBJECT_MANY / DEFAULT_BODY in schemas.py. */
const DEFAULTS = {
  subject_one: 'Application for {title} (Job ID {job_id}) - {name}',
  subject_many: 'Applying for {count} roles at {company} - {name}',
  body: '{greeting}\n\n{opening}\n{jobs}\n\nI am a {role}. My resume is attached; the roles above match my recent work, and I would be glad to share more detail or speak with the hiring team.\n\nThank you for your time.\n\nRegards,\n{signature}',
}

/** The resume PDF attached to emails when a job has no tailored CV. Lives outside the settings form: it saves on upload. */
export function ResumeCard() {
  const status = useResumeStatus()
  const { upload, remove } = useResume()
  const input = useRef<HTMLInputElement>(null)
  const r = status.data?.resume
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden /> Resume for emails
          <Badge variant={r?.present ? 'secondary' : 'outline'}>{r?.present ? 'uploaded' : 'missing'}</Badge>
        </CardTitle>
        <CardDescription>A PDF (up to 5 MB) attached to “Email HR” when the job has no tailored CV.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {r?.present && (
          <p className="text-sm">
            {r.filename} · {r.size_kb} KB{r.updated_at ? ` · saved ${fmtDateTime(r.updated_at)}` : ''}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor="resume-pdf" className="sr-only">
            Resume PDF
          </Label>
          <Input
            id="resume-pdf"
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="max-w-sm"
            disabled={upload.isPending}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) upload.mutate(file)
              if (input.current) input.current.value = ''
            }}
          />
          <Upload className="size-4 text-muted-foreground" aria-hidden />
          {r?.present && (
            <Button type="button" variant="ghost" size="sm" disabled={remove.isPending} onClick={() => remove.mutate()}>
              <Trash2 /> Remove
            </Button>
          )}
        </div>
        {upload.isError && <p className="text-sm text-destructive">{upload.error.message}</p>}
      </CardContent>
    </Card>
  )
}
