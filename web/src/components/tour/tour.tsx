import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { CircleHelp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { TOUR_STEPS, type TourStep } from './steps'

/** localStorage key. Bump the suffix to show the tour again after a big redesign. */
export const TOUR_KEY = 'jobhunter.tour.v1'

const seen = () => {
  try {
    return localStorage.getItem(TOUR_KEY) != null
  } catch {
    return true // storage blocked: never nag
  }
}
const markSeen = () => {
  try {
    localStorage.setItem(TOUR_KEY, 'done')
  } catch {
    /* private mode: the tour just shows again next visit */
  }
}

const TourContext = createContext<{ start: () => void }>({ start: () => {} })
export const useTour = () => useContext(TourContext)

type Box = { top: number; left: number; width: number; height: number }
const PAD = 6
const CARD_W = 352

function measure(selector: string | undefined): Box | null {
  if (!selector) return null
  const el = document.querySelector(selector)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0 ? { top: r.top, left: r.left, width: r.width, height: r.height } : null
}

function TourCard({ step, index, total, box, onBack, onNext, onSkip, onCta }: { step: TourStep; index: number; total: number; box: Box | null; onBack: () => void; onNext: () => void; onSkip: () => void; onCta: (to: string) => void }) {
  const next = useRef<HTMLButtonElement>(null)
  useEffect(() => next.current?.focus(), [index])
  const last = index === total - 1
  // Beside the highlighted item when there is room, else centred on screen.
  const beside = box != null && box.left + box.width + CARD_W + 24 < window.innerWidth
  const style = beside ? { top: Math.max(12, Math.min(box.top - 8, window.innerHeight - 300)), left: box.left + box.width + 16, width: CARD_W } : undefined
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-title"
      aria-describedby="tour-body"
      style={style}
      className={`fixed z-[101] grid gap-3 rounded-xl border bg-popover p-4 text-popover-foreground shadow-xl ${beside ? '' : 'top-1/2 left-1/2 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2'}`}
    >
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Step {index + 1} of {total}
        </span>
        <button type="button" className="underline hover:text-foreground" onClick={onSkip}>
          Skip tour
        </button>
      </div>
      <h2 id="tour-title" className="text-base font-semibold">
        {step.title}
      </h2>
      <p id="tour-body" className="text-sm leading-relaxed text-muted-foreground">
        {step.body}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1" aria-hidden>
          {Array.from({ length: total }, (_, i) => (
            <span key={i} className={`size-1.5 rounded-full ${i === index ? 'bg-primary' : 'bg-muted-foreground/30'}`} />
          ))}
        </div>
        <div className="flex gap-2">
          {step.cta && (
            <Button type="button" size="sm" variant="outline" onClick={() => onCta(step.cta!.to)}>
              {step.cta.label}
            </Button>
          )}
          {index > 0 && (
            <Button type="button" size="sm" variant="ghost" onClick={onBack}>
              Back
            </Button>
          )}
          <Button ref={next} type="button" size="sm" onClick={onNext}>
            {last ? 'Done' : 'Next'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function TourOverlay({ index, setIndex, close }: { index: number; setIndex: (i: number) => void; close: () => void }) {
  const navigate = useNavigate()
  const step = TOUR_STEPS[index]
  const [box, setBox] = useState<Box | null>(null)

  useLayoutEffect(() => {
    const update = () => setBox(measure(step.target))
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [step])

  const go = useCallback((i: number) => (i >= TOUR_STEPS.length ? close() : setIndex(Math.max(0, i))), [close, setIndex])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowRight') go(index + 1)
      else if (e.key === 'ArrowLeft') go(index - 1)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [go, close, index])

  return createPortal(
    <div data-testid="tour">
      {/* the dimmed page; the hole around the target is a box-shadow so clicks cannot reach the page underneath */}
      {box ? (
        <div
          aria-hidden
          className="pointer-events-none fixed z-[100] rounded-lg ring-2 ring-primary transition-all duration-200"
          style={{ top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2, boxShadow: '0 0 0 100vmax rgb(0 0 0 / 0.55)' }}
        />
      ) : (
        <div aria-hidden className="fixed inset-0 z-[100] bg-black/55" />
      )}
      <div aria-hidden className="fixed inset-0 z-[100]" onClick={(e) => e.stopPropagation()} />
      <TourCard
        step={step}
        index={index}
        total={TOUR_STEPS.length}
        box={box}
        onBack={() => go(index - 1)}
        onNext={() => go(index + 1)}
        onSkip={close}
        onCta={(to) => {
          close()
          navigate(to)
        }}
      />
    </div>,
    document.body,
  )
}

/** Opens the tour by itself on the first visit; `useTour().start()` (the sidebar button) replays it. */
export function TourProvider({ children }: { children: ReactNode }) {
  const [index, setIndex] = useState<number | null>(null)
  useEffect(() => {
    if (seen()) return
    const t = setTimeout(() => setIndex(0), 600)
    return () => clearTimeout(t)
  }, [])
  const close = useCallback(() => {
    markSeen()
    setIndex(null)
  }, [])
  const value = useMemo(() => ({ start: () => setIndex(0) }), [])
  return (
    <TourContext.Provider value={value}>
      {children}
      {index !== null && <TourOverlay index={index} setIndex={setIndex} close={close} />}
    </TourContext.Provider>
  )
}

export function TourButton({ onStart }: { onStart?: () => void }) {
  const { start } = useTour()
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="w-full justify-start gap-2 text-sidebar-foreground/80"
      onClick={() => {
        onStart?.()
        start()
      }}
    >
      <CircleHelp aria-hidden /> Take the tour
    </Button>
  )
}
