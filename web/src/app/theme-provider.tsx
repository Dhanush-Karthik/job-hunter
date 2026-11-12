// Own provider instead of next-themes: it renders an inline <script>, which React 19 logs as a console error in an SPA.
import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { THEME_STORAGE_KEY, ThemeContext, type Theme } from './theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'
const media = () => (typeof window.matchMedia === 'function' ? window.matchMedia(DARK_QUERY) : null)

function readStored(): Theme {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    // storage blocked: fall back to system
  }
  return 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStored)
  const [systemDark, setSystemDark] = useState(() => media()?.matches ?? false)

  useEffect(() => {
    const mq = media()
    if (!mq) return
    const on = () => setSystemDark(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme
  useLayoutEffect(() => {
    const el = document.documentElement
    el.classList.toggle('dark', resolved === 'dark')
    el.style.colorScheme = resolved
  }, [resolved])

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, t)
    } catch {
      // not persisted, still applied
    }
  }, [])

  const value = useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
