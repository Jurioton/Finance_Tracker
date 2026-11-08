import { motion } from 'motion/react'
import { springs } from '../motion'

// Activity-style progress ring. Springs from its previous value; never past 100%.
export default function Ring({ percent, color = 'var(--blue)', size = 64, stroke = 8, children }) {
  const pct = Math.max(0, Math.min(percent || 0, 100)) / 100
  const r = (size - stroke) / 2
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={`${Math.round(pct * 100)}%`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeOpacity={0.18} strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`}
          initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: pct, opacity: pct > 0 ? 1 : 0 }} transition={springs.value} />
      </svg>
      {children && <div className="ring-label">{children}</div>}
    </div>
  )
}
