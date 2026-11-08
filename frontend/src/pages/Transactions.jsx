import { useCallback, useEffect, useRef, useState } from 'react'
import api, { errorMessage } from '../api'
import Modal from '../components/Modal'
import { formatDate, formatMoney, today } from '../format'

const emptyForm = { type: 'expense', amount: '', date: today(), category_id: '', note: '' }

export default function Transactions() {
  const [transactions, setTransactions] = useState([])
  const [categories, setCategories] = useState([])
  const [filters, setFilters] = useState({ month: '', type: '', category_id: '', search: '' })
  const [editing, setEditing] = useState(null) // null = closed, {} = new, {id,...} = edit
  const [showCategory, setShowCategory] = useState(false)
  const [error, setError] = useState('')

  // Only send filters that have a value
  const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))

  const load = useCallback(() => {
    api.get('/transactions', { params }).then((r) => setTransactions(r.data)).catch((e) => setError(errorMessage(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)])

  const loadCategories = () => api.get('/categories').then((r) => setCategories(r.data))

  useEffect(() => { loadCategories() }, [])
  useEffect(() => { load() }, [load])

  const remove = async (tx) => {
    if (!confirm(`Delete this ${tx.type} of ${formatMoney(tx.amount)}?`)) return
    await api.delete(`/transactions/${tx.id}`)
    load()
  }

  const exportCsv = async () => {
    const res = await api.get('/transactions/export', { params, responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'transactions.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const total = (type) => transactions.filter((t) => t.type === type).reduce((s, t) => s + t.amount, 0)

  return (
    <div>
      <div className="page-header">
        <h1>Transactions</h1>
        <div className="actions">
          <button className="btn" onClick={() => setShowCategory(true)}>+ Category</button>
          <button className="btn" onClick={exportCsv}>Export CSV</button>
          <button className="btn primary" onClick={() => setEditing({})}>+ Add transaction</button>
        </div>
      </div>

      <div className="card filters">
        <input type="month" value={filters.month} onChange={(e) => setFilters({ ...filters, month: e.target.value })} />
        <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value, category_id: '' })}>
          <option value="">All types</option>
          <option value="income">Income</option>
          <option value="expense">Expense</option>
        </select>
        <select value={filters.category_id} onChange={(e) => setFilters({ ...filters, category_id: e.target.value })}>
          <option value="">All categories</option>
          {categories.filter((c) => !filters.type || c.type === filters.type).map((c) => (
            <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
          ))}
        </select>
        <input placeholder="Search descriptions…" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
        {Object.keys(params).length > 0 && (
          <button className="btn ghost" onClick={() => setFilters({ month: '', type: '', category_id: '', search: '' })}>Clear</button>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="card">
        <p className="muted">
          {transactions.length} transactions · Income <span className="income">{formatMoney(total('income'))}</span> ·
          Expenses <span className="expense">{formatMoney(total('expense'))}</span>
        </p>
        {transactions.length === 0 ? (
          <p className="muted">No transactions found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Date</th><th>Category</th><th>Description</th><th className="right">Amount</th><th /></tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id}>
                    <td>{formatDate(t.date)}</td>
                    <td><span className={`tag ${t.type}`}>{t.category.name}</span></td>
                    <td>{t.note}</td>
                    <td className={`right ${t.type}`}>{t.type === 'expense' ? '−' : '+'}{formatMoney(t.amount)}</td>
                    <td className="right nowrap">
                      <button className="btn ghost small" onClick={() => setEditing(t)}>Edit</button>
                      <button className="btn ghost small danger" onClick={() => remove(t)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <TransactionForm
          initial={editing}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
        />
      )}
      {showCategory && (
        <CategoryForm onClose={() => setShowCategory(false)} onSaved={() => { setShowCategory(false); loadCategories() }} />
      )}
    </div>
  )
}

function TransactionForm({ initial, categories, onClose, onSaved }) {
  const [form, setForm] = useState(
    initial.id
      ? { type: initial.type, amount: initial.amount, date: initial.date, category_id: initial.category.id, note: initial.note }
      : emptyForm,
  )
  const [error, setError] = useState('')
  const [suggestion, setSuggestion] = useState(null) // { engine } when the category was auto-filled
  const pickedByHand = useRef(Boolean(initial.id))
  const options = categories.filter((c) => c.type === form.type)

  // Auto-categorize: when the note changes, ask the backend for a category (waits until typing pauses)
  useEffect(() => {
    if (pickedByHand.current || form.note.trim().length < 3) return
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.post('/ai/categorize', { note: form.note, type: form.type })
        if (data.category && !pickedByHand.current) {
          setForm((f) => ({ ...f, category_id: data.category.id }))
          setSuggestion({ engine: data.engine })
        }
      } catch {
        // Suggestions are optional; ignore errors
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [form.note, form.type])

  const submit = async (e) => {
    e.preventDefault()
    const body = { ...form, amount: Number(form.amount), category_id: Number(form.category_id) }
    try {
      if (initial.id) await api.put(`/transactions/${initial.id}`, body)
      else await api.post('/transactions', body)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Modal title={initial.id ? 'Edit transaction' : 'Add transaction'} onClose={onClose}>
      <form onSubmit={submit} className="form">
        <div className="toggle">
          {['expense', 'income'].map((t) => (
            <button type="button" key={t} className={form.type === t ? `active ${t}` : ''}
              onClick={() => { pickedByHand.current = Boolean(initial.id); setSuggestion(null); setForm({ ...form, type: t, category_id: '' }) }}>
              {t === 'expense' ? 'Expense' : 'Income'}
            </button>
          ))}
        </div>
        <label>Amount
          <input type="number" min="0.01" step="0.01" required value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </label>
        <label>Description
          <input maxLength={255} placeholder="e.g. Swiggy dinner, Uber to office" value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </label>
        <label>
          <span className="label-row">
            Category
            {suggestion && (
              <span className="suggested" title={suggestion.engine === 'ai' ? 'Suggested by Claude' : 'Suggested from keywords and your history'}>
                ✨ Auto-suggested{suggestion.engine === 'ai' ? ' by AI' : ''}
              </span>
            )}
          </span>
          <select required value={form.category_id} onChange={(e) => {
            pickedByHand.current = true
            setSuggestion(null)
            setForm({ ...form, category_id: e.target.value })
          }}>
            <option value="">Choose…</option>
            {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>Date
          <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary">Save</button>
      </form>
    </Modal>
  )
}

function CategoryForm({ onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', type: 'expense' })
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/categories', form)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Modal title="New category" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label>Name
          <input required maxLength={50} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>Type
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </select>
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary">Create</button>
      </form>
    </Modal>
  )
}
