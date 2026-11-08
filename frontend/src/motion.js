import { useSyncExternalStore } from 'react'

// Spring presets shared by the whole app. `visualDuration` + `bounce` roughly map to
// Apple's response + damping (bounce 0 = critically damped, 0.2 ≈ damping 0.8).
export const springs = {
  // Dialog / sheet open and close
  sheet: { type: 'spring', visualDuration: 0.3, bounce: 0 },
  // Sheet settling after a fast fling: a little bounce because the gesture carried momentum
  fling: { type: 'spring', visualDuration: 0.3, bounce: 0.2 },
  // Sliding pills (nav, expense/income toggle)
  pill: { type: 'spring', visualDuration: 0.35, bounce: 0 },
  // Money values and progress bars: never overshoot, a bar must not show 103% on the way to 100%
  value: { type: 'spring', visualDuration: 0.4, bounce: 0 },
  // Reduced motion: a short crossfade instead of movement
  fade: { duration: 0.15, ease: 'linear' },
}

// Fling speed (px/s) above which a settling spring may bounce
export const FLING_VELOCITY = 500

// Where something thrown at `velocity` px/s would come to rest (iOS scroll deceleration rate)
export function project(position, velocity, rate = 0.998) {
  return position + (velocity / 1000) * rate / (1 - rate)
}

// Resistance past an edge: moves less and less the further you pull, never a hard stop
export function rubberBand(overshoot, size, c = 0.55) {
  const sign = Math.sign(overshoot)
  const d = Math.abs(overshoot)
  return sign * (1 - 1 / ((d * c) / size + 1)) * size
}

export function useMediaQuery(query) {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

// Remember where a modal was opened from, so it can grow out of (and shrink back into) its button
export function originOf(event) {
  return event?.currentTarget?.getBoundingClientRect?.() ?? null
}
