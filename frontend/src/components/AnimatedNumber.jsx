import { useEffect } from 'react'
import { motion, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { springs } from '../motion'

// Shows a number that springs from its previous value to the new one (e.g. when the month changes).
// It starts at the real value on first render, so it never counts up from 0.
export default function AnimatedNumber({ value, format, className }) {
  const reduce = useReducedMotion()
  const mv = useSpring(value, springs.value)
  useEffect(() => {
    if (reduce) mv.jump(value)
    else mv.set(value)
  }, [value, reduce, mv])
  const text = useTransform(mv, format)
  return <motion.strong className={className}>{text}</motion.strong>
}
