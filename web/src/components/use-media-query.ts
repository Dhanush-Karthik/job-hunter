import { useSyncExternalStore } from 'react'

/** Subscribes to a media query. Without matchMedia (jsdom) it reports `fallback`. */
export function useMediaQuery(query: string, fallback = true) {
  return useSyncExternalStore(
    (notify) => {
      if (typeof window.matchMedia !== 'function') return () => {}
      const mq = window.matchMedia(query)
      mq.addEventListener('change', notify)
      return () => mq.removeEventListener('change', notify)
    },
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : fallback),
    () => fallback,
  )
}
