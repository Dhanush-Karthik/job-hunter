import { useState, type ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { makeQueryClient } from './query-client'
import { useTheme } from './theme'
import { ThemeProvider } from './theme-provider'

function ThemedToaster() {
  return <Toaster richColors closeButton theme={useTheme().resolved} />
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(() => makeQueryClient())
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          {children}
          <ThemedToaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
