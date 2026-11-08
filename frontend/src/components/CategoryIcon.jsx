import { categoryMeta } from '../categories'

// Round coloured badge with the category's icon, like iOS settings rows
export default function CategoryIcon({ name, size = 36 }) {
  const { Icon, color } = categoryMeta(name)
  return (
    <span className="cat-icon" style={{ background: color, width: size, height: size }} aria-hidden="true">
      <Icon size={Math.round(size * 0.5)} strokeWidth={2.25} color="#fff" />
    </span>
  )
}
