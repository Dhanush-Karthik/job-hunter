import { Monitor, Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from './theme'

const OPTIONS = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Monitor },
] as const

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <div role="group" aria-label="Theme" className="flex gap-1">
      {OPTIONS.map(({ value, label, Icon }) => (
        <Button
          key={value}
          variant={theme === value ? 'secondary' : 'ghost'}
          size="icon-sm"
          aria-label={`${label} theme`}
          aria-pressed={theme === value}
          title={`${label} theme`}
          onClick={() => setTheme(value)}
        >
          <Icon />
        </Button>
      ))}
    </div>
  )
}
