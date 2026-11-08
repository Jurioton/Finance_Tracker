import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api'
import Modal from '../components/Modal'
import ProgressBar from '../components/ProgressBar'
import { formatDate, formatMoney } from '../format'

export default function Goals() {
  const [goals, setGoals] = useState([])
  const [editing, setEditing] = useState(null)
  const [contributing, setContributing] = useState(null)
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
        <h1>Savings goals</h1>
        <button className="btn primary" onClick={() => setEditing({})}>+ New goal</button>
      </div>
      {error && <p className="error">{error}</p>}

      {goals.length === 0 ? (
        <div className="card"><p className="muted">No goals yet. Create one, like "Emergency fund" or "New laptop".</p></div>
      ) : (
        <div className="grid-3">
          {goals.map((g) => (
            <div key={g.id} className={`card goal ${g.completed ? 'done' : ''}`}>
              <div className="page-header">
                <h3>{g.name}</h3>
                {g.completed && <span className="badge ok">🎉 Reached</span>}
              </div>
              <p><strong>{formatMoney(g.saved_amount)}</strong> <span className="muted">of {formatMoney(g.target_amount)}</span></p>
              <ProgressBar percent={g.percent} />
              <p className="muted">
                {g.percent}% · {formatMoney(g.remaining)} to go
                {g.deadline && <> · by {formatDate(g.deadline)}</>}
              </p>
              {g.monthly_needed && <p className="hint">Save about {formatMoney(g.monthly_needed)} a month to reach it on time.</p>}
              <div className="actions">
                {!g.completed && <button className="btn small primary" onClick={() => setContributing(g)}>+ Add money</button>}
                <button className="btn ghost small" onClick={() => setEditing(g)}>Edit</button>
                <button className="btn ghost small danger" onClick={() => remove(g)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && <GoalForm initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {contributing && (
        <ContributeForm goal={contributing} onClose={() => setContributing(null)} onSaved={() => { setContributing(null); load() }} />
      )}
    </div>
  )
}

function GoalForm({ initial, onClose, onSaved }) {
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
    <Modal title={initial.id ? 'Edit goal' : 'New goal'} onClose={onClose}>
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
        <button className="btn primary">Save</button>
      </form>
    </Modal>
  )
}

function ContributeForm({ goal, onClose, onSaved }) {
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
    <Modal title={`Add money to "${goal.name}"`} onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label>Amount
          <input type="number" min="0.01" step="0.01" required autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary">Add</button>
      </form>
    </Modal>
  )
}
