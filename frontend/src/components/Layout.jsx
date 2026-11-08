import { NavLink, Outlet } from 'react-router-dom'
import { motion } from 'motion/react'
import { useAuth } from '../AuthContext'
import { springs } from '../motion'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/budgets', label: 'Budgets' },
  { to: '/goals', label: 'Goals' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">💰 Finance Tracker</span>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === '/'}>
              {({ isActive }) => (
                <>
                  {/* One highlight that slides between tabs instead of jumping */}
                  {isActive && <motion.span layoutId="nav-pill" className="nav-pill" transition={springs.pill} />}
                  <span className="nav-label">{l.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="user">
          <span>{user?.name}</span>
          <button className="btn ghost" onClick={logout}>Log out</button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
