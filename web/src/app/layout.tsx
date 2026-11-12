import { useState } from 'react'
import { Menu, Rocket } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { SidebarNav } from './nav'
import { ThemeToggle } from './theme-toggle'

function Brand() {
  return (
    <div className="flex items-center gap-2 px-2.5 text-base font-semibold">
      <Rocket className="size-5" aria-hidden />
      job-hunter
    </div>
  )
}

export function AppLayout() {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside className="sticky top-0 hidden h-svh w-60 shrink-0 flex-col gap-4 border-r bg-sidebar p-3 text-sidebar-foreground md:flex">
        <Brand />
        <SidebarNav />
        <div className="mt-auto flex items-center justify-between px-1">
          <span className="text-xs text-muted-foreground">Theme</span>
          <ThemeToggle />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b bg-background/95 px-4 py-2 backdrop-blur md:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Open navigation">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="gap-4 bg-sidebar p-3 text-sidebar-foreground">
              <SheetHeader className="p-0">
                <SheetTitle>
                  <Brand />
                </SheetTitle>
                <SheetDescription className="sr-only">Navigation</SheetDescription>
              </SheetHeader>
              <SidebarNav onNavigate={() => setOpen(false)} />
              <div className="mt-auto flex items-center justify-between px-1">
                <span className="text-xs text-muted-foreground">Theme</span>
                <ThemeToggle />
              </div>
            </SheetContent>
          </Sheet>
          <Brand />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
