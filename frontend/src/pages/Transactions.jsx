import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Download, Inbox, Pencil, Plus, ScanLine, Search, Sparkles, Tag, Trash2 } from 'lucide-react'
import api, { errorMessage } from '../api'
import CategoryIcon from '../components/CategoryIcon'
import Modal from '../components/Modal'
import ReceiptScanner from '../components/ReceiptScanner'
import { formatMoney, today } from '../format'
import { originOf, springs } from '../motion'

const emptyForm = { type: 'expense', amount: '', date: today(), category_id: '', note: '' }
const noFilters = { month: '', type: '', category_id: '', search: '' }
const TYPES = [{ value: '', label: 'All' }, { value: 'expense', label: 'Expenses' }, { value: 'income', label: 'Income' }]

// "Today", "Yesterday", or "Mon, 3 Nov" (plus the year if it isn't this year)
function dayLabel(iso) {
  const d = new Date(iso + 'T00:00:00')
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diff = Math.round((startOfToday - d) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', ...(d.getFullYear() !== now.getFullYear() && { year: 'numeric' }),
  })
}

// Transactions come newest first; group neighbours that share a date
function groupByDay(transactions) {
  const groups = []
  for (const t of transactions) {
    const last = groups[groups.length - 1]
    if (last && last.date === t.date) last.items.push(t)
    else groups.push({ date: t.date, items: [t] })
  }
  return groups
}

export default function Transactions() {
  const [transactions, setTransactions] = useState([])
  const [categories, setCategories] = useState([])
  const [filters, setFilters] = useState(noFilters)
  const [editing, setEditing] = useState(null) // null = closed, {} = new, {id,...} = edit
  const [showCategory, setShowCategory] = useState(false)
  const [showReceipt, setShowReceipt] = useState(false)
  const [origin, setOrigin] = useState(null) // where the open form grows from
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
    if (!confirm(`Delete this ${tx.type} of ${formatMoney(tx.amount)}?`)) return false
    await api.delete(`/transactions/${tx.id}`)
    load()
    return true
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

  const openEdit = (e, t) => { setOrigin(originOf(e)); setEditing(t) }
  const total = (type) => transactions.filter((t) => t.type === type).reduce((s, t) => s + t.amount, 0)
  const income = total('income')
  const expenses = total('expense')

  return (
    <div>
      <div className="page-header">
        <h1 className="large-title">Transactions</h1>
        <div className="actions">
          <button className="btn" onClick={(e) => { setOrigin(originOf(e)); setShowCategory(true) }} title="New category">
            <Tag size={16} /><span className="btn-label">Category</span>
          </button>
          <button className="btn" onClick={exportCsv} title="Export CSV">
            <Download size={16} /><span className="btn-label">Export</span>
          </button>
          <button className="btn" onClick={() => setShowReceipt(true)} title="Scan receipt">
            <ScanLine size={16} /><span className="btn-label">Scan receipt</span>
          </button>
          <button className="btn primary" onClick={(e) => { setOrigin(originOf(e)); setEditing({}) }}>
            <Plus size={17} strokeWidth={2.5} />Add
          </button>
        </div>
      </div>

      <div className="filters">
        <div className="segmented" role="group" aria-label="Type">
          {TYPES.map((t) => (
            <button key={t.value} type="button" className={filters.type === t.value ? 'active' : ''}
              onClick={() => setFilters({ ...filters, type: t.value, category_id: '' })}>
              {filters.type === t.value && <motion.span layoutId="type-filter-pill" className="segment-pill" transition={springs.pill} />}
              <span className="segment-label">{t.label}</span>
            </button>
          ))}
        </div>
        <input type="month" aria-label="Month" value={filters.month} onChange={(e) => setFilters({ ...filters, month: e.target.value })} />
        <select aria-label="Category" value={filters.category_id} onChange={(e) => setFilters({ ...filters, category_id: e.target.value })}>
          <option value="">All categories</option>
          {categories.filter((c) => !filters.type || c.type === filters.type).map((c) => (
            <option key={c.id} value={c.id}>{c.name}{filters.type ? '' : ` (${c.type})`}</option>
          ))}
        </select>
        <label className="search">
          <Search size={16} />
          <input type="search" placeholder="Search" aria-label="Search descriptions" value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
        </label>
        {Object.keys(params).length > 0 && (
          <button className="btn ghost small" onClick={() => setFilters(noFilters)}>Clear</button>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="summary-strip">
        <div><span>Income</span><strong className="income">{formatMoney(income)}</strong></div>
        <div><span>Expenses</span><strong>{formatMoney(expenses)}</strong></div>
        <div><span>Net</span><strong className={income - expenses >= 0 ? 'income' : 'expense'}>{formatMoney(income - expenses)}</strong></div>
      </div>

      {transactions.length === 0 ? (
        <div className="list empty" style={{ marginTop: '1rem' }}>
          <Inbox size={40} strokeWidth={1.5} />
          <p>No transactions{Object.keys(params).length ? ' match these filters' : ' yet'}.</p>
        </div>
      ) : (
        groupByDay(transactions).map((g) => (
          <section key={g.date}>
            <h2 className="section-header">{dayLabel(g.date)}</h2>
            <div className="list">
              <AnimatePresence initial={false}>
                {g.items.map((t) => (
                  <motion.div key={t.id} className="list-row" role="button" tabIndex={0}
                    initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={springs.value}
                    onClick={(e) => openEdit(e, t)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEdit(e, t) } }}>
                    <CategoryIcon name={t.category.name} />
                    <div className="row-main">
                      <div className="row-title">{t.note || t.category.name}</div>
                      <div className="row-sub">{t.note ? t.category.name : (t.type === 'income' ? 'Income' : 'Expense')}</div>
                    </div>
                    <div className="row-actions">
                      <button className="icon-btn plain" aria-label="Edit" onClick={(e) => { e.stopPropagation(); openEdit(e, t) }}><Pencil size={15} /></button>
                      <button className="icon-btn plain danger" aria-label="Delete" onClick={(e) => { e.stopPropagation(); remove(t) }}><Trash2 size={15} /></button>
                    </div>
                    <div className={`row-amount ${t.type}`}>{t.type === 'expense' ? '−' : '+'}{formatMoney(t.amount)}</div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </section>
        ))
      )}

      <AnimatePresence>
      {editing && (
        <TransactionForm
          key="transaction-form"
          origin={origin}
          initial={editing}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
          onDelete={async () => { if (await remove(editing)) setEditing(null) }}
        />
      )}
      </AnimatePresence>
      <AnimatePresence>
      {showCategory && (
        <CategoryForm key="category-form" origin={origin}
          onClose={() => setShowCategory(false)} onSaved={() => { setShowCategory(false); loadCategories() }} />
      )}
      </AnimatePresence>
      <AnimatePresence>
        {showReceipt && (
          <ReceiptScanner
            onClose={() => setShowReceipt(false)}
            onScanned={(result) => {
              const matched = categories.find((category) => category.type === 'expense' &&
                category.name.toLowerCase() === (result.suggested_category || '').toLowerCase())
              setOrigin(null)
              setEditing({
                type: 'expense', amount: result.amount ?? '', date: result.date || today(),
                category_id: matched?.id || '', note: result.note || result.merchant || '',
              })
              setShowReceipt(false)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function TransactionForm({ initial, categories, origin, onClose, onSaved, onDelete }) {
  const [form, setForm] = useState(
    initial.id
      ? { type: initial.type, amount: initial.amount, date: initial.date, category_id: initial.category.id, note: initial.note }
      : { ...emptyForm, ...initial },
  )
  const [error, setError] = useState('')
  const [suggestion, setSuggestion] = useState(null) // { engine } when the category was auto-filled
  const pickedByHand = useRef(Boolean(initial.id || initial.category_id))
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
    <Modal title={initial.id ? 'Edit transaction' : 'Add transaction'} origin={origin} onClose={onClose}>
      <form onSubmit={submit} className="form">
        <div className="toggle">
          {['expense', 'income'].map((t) => (
            <button type="button" key={t} className={form.type === t ? `active ${t}` : ''}
              onClick={() => { pickedByHand.current = Boolean(initial.id); setSuggestion(null); setForm({ ...form, type: t, category_id: '' }) }}>
              {form.type === t && <motion.span layoutId="type-pill" className={`toggle-pill ${t}`} transition={springs.pill} />}
              <span className="toggle-label">{t === 'expense' ? 'Expense' : 'Income'}</span>
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
            <AnimatePresence>
              {suggestion && (
                // Materializes in so it's clear *why* the category just changed
                <motion.span key="suggested" className="suggested"
                  title={suggestion.engine === 'ai' ? 'Suggested by Claude' : 'Suggested from keywords and your history'}
                  initial={{ opacity: 0, scale: 0.9, filter: 'blur(4px)' }}
                  animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, scale: 0.9, filter: 'blur(4px)' }}
                  transition={springs.sheet}>
                  <Sparkles size={12} />Auto-suggested{suggestion.engine === 'ai' ? ' by AI' : ''}
                </motion.span>
              )}
            </AnimatePresence>
          </span>
          <select required className={suggestion ? 'just-suggested' : ''} value={form.category_id} onChange={(e) => {
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
        <div className="form-buttons">
          <button className="btn primary block">Save</button>
          {initial.id && (
            <button type="button" className="btn danger block" onClick={onDelete}><Trash2 size={16} />Delete transaction</button>
          )}
        </div>
      </form>
    </Modal>
  )
}

function CategoryForm({ origin, onClose, onSaved }) {
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
    <Modal title="New category" origin={origin} onClose={onClose}>
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
        <button className="btn primary block">Create</button>
      </form>
    </Modal>
  )
}
