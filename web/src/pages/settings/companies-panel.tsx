import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { Company } from '@/api/client'
import { EmptyState, ErrorState } from '@/components/query-states'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useCompanies, useCompanyActions } from './use-settings'

const validUrl = (u: string) => {
  try {
    return ['http:', 'https:'].includes(new URL(u).protocol)
  } catch {
    return false
  }
}

function AddCompany({ actions }: { actions: ReturnType<typeof useCompanyActions> }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const ok = name.trim().length > 0 && validUrl(url.trim())
  return (
    <form
      className="grid items-end gap-3 sm:grid-cols-[1fr_2fr_auto]"
      onSubmit={(e) => {
        e.preventDefault()
        if (ok)
          actions.add.mutate(
            { name: name.trim(), careers_url: url.trim() },
            {
              onSuccess: () => {
                setName('')
                setUrl('')
              },
            },
          )
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor="company-name">Company name</Label>
        <Input id="company-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Postman" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="company-url">Careers URL</Label>
        <Input id="company-url" type="url" value={url} aria-invalid={url !== '' && !validUrl(url.trim())} onChange={(e) => setUrl(e.target.value)} placeholder="https://jobs.example.com" />
      </div>
      <Button type="submit" disabled={!ok || actions.busy}>
        <Plus /> Add company
      </Button>
      {actions.add.isError && <p className="text-sm text-destructive sm:col-span-3">{actions.add.error.message}</p>}
    </form>
  )
}

/** Companies the career-page scan watches. "API" means a known ATS the app reads directly; otherwise it falls back to web search. */
export function CompaniesPanel() {
  const companies = useCompanies()
  const actions = useCompanyActions()
  const [q, setQ] = useState('')
  const [pending, setPending] = useState<Company | null>(null)
  const shown = companies.data?.filter((c) => `${c.name} ${c.careers_url}`.toLowerCase().includes(q.trim().toLowerCase())) ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle>Companies</CardTitle>
        <CardDescription>Career pages scanned twice a day. Disable a company to keep it in the list without scanning it.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <AddCompany actions={actions} />
        {companies.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading companies" />
        ) : companies.isError ? (
          <ErrorState error={companies.error} onRetry={() => companies.refetch()} />
        ) : (
          <>
            <div className="flex items-center gap-3">
              <Label htmlFor="company-search" className="sr-only">
                Search companies
              </Label>
              <Input id="company-search" type="search" className="max-w-xs" placeholder="Search companies" value={q} onChange={(e) => setQ(e.target.value)} />
              <span className="text-sm text-muted-foreground">
                {shown.length} of {companies.data.length}
              </span>
            </div>
            {shown.length === 0 ? (
              <EmptyState title={companies.data.length ? 'No company matches' : 'No companies yet'} />
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <Table className="min-w-[40rem]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Company</TableHead>
                      <TableHead>Scan via</TableHead>
                      <TableHead>Careers page</TableHead>
                      <TableHead>Enabled</TableHead>
                      <TableHead className="w-12">
                        <span className="sr-only">Delete</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {shown.map((c) => (
                      <TableRow key={c.name}>
                        <TableCell className="font-medium">{c.name}</TableCell>
                        <TableCell>
                          {c.provider ? (
                            <Badge variant="secondary" title={`ATS: ${c.provider}`}>
                              API
                            </Badge>
                          ) : (
                            <Badge variant="outline" title={c.notes ?? 'No supported ATS found; uses web search'}>
                              websearch
                            </Badge>
                          )}
                          {c.provider && <span className="ml-2 text-xs text-muted-foreground">{c.provider}</span>}
                        </TableCell>
                        <TableCell className="max-w-72 truncate">
                          <a href={c.careers_url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                            {c.careers_url}
                          </a>
                        </TableCell>
                        <TableCell>
                          <Switch size="sm" aria-label={`Enable ${c.name}`} checked={c.enabled} disabled={actions.busy} onCheckedChange={(enabled) => actions.toggle.mutate({ name: c.name, enabled })} />
                        </TableCell>
                        <TableCell>
                          <Button size="icon-sm" variant="ghost" aria-label={`Delete ${c.name}`} disabled={actions.busy} onClick={() => setPending(c)}>
                            <Trash2 />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </>
        )}
      </CardContent>
      <AlertDialog open={pending != null} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pending?.name}?</AlertDialogTitle>
            <AlertDialogDescription>It is removed from the scan list. Leads already found stay.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => pending && actions.remove.mutate(pending.name)}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
