import {
  Briefcase, Car, Clapperboard, Gift, HeartPulse, House, Laptop, Receipt, ShoppingBag, Tag, Utensils,
} from 'lucide-react'

// iOS system colours (work in light and dark mode)
export const SYSTEM = {
  blue: '#0a84ff', green: '#30c759', orange: '#ff9500', red: '#ff3b30', purple: '#af52de',
  pink: '#ff2d55', teal: '#30b0c7', indigo: '#5856d6', yellow: '#ffcc00', mint: '#00c7be', gray: '#8e8e93',
}

const KNOWN = {
  food: { Icon: Utensils, color: SYSTEM.orange },
  rent: { Icon: House, color: SYSTEM.indigo },
  transport: { Icon: Car, color: SYSTEM.blue },
  shopping: { Icon: ShoppingBag, color: SYSTEM.pink },
  bills: { Icon: Receipt, color: SYSTEM.teal },
  entertainment: { Icon: Clapperboard, color: SYSTEM.purple },
  health: { Icon: HeartPulse, color: SYSTEM.red },
  salary: { Icon: Briefcase, color: SYSTEM.green },
  freelance: { Icon: Laptop, color: SYSTEM.mint },
  gifts: { Icon: Gift, color: SYSTEM.pink },
  other: { Icon: Tag, color: SYSTEM.gray },
}

const PALETTE = [SYSTEM.blue, SYSTEM.orange, SYSTEM.green, SYSTEM.purple, SYSTEM.pink, SYSTEM.teal, SYSTEM.indigo, SYSTEM.mint]

// Icon + colour for a category. Custom categories get a tag icon and a stable colour from their name.
export function categoryMeta(name = '') {
  const key = name.trim().toLowerCase()
  if (KNOWN[key]) return KNOWN[key]
  let hash = 0
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) | 0
  return { Icon: Tag, color: PALETTE[Math.abs(hash) % PALETTE.length] }
}
