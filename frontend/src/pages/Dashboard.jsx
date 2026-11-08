import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import api, { errorMessage } from '../api'
import ProgressBar from '../components/ProgressBar'
import { currentMonth, formatMoney, monthLabel } from '../format'

const COLORS = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#64748b']

export default function Dashboard() {
  const [month, setMonth] = useState(currentMonth())
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState([])
  const [goals, setGoals] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/dashboard/summary', { params: { month } }),
      api.get('/dashboard/trends', { params: { months: 6, end_month: month } }),
      api.get('/goals'),
    ])
      .then(([s, t, g]) => {
        setSummary(s.data)
        setTrends(t.data.map((p) => ({ ...p, label: monthLabel(p.month) })))
        setGoals(g.data.filter((goal) => !goal.completed).slice(0, 3))
      })
      .catch((err) => setError(errorMessage(err)))
  }, [month])

  if (error) return <p className="error">{error}</p>
  if (!summary) return <p className="muted">Loading…</p>

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
      </div>

      <div className="stats">
        <Stat label="Income" value={formatMoney(summary.income)} tone="income" />
        <Stat label="Expenses" value={formatMoney(summary.expenses)} tone="expense" />
        <Stat label="Balance" value={formatMoney(summary.balance)} tone={summary.balance >= 0 ? 'income' : 'expense'} />
        <Stat label="Savings rate" value={`${summary.savings_rate}%`} />
      </div>

      {summary.budget_alerts.length > 0 && (
        <div className="card alerts">
          <h3>⚠️ Budget alerts</h3>
          {summary.budget_alerts.map((b) => (
            <div key={b.id} className="alert-row">
              <span>
                <strong>{b.category.name}</strong>: {formatMoney(b.spent)} of {formatMoney(b.limit)} ({b.percent}%)
                {b.status === 'over' ? ' — over budget!' : ' — getting close'}
              </span>
              <ProgressBar percent={b.percent} status={b.status} />
            </div>
          ))}
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <h3>Spending by category</h3>
          {summary.by_category.length === 0 ? (
            <p className="muted">No expenses this month yet. <Link to="/transactions">Add one</Link></p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={summary.by_category} dataKey="total" nameKey="category" innerRadius={60} outerRadius={100}>
                  {summary.by_category.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => formatMoney(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h3>Income vs expenses (last 6 months)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="label" fontSize={12} />
              <YAxis fontSize={12} width={70} />
              <Tooltip formatter={(v) => formatMoney(v)} />
              <Legend />
              <Line type="monotone" dataKey="income" name="Income" stroke="#10b981" strokeWidth={2} />
              <Line type="monotone" dataKey="expenses" name="Expenses" stroke="#ef4444" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <div className="page-header">
          <h3>Savings goals</h3>
          <Link to="/goals">View all</Link>
        </div>
        {goals.length === 0 ? (
          <p className="muted">No active goals. <Link to="/goals">Create one</Link></p>
        ) : (
          goals.map((g) => (
            <div key={g.id} className="alert-row">
              <span>
                <strong>{g.name}</strong>: {formatMoney(g.saved_amount)} of {formatMoney(g.target_amount)}
              </span>
              <ProgressBar percent={g.percent} />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, tone }) {
  return (
    <div className="card stat">
      <span className="muted">{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  )
}
