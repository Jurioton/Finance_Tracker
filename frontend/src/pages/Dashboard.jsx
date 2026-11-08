import { useEffect, useState } from 'react'
import { useReducedMotion } from 'motion/react'
import { Link } from 'react-router-dom'
import { ArrowDownLeft, ArrowUpRight, ChevronRight, PiggyBank, Scale, TriangleAlert } from 'lucide-react'
import {
  CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import api, { errorMessage } from '../api'
import { categoryMeta, SYSTEM } from '../categories'
import AnimatedNumber from '../components/AnimatedNumber'
import CategoryIcon from '../components/CategoryIcon'
import Insights from '../components/Insights'
import ProgressBar from '../components/ProgressBar'
import Ring from '../components/Ring'
import { currentMonth, formatMoney, monthLabel } from '../format'

const compactMoney = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })

export default function Dashboard() {
  const [month, setMonth] = useState(currentMonth())
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState([])
  const [goals, setGoals] = useState([])
  const [error, setError] = useState('')
  const reduce = useReducedMotion()
  // Short chart tweens, none at all with reduced motion
  const chartAnim = { isAnimationActive: !reduce, animationDuration: 400 }

  useEffect(() => {
    Promise.all([
      api.get('/dashboard/summary', { params: { month } }),
      api.get('/dashboard/trends', { params: { months: 6, end_month: month } }),
      api.get('/goals'),
    ])
      .then(([s, t, g]) => {
        setSummary(s.data)
        setTrends(t.data.map((p) => ({ ...p, label: monthLabel(p.month).split(' ')[0] })))
        setGoals(g.data.filter((goal) => !goal.completed).slice(0, 3))
      })
      .catch((err) => setError(errorMessage(err)))
  }, [month])

  if (error) return <p className="error">{error}</p>
  if (!summary) return <p className="muted">Loading…</p>

  return (
    <div>
      <div className="page-header">
        <h1 className="large-title">Summary</h1>
        <input type="month" aria-label="Month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
      </div>

      <div className="stats">
        <Stat label="Income" Icon={ArrowDownLeft} color={SYSTEM.green} value={summary.income} format={formatMoney} tone="income" />
        <Stat label="Expenses" Icon={ArrowUpRight} color={SYSTEM.red} value={summary.expenses} format={formatMoney} />
        <Stat label="Balance" Icon={Scale} color={SYSTEM.blue} value={summary.balance} format={formatMoney}
          tone={summary.balance >= 0 ? '' : 'expense'} />
        <Stat label="Savings rate" Icon={PiggyBank} color={SYSTEM.purple} value={summary.savings_rate} format={formatPercent} />
      </div>

      <Insights month={month} />

      {summary.budget_alerts.length > 0 && (
        <div className="card alerts">
          <div className="card-title">
            <h3><TriangleAlert size={18} color={SYSTEM.orange} />Budget alerts</h3>
            <Link to="/budgets" className="small-text">Budgets</Link>
          </div>
          {summary.budget_alerts.map((b) => (
            <div key={b.category.id} className="alert-row">
              <div className="meter-head">
                <CategoryIcon name={b.category.name} size={28} />
                <div className="row-main">
                  <strong>{b.category.name}</strong>
                  <div className="muted small-text">{formatMoney(b.spent)} of {formatMoney(b.limit)}</div>
                </div>
                <span className={`badge ${b.status}`}>{b.status === 'over' ? 'Over budget' : `${b.percent}% used`}</span>
              </div>
              <ProgressBar percent={b.percent} status={b.status} />
            </div>
          ))}
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><h3>Spending</h3><span className="muted small-text">{monthLabel(month)}</span></div>
          {summary.by_category.length === 0 ? (
            <p className="empty">No expenses this month yet. <Link to="/transactions">Add one</Link></p>
          ) : (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={summary.by_category} dataKey="total" nameKey="category" innerRadius={78} outerRadius={104}
                    paddingAngle={2} cornerRadius={6} stroke="none" {...chartAnim}>
                    {summary.by_category.map((c) => <Cell key={c.category} fill={categoryMeta(c.category).color} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatMoney(v)} />
                  <Legend iconType="circle" iconSize={8} />
                </PieChart>
              </ResponsiveContainer>
              <div className="donut-center">
                <span className="muted small-text">Spent</span>
                <strong>{formatMoney(summary.expenses)}</strong>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title"><h3>Income vs expenses</h3><span className="muted small-text">6 months</span></div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trends} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--separator)" />
              <XAxis dataKey="label" axisLine={false} tickLine={false} />
              <YAxis axisLine={false} tickLine={false} width={48} tickFormatter={(v) => compactMoney.format(v)} />
              <Tooltip formatter={(v) => formatMoney(v)} />
              <Legend iconType="circle" iconSize={8} />
              <Line type="monotone" dataKey="income" name="Income" stroke={SYSTEM.green} strokeWidth={3} dot={false} activeDot={{ r: 5 }} {...chartAnim} />
              <Line type="monotone" dataKey="expenses" name="Expenses" stroke={SYSTEM.red} strokeWidth={3} dot={false} activeDot={{ r: 5 }} {...chartAnim} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <h3>Savings goals</h3>
          <Link to="/goals" className="small-text" style={{ display: 'inline-flex', alignItems: 'center' }}>
            See all<ChevronRight size={16} />
          </Link>
        </div>
        {goals.length === 0 ? (
          <p className="muted">No active goals. <Link to="/goals">Create one</Link></p>
        ) : (
          <div className="goal-rings">
            {goals.map((g) => (
              <div key={g.id} className="goal-ring">
                <Ring percent={g.percent} size={64} stroke={8} color={SYSTEM.blue}>{Math.round(g.percent)}%</Ring>
                <div>
                  <strong>{g.name}</strong>
                  <span className="muted small-text">{formatMoney(g.saved_amount)} of {formatMoney(g.target_amount)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const formatPercent = (v) => `${Math.round(v * 10) / 10}%`

// Values spring from last month's number to this month's when the month changes
function Stat({ label, Icon, color, value, format, tone }) {
  return (
    <div className="card stat">
      <span className="stat-label">
        <span className="stat-dot" style={{ background: color }}><Icon size={14} strokeWidth={2.5} /></span>
        {label}
      </span>
      <AnimatedNumber value={value} format={format} className={tone} />
    </div>
  )
}
