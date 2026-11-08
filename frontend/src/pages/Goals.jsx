import { useEffect, useState } from 'react'
import { AnimatePresence } from 'motion/react'
import { CalendarDays, Pencil, Plus, Target, Trash2 } from 'lucide-react'
import { SYSTEM } from '../categories'
import Ring from '../components/Ring'
import api, { errorMessage } from '../api'
import Modal from '../components/Modal'
import { formatDate, formatMoney } from '../format'
import { originOf } from '../motion'

export default function Goals() {
  const [goals, setGoals] = useState([])
  const [editing, setEditing] = useState(null)
  const [contributing, setContributing] = useState(null)
  const [origin, setOrigin] = useState(null)
  const [error, setError] = useState('')

  const load = () => api.get('/goals').then((r) => setGoals(r.data)).catch((e) => setError(errorMessage(e)))
  useEffect(() => { load() }, [])

  const remove = async (g) => {
    if (!confirm(`Delete the goal "${g.name}"?`)) return
    await api.delete(`/goals/${g.id}`)
    load()
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="large-title">Goals</h1>
        <button className="btn primary" onClick={(e) => { setOrigin(originOf(e)); setEditing({}) }}><Plus size={17} strokeWidth={2.5} />New goal</button>
      </div>
      {error && <p className="error">{error}</p>}

      {goals.length === 0 ? (
        <div className="card empty">
          <Target size={40} strokeWidth={1.5} />
          <p>No goals yet. Create one, like "Emergency fund" or "New laptop".</p>
        </div>
      ) : (
        <div className="grid-3">
          {goals.map((g) => (
            <div key={g.id} className="card goal-card">
              <div className="row-between">
                <h3>{g.name}</h3>
                {g.completed && <span className="badge ok">Reached</span>}
              </div>
              <div className="goal-top">
                <Ring percent={g.percent} size={76} stroke={9} color={g.completed ? SYSTEM.green : SYSTEM.blue}>
                  {Math.round(g.percent)}%
                </Ring>
                <div>
                  <div className="amount">{formatMoney(g.saved_amount)}</div>
                  <span className="muted small-text">of {formatMoney(g.target_amount)} · {formatMoney(g.remaining)} to go</span>
                  {g.deadline && (
                    <div className="muted small-text" style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                      <CalendarDays size={13} />by {formatDate(g.deadline)}
                    </div>
                  )}
                </div>
              </div>
              {g.monthly_needed && <p className="hint">Save about {formatMoney(g.monthly_needed)} a month to reach it on time.</p>}
              <div className="card-actions">
                {!g.completed && (
                  <button className="btn small primary" onClick={(e) => { setOrigin(originOf(e)); setContributing(g) }}>
                    <Plus size={14} strokeWidth={2.5} />Add money
                  </button>
                )}
                <span style={{ flex: 1 }} />
                <button className="icon-btn" aria-label="Edit" onClick={(e) => { setOrigin(originOf(e)); setEditing(g) }}><Pencil size={14} /></button>
                <button className="icon-btn danger" aria-label="Delete" onClick={() => remove(g)}><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {editing && <GoalForm key="goal-form" origin={origin} initial={editing}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      </AnimatePresence>
      <AnimatePresence>
        {contributing && (
          <ContributeForm key="contribute-form" origin={origin} goal={contributing}
            onClose={() => setContributing(null)} onSaved={() => { setContributing(null); load() }} />
        )}
      </AnimatePresence>
    </div>
  )
}

function GoalForm({ initial, origin, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: initial.name || '',
    target_amount: initial.target_amount || '',
    saved_amount: initial.saved_amount ?? 0,
    deadline: initial.deadline || '',
  })
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    const body = {
      ...form,
      target_amount: Number(form.target_amount),
      saved_amount: Number(form.saved_amount),
      deadline: form.deadline || null,
    }
    try {
      if (initial.id) await api.put(`/goals/${initial.id}`, body)
      else await api.post('/goals', body)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Modal title={initial.id ? 'Edit goal' : 'New goal'} origin={origin} onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label>Name
          <input required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>Target amount
          <input type="number" min="1" step="0.01" required value={form.target_amount}
            onChange={(e) => setForm({ ...form, target_amount: e.target.value })} />
        </label>
        <label>Already saved
          <input type="number" min="0" step="0.01" value={form.saved_amount}
            onChange={(e) => setForm({ ...form, saved_amount: e.target.value })} />
        </label>
        <label>Deadline (optional)
          <input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary block">Save</button>
      </form>
    </Modal>
  )
}

function ContributeForm({ goal, origin, onClose, onSaved }) {
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post(`/goals/${goal.id}/contribute`, { amount: Number(amount) })
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Modal title={`Add money to "${goal.name}"`} origin={origin} onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label>Amount
          <input type="number" min="0.01" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary block">Add</button>
      </form>
    </Modal>
  )
}
