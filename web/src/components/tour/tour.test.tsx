import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { TOUR_STEPS } from './steps'
import { TOUR_KEY, TourButton, TourProvider } from './tour'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().search}</p>
const app = () =>
  render(
    <MemoryRouter>
      <TourProvider>
        <nav>
          <a href="/" data-tour="nav-/">
            Home
          </a>
          <TourButton />
        </nav>
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </TourProvider>
    </MemoryRouter>,
  )

describe('first-visit tour', () => {
  it('opens by itself on the first visit and walks through every step', async () => {
    const user = userEvent.setup()
    app()
    const dialog = await screen.findByRole('dialog', {}, { timeout: 3000 })
    expect(dialog).toHaveAccessibleName('Welcome to job-hunter')
    for (let i = 1; i < TOUR_STEPS.length; i++) {
      await user.click(screen.getByRole('button', { name: 'Next' }))
      expect(screen.getByRole('dialog')).toHaveAccessibleName(TOUR_STEPS[i].title)
    }
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(localStorage.getItem(TOUR_KEY)).toBe('done')
  })

  it('can be skipped with the button or Escape, and then stays away', async () => {
    const user = userEvent.setup()
    app()
    await screen.findByRole('dialog', {}, { timeout: 3000 })
    await user.click(screen.getByRole('button', { name: 'Skip tour' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    cleanup()
    app() // second visit: the key is set, so nothing opens
    await new Promise((r) => setTimeout(r, 900))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('goes back, handles the arrow keys, and replays from the sidebar button', async () => {
    const user = userEvent.setup()
    localStorage.setItem(TOUR_KEY, 'done')
    app()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Take the tour' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName(TOUR_STEPS[0].title)
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('dialog')).toHaveAccessibleName(TOUR_STEPS[1].title)
    await user.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName(TOUR_STEPS[0].title)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('ends with a shortcut to the Gmail and resume settings', async () => {
    const user = userEvent.setup()
    localStorage.setItem(TOUR_KEY, 'done')
    app()
    await user.click(screen.getByRole('button', { name: 'Take the tour' }))
    for (let i = 1; i < TOUR_STEPS.length; i++) await user.keyboard('{ArrowRight}')
    await user.click(screen.getByRole('button', { name: 'Open Settings' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/settings?tab=account')
  })
})
