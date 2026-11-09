import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'motion/react'
import { Activity, ArrowLeftRight, LayoutGrid, LogOut, PieChart, Target, Wallet } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { springs } from '../motion'

const links = [
  { to: '/', label: 'Dashboard', Icon: LayoutGrid },
  { to: '/transactions', label: 'Transactions', Icon: ArrowLeftRight },
  { to: '/analytics', label: 'Analytics', Icon: Activity },
  { to: '/budgets', label: 'Budgets', Icon: PieChart },
  { to: '/goals', label: 'Goals', Icon: Target },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const current = links.find((l) => l.to === pathname) || links[0]

  const { scrollY } = useScroll()
  const compactOpacity = useTransform(scrollY, [24, 56], [0, 1])

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <span className="app-icon"><Wallet size={17} strokeWidth={2.4} /></span>
          <span>Finance</span>
        </span>

        <nav className="segmented" aria-label="Main">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === '/'}>
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="nav-pill" className="segment-pill" transition={springs.pill} />}
                  <span className="segment-label">{l.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <motion.span className="compact-title" style={{ opacity: compactOpacity }} aria-hidden="true">
          {current.label}
        </motion.span>

        <div className="user">
          <span className="user-name">{user?.name}</span>
          <span className="avatar" title={user?.name}>{user?.name?.[0]?.toUpperCase()}</span>
          <button className="icon-btn" onClick={logout} aria-label="Log out" title="Log out"><LogOut size={15} /></button>
        </div>
      </header>

      <main className="content">
        <Outlet />
      </main>

      <nav className="tabbar" aria-label="Main">
        {links.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to} end={to === '/'}>
            <Icon size={22} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
