// Test helpers (not shipped): render with the same providers the app uses, on MSW.
import type { ReactElement } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach } from 'vitest'
import { makeQueryClient } from './query-client'

// vitest globals are off, so Testing Library's auto-cleanup is not registered.
afterEach(cleanup)

function LocationProbe() {
  const l = useLocation()
  return <output data-testid="location">{l.pathname + l.search}</output>
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = makeQueryClient({ retry: false })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
