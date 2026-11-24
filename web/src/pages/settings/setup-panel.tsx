import { useRef, useState } from 'react'
import { CircleCheck, CircleDashed, Upload } from 'lucide-react'
import type { SetupStatus } from '@/api/client'
import { ErrorState } from '@/components/query-states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useSaveGmailSecrets, useSecrets, useSetup, useTestGmail, useUploadCv } from './use-settings'

const STEPS: { key: keyof Omit<SetupStatus, 'complete'>; label: string; hint: string }[] = [
  { key: 'cv_a', label: 'CV variant A', hint: 'Required. Master CV as markdown.' },
  { key: 'cv_b', label: 'CV variant B', hint: 'Optional. The AI-tooling variant.' },
  { key: 'gmail', label: 'Gmail app password', hint: 'Needed for alerts, replies and recruiter mail.' },
  { key: 'claude_cli', label: 'Claude CLI', hint: 'Install it and run `claude` once to log in.' },
  { key: 'careerops', label: 'career-ops', hint: 'Career-page scanning and evaluation.' },
  { key: 'playwright', label: 'Playwright browser', hint: 'Used by Assist apply.' },
]

function Checklist({ status }: { status: SetupStatus }) {
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2" aria-label="Setup checklist">
      {STEPS.map((s) => {
        const done = status[s.key]
        const Icon = done ? CircleCheck : CircleDashed
        return (
          <li key={s.key} className="flex items-start gap-2 text-sm">
            <Icon className={cn('mt-0.5 size-4 shrink-0', done ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground')} aria-hidden />
            <span>
              {s.label}: <span className="font-medium">{done ? 'done' : 'missing'}</span>
              {!done && <span className="block text-xs text-muted-foreground">{s.hint}</span>}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function CvUpload({ variant, done }: { variant: 'A' | 'B'; done: boolean }) {
  const upload = useUploadCv()
  const input = useRef<HTMLInputElement>(null)
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={`cv-${variant}`}>
        CV variant {variant} (markdown){' '}
        <Badge variant={done ? 'secondary' : 'outline'}>{done ? 'uploaded' : 'missing'}</Badge>
      </Label>
      <div className="flex gap-2">
        <Input
          id={`cv-${variant}`}
          ref={input}
          type="file"
          accept=".md,.markdown,text/markdown,text/plain"
          disabled={upload.isPending}
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return
            upload.mutate({ variant, markdown: await file.text() })
            if (input.current) input.current.value = ''
          }}
        />
        <Upload className="mt-2 size-4 shrink-0 text-muted-foreground" aria-hidden />
      </div>
      {upload.isError && <p className="text-xs text-destructive">{upload.error.message}</p>}
    </div>
  )
}

function GmailForm() {
  const secrets = useSecrets()
  const save = useSaveGmailSecrets()
  const test = useTestGmail()
  const [address, setAddress] = useState('')
  const [password, setPassword] = useState('')
  const present = (name: string) => secrets.data?.find((s) => s.name === name)?.present ?? false
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(
          { gmail_address: address.trim(), gmail_app_password: password.replaceAll(' ', '') },
          {
            onSuccess: () => {
              setAddress('')
              setPassword('')
            },
          },
        )
      }}
    >
      <h3 className="font-medium">Gmail</h3>
      <p className="text-sm text-muted-foreground">
        The app reads your inbox over IMAP. It sends mail only when you press Send on a job page&apos;s Email HR card. Use an app password, not your Google password: turn on 2-step verification, open Google Account → Security → App passwords, create one named
        “job-hunter” and paste the 16 characters here. It is stored in your system keychain and never shown again.
      </p>
      {secrets.isError && <ErrorState error={secrets.error} onRetry={() => secrets.refetch()} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="gmail-address">
            Gmail address <Badge variant={present('gmail_address') ? 'secondary' : 'outline'}>{present('gmail_address') ? 'saved' : 'not set'}</Badge>
          </Label>
          <Input id="gmail-address" type="email" autoComplete="off" placeholder={present('gmail_address') ? 'Saved; type to replace' : 'you@gmail.com'} value={address} onChange={(e) => setAddress(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="gmail-password">
            App password <Badge variant={present('gmail_app_password') ? 'secondary' : 'outline'}>{present('gmail_app_password') ? 'saved' : 'not set'}</Badge>
          </Label>
          <Input id="gmail-password" type="password" autoComplete="new-password" placeholder={present('gmail_app_password') ? 'Saved; type to replace' : '16 characters'} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={save.isPending || (!address.trim() && !password)}>
          Save to keychain
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
          Test Gmail
        </Button>
        {save.isError && <span className="text-sm text-destructive">{save.error.message}</span>}
        {test.isError && <span className="text-sm text-destructive">{test.error.message}</span>}
        {test.data && (
          <span role="status" className={cn('text-sm', test.data.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-destructive')}>
            {test.data.ok ? 'OK' : 'Failed'}: {test.data.detail}
          </span>
        )}
      </div>
    </form>
  )
}

/** First-run wizard: what is missing, CV upload, Gmail credentials. Stays on top of Settings as a status panel afterwards. */
export function SetupPanel() {
  const setup = useSetup()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Setup
          {setup.data && <Badge variant={setup.data.complete ? 'secondary' : 'destructive'}>{setup.data.complete ? 'Complete' : 'Incomplete'}</Badge>}
        </CardTitle>
        <CardDescription>Everything the app needs before intake and replies work end to end.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        {setup.isPending ? (
          <Skeleton className="h-24" role="status" aria-busy="true" aria-label="Loading setup" />
        ) : setup.isError ? (
          <ErrorState error={setup.error} onRetry={() => setup.refetch()} />
        ) : (
          <>
            <Checklist status={setup.data} />
            <div className="grid gap-4 sm:grid-cols-2">
              <CvUpload variant="A" done={setup.data.cv_a} />
              <CvUpload variant="B" done={setup.data.cv_b} />
            </div>
          </>
        )}
        <GmailForm />
      </CardContent>
    </Card>
  )
}
