import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api'
import Modal from '../components/Modal'
import ProgressBar from '../components/ProgressBar'
import { currentMonth, formatMoney, monthLabel } from '../format'

const STATUS_TEXT = { ok: 'On track', warning: 'Over 80% used', over: 'Over budget' }

export default function Budgets() {
  const [month, setMonth] = useState(currentMonth())
  const [budgets, setBudgets] = useState([])
  const [categories, setCategories] = useState([])
  const [editing, setEditing] = useState(null)
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
        <h1>Budgets</h1>
        <div className="actions">
          <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          <button className="btn primary" disabled={!unbudgeted.length} onClick={() => setEditing({})}>+ Add budget</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {budgets.length > 0 && (
        <div className="card">
          <h3>{monthLabel(month)} overview</h3>
          <p>{formatMoney(totalSpent)} spent of {formatMoney(totalLimit)} budgeted</p>
          <ProgressBar percent={totalLimit ? (totalSpent / totalLimit) * 100 : 0}
            status={totalSpent >= totalLimit ? 'over' : totalSpent >= totalLimit * 0.8 ? 'warning' : 'ok'} />
        </div>
      )}

      {budgets.length === 0 ? (
        <div className="card"><p className="muted">No budgets for {monthLabel(month)}. Set a monthly limit for a category to get alerts.</p></div>
      ) : (
        <div className="grid-3">
          {budgets.map((b) => (
            <div key={b.id} className={`card budget ${b.status}`}>
              <div className="page-header">
                <h3>{b.category.name}</h3>
                <span className={`badge ${b.status}`}>{STATUS_TEXT[b.status]}</span>
              </div>
              <p><strong>{formatMoney(b.spent)}</strong> <span className="muted">of {formatMoney(b.limit)}</span></p>
              <ProgressBar percent={b.percent} status={b.status} />
              <p className="muted">
                {b.limit - b.spent >= 0 ? `${formatMoney(b.limit - b.spent)} left` : `${formatMoney(b.spent - b.limit)} over`} · {b.percent}%
              </p>
              <div className="actions">
                <button className="btn ghost small" onClick={() => setEditing(b)}>Edit</button>
                <button className="btn ghost small danger" onClick={() => remove(b)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <BudgetForm initial={editing} month={month} categories={unbudgeted}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />
      )}
    </div>
  )
}

function BudgetForm({ initial, month, categories, onClose, onSaved }) {
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
    <Modal title={initial.id ? `Edit ${initial.category.name} budget` : `New budget for ${monthLabel(month)}`} onClose={onClose}>
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
        <button className="btn primary">Save</button>
      </form>
    </Modal>
  )
}
