import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Plain <select> styled like the inputs: reliable on mobile and in tests. */
export function NativeSelect({ className, ...props }: React.ComponentProps<'select'>) {
  return (
    <div className="relative">
      <select
        className={cn(
          'h-8 w-full appearance-none rounded-lg border border-input bg-transparent py-1 pr-7 pl-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 [&>option]:bg-popover',
          className,
        )}
        {...props}
      />
      <ChevronDown className="pointer-events-none absolute top-2 right-2 size-4 text-muted-foreground" aria-hidden />
    </div>
  )
}
