import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { inRange } from './validate'

export function NumberField({
  label,
  value,
  min,
  max,
  step,
  integer,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  integer?: boolean
  onChange: (n: number) => void
}) {
  const id = `num-${label.toLowerCase().replace(/\W+/g, '-')}`
  const bad = !inRange(value, min, max, integer)
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="number" min={min} max={max} step={step} value={Number.isFinite(value) ? value : ''} aria-invalid={bad} onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))} />
      {bad && (
        <p className="text-xs text-destructive">
          {integer ? 'Whole number between' : 'Between'} {min} and {max}.
        </p>
      )}
    </div>
  )
}
