import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark' | 'system'
export const THEME_STORAGE_KEY = 'jh-theme'

export const ThemeContext = createContext<{ theme: Theme; resolved: 'light' | 'dark'; setTheme: (t: Theme) => void }>({
  theme: 'system',
  resolved: 'light',
  setTheme: () => {},
})

export const useTheme = () => useContext(ThemeContext)
