import { motion } from 'motion/react'
import { springs } from '../motion'

// The fill is full width and slides in from the left (transform only, keeps its rounded end).
// When the value changes, it springs from wherever it is now, never past the target.
export default function ProgressBar({ percent, status = 'ok' }) {
  const pct = Math.max(0, Math.min(percent, 100))
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <motion.div className={`progress-fill ${status}`}
        initial={{ x: '-100%' }} animate={{ x: `${pct - 100}%` }} transition={springs.value} />
    </div>
  )
}
