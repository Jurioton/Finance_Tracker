import { useEffect, useState } from 'react'
import { AnimatePresence } from 'motion/react'
import { Pencil, PieChart, Plus, Trash2 } from 'lucide-react'
import { SYSTEM } from '../categories'
import CategoryIcon from '../components/CategoryIcon'
import Ring from '../components/Ring'
import api, { errorMessage } from '../api'
import Modal from '../components/Modal'
import ProgressBar from '../components/ProgressBar'
import { currentMonth, formatMoney, monthLabel } from '../format'
import { originOf } from '../motion'

const STATUS_TEXT = { ok: 'On track', warning: 'Over 80% used', over: 'Over budget' }

export default function Budgets() {
  const [month, setMonth] = useState(currentMonth())
  const [budgets, setBudgets] = useState([])
  const [categories, setCategories] = useState([])
  const [editing, setEditing] = useState(null)
  const [origin, setOrigin] = useState(null)
  const [error, setError] = useState('')

  const load = () =>
    api.get('/budgets', { params: { month } }).then((r) => setBudgets(r.data)).catch((e) => setError(errorMessage(e)))

  useEffect(() => { api.get('/categories', { params: { type: 'expense' } }).then((r) => setCategories(r.data)) }, [])
  useEffect(() => { load() }, [month]) // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async (b) => {
    if (!confirm(`Delete the ${b.category.name} budget?`)) return
    await api.delete(`/budgets/${b.id}`)
    load()
  }

  const totalLimit = budgets.reduce((s, b) => s + b.limit, 0)
  const totalSpent = budgets.reduce((s, b) => s + b.spent, 0)
  const unbudgeted = categories.filter((c) => !budgets.some((b) => b.category.id === c.id))

  return (
    <div>
      <div className="page-header">
        <h1 className="large-title">Budgets</h1>
        <div className="actions">
          <input type="month" aria-label="Month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          <button className="btn primary" disabled={!unbudgeted.length} onClick={(e) => { setOrigin(originOf(e)); setEditing({}) }}><Plus size={17} strokeWidth={2.5} />Add</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {budgets.length > 0 && (
        <div className="card overview">
          <Ring percent={totalLimit ? (totalSpent / totalLimit) * 100 : 0} size={88} stroke={11}
            color={totalSpent >= totalLimit ? SYSTEM.red : totalSpent >= totalLimit * 0.8 ? SYSTEM.orange : SYSTEM.green}>
            {totalLimit ? Math.round((totalSpent / totalLimit) * 100) : 0}%
          </Ring>
          <div>
            <span className="muted small-text">{monthLabel(month)}</span>
            <div className="big">{formatMoney(totalSpent)}</div>
            <span className="muted">spent of {formatMoney(totalLimit)} budgeted</span>
          </div>
        </div>
      )}

      {budgets.length === 0 ? (
        <div className="card empty">
          <PieChart size={40} strokeWidth={1.5} />
          <p>No budgets for {monthLabel(month)}. Set a monthly limit for a category to get alerts.</p>
        </div>
      ) : (
        <div className="grid-3">
          {budgets.map((b) => (
            <div key={b.category.id} className="card budget-card">
              <div className="meter-head">
                <CategoryIcon name={b.category.name} size={32} />
                <h3 className="row-main">{b.category.name}</h3>
                <span className={`badge ${b.status}`}>{STATUS_TEXT[b.status]}</span>
              </div>
              <p style={{ marginTop: '0.8rem' }}><span className="amount">{formatMoney(b.spent)}</span> <span className="muted">of {formatMoney(b.limit)}</span></p>
              <ProgressBar percent={b.percent} status={b.status} />
              <div className="row-between">
                <span className="muted small-text">
                  {b.limit - b.spent >= 0 ? `${formatMoney(b.limit - b.spent)} left` : `${formatMoney(b.spent - b.limit)} over`} · {b.percent}%
                </span>
                <span className="actions">
                  <button className="icon-btn" aria-label="Edit" onClick={(e) => { setOrigin(originOf(e)); setEditing(b) }}><Pencil size={14} /></button>
                  <button className="icon-btn danger" aria-label="Delete" onClick={() => remove(b)}><Trash2 size={14} /></button>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <AnimatePresence>
      {editing && (
        <BudgetForm key="budget-form" origin={origin} initial={editing} month={month} categories={unbudgeted}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />
      )}
      </AnimatePresence>
    </div>
  )
}

function BudgetForm({ initial, month, categories, origin, onClose, onSaved }) {
  const [form, setForm] = useState({ category_id: '', limit: initial.limit || '' })
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    try {
      if (initial.id) await api.put(`/budgets/${initial.id}`, { limit: Number(form.limit) })
      else await api.post('/budgets', { category_id: Number(form.category_id), limit: Number(form.limit), month })
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Modal title={initial.id ? `Edit ${initial.category.name} budget` : `New budget for ${monthLabel(month)}`} origin={origin} onClose={onClose}>
      <form onSubmit={submit} className="form">
        {!initial.id && (
          <label>Category
            <select required value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
              <option value="">Choose…</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        )}
        <label>Monthly limit
          <input type="number" min="1" step="0.01" required value={form.limit}
            onChange={(e) => setForm({ ...form, limit: e.target.value })} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary block">Save</button>
      </form>
    </Modal>
  )
}
