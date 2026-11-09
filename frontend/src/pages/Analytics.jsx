import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { Activity, ArrowDownLeft, ArrowUpRight, ReceiptText, Scale, TrendingUp } from 'lucide-react'
import api, { errorMessage } from '../api'
import { categoryMeta, SYSTEM } from '../categories'
import { formatMoney, currentMonth, monthLabel } from '../format'

function shiftMonth(month, delta) {
  const [year, mon] = month.split('-').map(Number)
  const value = year * 12 + mon - 1 + delta
  return `${Math.floor(value / 12)}-${String(value % 12 + 1).padStart(2, '0')}`
}

const Metric = ({ label, value, Icon, color, hint }) => (
  <div className="card stat">
    <span className="stat-label">
      <span className="stat-dot" style={{ background: color }}><Icon size={14} /></span>
      {label}
    </span>
    <strong>{value}</strong>
    {hint && <span className="muted small-text">{hint}</span>}
  </div>
)

export default function Analytics() {
  const endDefault = currentMonth()
  const [startMonth, setStartMonth] = useState(shiftMonth(endDefault, -5))
  const [endMonth, setEndMonth] = useState(endDefault)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!startMonth || !endMonth || startMonth > endMonth) {
      setData(null)
      setError('Choose a valid date range. The start month must not be after the end month.')
      setLoading(false)
      return
    }
    const count = (Number(endMonth.slice(0, 4)) - Number(startMonth.slice(0, 4))) * 12
      + Number(endMonth.slice(5)) - Number(startMonth.slice(5)) + 1
    if (count > 24) {
      setData(null)
      setError('Choose a range of 24 months or less.')
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    api.get('/dashboard/analytics', { params: { start_month: startMonth, end_month: endMonth } })
      .then((response) => !cancelled && setData(response.data))
      .catch((err) => !cancelled && setError(errorMessage(err)))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [startMonth, endMonth])

  const monthly = (data?.monthly || []).map((point) => ({
    ...point,
    label: monthLabel(point.month).split(' ')[0],
  }))
  const categories = (data?.by_category || []).map((item) => ({
    ...item,
    color: categoryMeta(item.category).color,
  }))

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="large-title">Analytics</h1>
          <p className="muted">Explore your income and spending patterns</p>
        </div>
        <div className="actions analytics-range">
          <label className="small-text muted">From <input aria-label="Start month" type="month" value={startMonth}
            max={endMonth} onChange={(e) => setStartMonth(e.target.value)} /></label>
          <label className="small-text muted">To <input aria-label="End month" type="month" value={endMonth}
            min={startMonth} onChange={(e) => setEndMonth(e.target.value)} /></label>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Calculating your analytics…</p>}
      {!loading && data && (
        <>
          <div className="stats">
            <Metric label="Total income" value={formatMoney(data.income)} Icon={ArrowDownLeft} color={SYSTEM.green} />
            <Metric label="Total expenses" value={formatMoney(data.expenses)} Icon={ArrowUpRight} color={SYSTEM.red}
              hint={`Average ${formatMoney(data.average_monthly_expenses)} / month`} />
            <Metric label="Net balance" value={formatMoney(data.balance)} Icon={Scale} color={SYSTEM.blue} />
            <Metric label="Savings rate" value={`${data.savings_rate}%`} Icon={TrendingUp} color={SYSTEM.purple} />
          </div>

          <div className="summary-strip analytics-summary">
            <div><span>Transactions</span><strong>{data.transaction_count}</strong></div>
            <div><span>Period</span><strong>{data.monthly.length} months</strong></div>
            <div><span>Average monthly expenses</span><strong>{formatMoney(data.average_monthly_expenses)}</strong></div>
          </div>

          <div className="grid-2 analytics-charts">
            <div className="card">
              <div className="card-title"><h3><Activity size={18} />Monthly cash flow</h3></div>
              {monthly.every((m) => !m.income && !m.expenses) ? <p className="empty">No transactions in this period.</p> : (
                <ResponsiveContainer width="100%" height={290}>
                  <BarChart data={monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--separator)" />
                    <XAxis dataKey="label" axisLine={false} tickLine={false} />
                    <YAxis axisLine={false} tickLine={false} width={52} tickFormatter={(v) => new Intl.NumberFormat('en-IN', { notation: 'compact' }).format(v)} />
                    <Tooltip formatter={(v) => formatMoney(v)} />
                    <Legend iconType="circle" iconSize={8} />
                    <Bar dataKey="income" name="Income" fill={SYSTEM.green} radius={[5, 5, 0, 0]} />
                    <Bar dataKey="expenses" name="Expenses" fill={SYSTEM.red} radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="card">
              <div className="card-title"><h3>Expense by category</h3></div>
              {categories.length === 0 ? <p className="empty">No expenses in this period.</p> : (
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height={290}>
                    <PieChart>
                      <Pie data={categories} dataKey="total" nameKey="category" innerRadius={68} outerRadius={102}
                        paddingAngle={2} stroke="none">
                        {categories.map((item) => <Cell key={item.category} fill={item.color} />)}
                      </Pie>
                      <Tooltip formatter={(v) => formatMoney(v)} />
                      <Legend iconType="circle" iconSize={8} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-title"><h3>Category breakdown</h3></div>
              {categories.length === 0 ? <p className="muted">No expense categories to show.</p> : (
                <div className="analytics-category-list">
                  {categories.map((item) => (
                    <div className="analytics-category" key={item.category}>
                      <span className="analytics-category-dot" style={{ background: item.color }} />
                      <span className="row-main">{item.category}</span>
                      <strong>{formatMoney(item.total)}</strong>
                      <span className="muted small-text">{data.expenses ? Math.round(item.total / data.expenses * 100) : 0}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="card">
              <div className="card-title"><h3><ReceiptText size={18} />Largest expense</h3></div>
              {data.top_expense ? (
                <div className="analytics-top-expense">
                  <strong>{formatMoney(data.top_expense.amount)}</strong>
                  <span>{data.top_expense.merchant}</span>
                  <span className="muted small-text">{data.top_expense.category} · {new Date(data.top_expense.date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                </div>
              ) : <p className="muted">No expenses in this period.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
