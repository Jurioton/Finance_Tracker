import { useEffect, useLayoutEffect, useRef } from 'react'
import { animate, motion, useIsPresent, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { FLING_VELOCITY, project, rubberBand, springs, useMediaQuery } from '../motion'

const DRAG_START = 10 // px of movement before a press on the sheet header becomes a drag

// Every form in the app opens in this component.
// Desktop: a dialog that grows out of the button that opened it (`origin`) and shrinks back into it.
// Phone: a bottom sheet you can drag down (or fling) to dismiss.
// Must be rendered inside <AnimatePresence> so the exit animation can play.
export default function Modal({ title, onClose, children, origin }) {
  const isSheet = useMediaQuery('(max-width: 640px)')
  const reduce = useReducedMotion()
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  useLayoutEffect(() => { onCloseRef.current = onClose })

  useDialogFocus(panelRef, onCloseRef)

  // While closing, let clicks fall through to the page so nothing waits on the animation
  const isPresent = useIsPresent()
  const props = { title, children, panelRef, reduce, onClose: () => onCloseRef.current() }
  return (
    <div className={`modal-root${isSheet ? ' sheet' : ''}${isPresent ? '' : ' leaving'}`}>
      {isSheet ? <Sheet {...props} /> : <Dialog {...props} origin={origin} />}
    </div>
  )
}

function Header({ title, onClose, ...rest }) {
  return (
    <div className="modal-header" {...rest}>
      <h3>{title}</h3>
      <button className="btn ghost" onClick={onClose} aria-label="Close">✕</button>
    </div>
  )
}

function Dialog({ title, children, onClose, origin, panelRef, reduce }) {
  // Start (and end) at the trigger button's position, scaled down and blurred
  const hidden = (() => {
    if (reduce) return { opacity: 0 }
    const from = origin
      ? { x: origin.left + origin.width / 2 - window.innerWidth / 2, y: origin.top + origin.height / 2 - window.innerHeight / 2 }
      : { x: 0, y: 24 }
    return { ...from, scale: 0.5, opacity: 0, filter: 'blur(8px)' }
  })()
  const shown = reduce ? { opacity: 1 } : { x: 0, y: 0, scale: 1, opacity: 1, filter: 'blur(0px)' }
  const transition = reduce ? springs.fade : springs.sheet

  return (
    <>
      <motion.div className="modal-scrim" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={transition} />
      <motion.div ref={panelRef} className="modal" role="dialog" aria-modal="true" aria-label={title}
        initial={hidden} animate={shown} exit={hidden} transition={transition}>
        <Header title={title} onClose={onClose} />
        {children}
      </motion.div>
    </>
  )
}

function Sheet({ title, children, onClose, panelRef, reduce }) {
  const offscreen = typeof window === 'undefined' ? 1000 : window.innerHeight
  const y = useMotionValue(reduce ? 0 : offscreen)
  const height = useRef(offscreen)
  const drag = useRef(null)

  // The scrim follows the sheet: half dragged down = half dimmed
  const scrimOpacity = useTransform(y, (v) => Math.min(1, Math.max(0, 1 - v / height.current)))

  useLayoutEffect(() => {
    height.current = panelRef.current?.offsetHeight || offscreen
    if (!reduce) {
      const a = animate(y, 0, springs.sheet)
      return () => a.stop()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onPointerDown = (e) => {
    if (e.button !== 0 || e.target.closest('button')) return
    y.stop() // grab it mid-flight: it stays exactly under the finger
    e.currentTarget.setPointerCapture(e.pointerId) // keep getting moves even when the pointer leaves the header
    drag.current = { id: e.pointerId, startY: e.clientY, startValue: y.get(), active: false }
  }

  const onPointerMove = (e) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    if (!d.active) {
      if (Math.abs(e.clientY - d.startY) < DRAG_START) return
      d.active = true
      d.startY = e.clientY // start tracking from here so the sheet doesn't jump by the threshold
    }
    const raw = d.startValue + (e.clientY - d.startY)
    y.set(raw < 0 ? rubberBand(raw, height.current) : raw)
  }

  const onPointerUp = (e) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    drag.current = null
    const velocity = d.active ? y.getVelocity() : 0

    if (d.active && project(y.get(), velocity) > height.current / 2) {
      if (reduce) y.set(offscreen)
      else animate(y, offscreen, { ...springs.sheet, velocity })
      onClose()
      return
    }
    // Settle back open (also resumes an entrance that was tapped mid-flight)
    if (reduce) y.set(0)
    else animate(y, 0, { ...(Math.abs(velocity) > FLING_VELOCITY ? springs.fling : springs.sheet), velocity })
  }

  const scrim = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: springs.fade }
    : { style: { opacity: scrimOpacity } }
  const panel = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: springs.fade }
    : { exit: { y: offscreen }, transition: springs.sheet } // exit starts from the live value and velocity

  return (
    <>
      <motion.div className="modal-scrim" onClick={onClose} {...scrim} />
      <motion.div ref={panelRef} className="modal sheet" role="dialog" aria-modal="true" aria-label={title}
        style={{ y }} {...panel}>
        <div className="sheet-grab" onPointerDown={onPointerDown} onPointerMove={onPointerMove}
          onPointerUp={onPointerUp} onPointerCancel={onPointerUp}>
          <div className="sheet-handle" aria-hidden="true" />
          <Header title={title} onClose={onClose} />
        </div>
        {children}
      </motion.div>
    </>
  )
}

// Esc closes, Tab stays inside, the first field gets focus while the panel is still arriving,
// and focus goes back to the button that opened it afterwards.
function useDialogFocus(panelRef, onCloseRef) {
  useEffect(() => {
    const opener = document.activeElement
    const fields = 'input:not([type=hidden]), select, textarea'
    const focusable = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

    // ~80% of the way through the 0.3s spring, so typing can start before it fully settles
    const timer = setTimeout(() => {
      const panel = panelRef.current
      if (panel && !panel.contains(document.activeElement)) panel.querySelector(fields)?.focus({ preventScroll: true })
    }, 240)

    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onCloseRef.current(); return }
      if (e.key !== 'Tab' || !panelRef.current) return
      const items = [...panelRef.current.querySelectorAll(focusable)].filter((el) => !el.disabled)
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('keydown', onKey)
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}
