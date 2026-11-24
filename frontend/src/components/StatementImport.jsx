import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CheckCircle2, FileText, Landmark, Lock, TriangleAlert, Upload } from 'lucide-react'
import api, { errorMessage } from '../api'
import CategoryIcon from './CategoryIcon'
import Modal from './Modal'
import { formatDate, formatMoney } from '../format'
import { springs } from '../motion'

const SOURCES = {
  gpay: {
    title: 'Import Google Pay statement',
    hint: "In Google Pay, open your profile and download a transaction statement as PDF. We'll read each payment and let you review everything before anything is saved.",
    accept: 'application/pdf,.pdf',
    choose: 'Choose statement PDF',
    types: 'PDF · up to 10 MB',
    icon: FileText,
    views: [{ value: '', label: 'All' }, { value: 'expense', label: 'Paid' }, { value: 'income', label: 'Received' }],
    labels: { income: 'Received', expense: 'Paid' },
  },
  bank: {
    title: 'Import bank statement',
    hint: "Download your account statement from your bank's net banking or app. Any bank works. Debits become expenses and credits become income, and you can review everything before it's saved.",
    accept: '.pdf,.csv,.xls,.xlsx,.txt,application/pdf,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    choose: 'Choose statement file',
    types: 'PDF, Excel or CSV · up to 10 MB',
    icon: Landmark,
    views: [{ value: '', label: 'All' }, { value: 'expense', label: 'Debits' }, { value: 'income', label: 'Credits' }],
    labels: { income: 'Credits', expense: 'Debits' },
  },
}

// Import a statement in three steps: upload -> review -> done.
// source "gpay": a Google Pay PDF. source "bank": any bank's statement (PDF, Excel or CSV).
export default function StatementImport({ source = 'gpay', categories, onClose, onImported }) {
  const config = SOURCES[source]
  const Icon = config.icon
  const [file, setFile] = useState(null)
  const [password, setPassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [preview, setPreview] = useState(null)
  const [rows, setRows] = useState([]) // preview rows plus { key, selected, category_id }
  const [view, setView] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const categoryById = useMemo(() => Object.fromEntries(categories.map((c) => [c.id, c])), [categories])

  const read = async (event) => {
    event.preventDefault()
    if (!file) return
    setLoading(true)
    setError('')
    const body = new FormData()
    body.append('file', file)
    if (needsPassword && password) body.append('password', password)
    try {
      const { data } = await api.post(`/statements/${source}/preview`, body)
      setPreview(data)
      setRows(data.transactions.map((t, i) => ({
        ...t, key: t.reference || t.upi_id || `row-${i}`, selected: !t.duplicate,
        category_id: t.suggested_category_id || '',
      })))
    } catch (err) {
      // 423: the PDF is locked. Ask for its password and try again.
      if (err.response?.status === 423) setNeedsPassword(true)
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const update = (key, changes) => setRows((all) => all.map((r) => (r.key === key ? { ...r, ...changes } : r)))
  const visible = rows.filter((r) => !view || r.type === view)
  const chosen = rows.filter((r) => r.selected)
  const sum = (type) => chosen.filter((r) => r.type === type).reduce((s, r) => s + r.amount, 0)
  const missingCategory = chosen.some((r) => !r.category_id)
  const allVisibleSelected = visible.length > 0 && visible.every((r) => r.selected || r.duplicate)

  const save = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.post(`/statements/${source}/import`, {
        transactions: chosen.map((r) => ({
          date: r.date, type: r.type, amount: r.amount, note: r.note,
          category_id: Number(r.category_id), upi_id: r.upi_id, reference: r.reference,
        })),
      })
      setResult(data)
      onImported()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    return (
      <Modal title="Statement imported" onClose={onClose}>
        <div className="form statement-done">
          <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={springs.sheet}>
            <CheckCircle2 size={52} strokeWidth={1.75} />
          </motion.div>
          <p><strong>{result.imported}</strong> transaction{result.imported === 1 ? '' : 's'} added.</p>
          {result.skipped_duplicates > 0 && (
            <p className="muted small-text">{result.skipped_duplicates} were already in your list, so they were skipped.</p>
          )}
          <button className="btn primary block" onClick={onClose}>Done</button>
        </div>
      </Modal>
    )
  }

  if (!preview) {
    return (
      <Modal title={config.title} onClose={onClose}>
        <form className="form" onSubmit={read}>
          <div className="hint">{config.hint}</div>
          <label className="receipt-upload">
            <Icon size={28} />
            <strong>{file ? file.name : config.choose}</strong>
            <span className="muted small-text">{config.types}</span>
            <input type="file" accept={config.accept} required
              onChange={(event) => { setFile(event.target.files?.[0] || null); setNeedsPassword(false); setPassword(''); setError('') }} />
          </label>
          {needsPassword && (
            <label>
              <span className="statement-lock"><Lock size={13} />Statement password</span>
              <input type="password" autoComplete="off" autoFocus value={password} required
                placeholder="Often your customer ID or date of birth" onChange={(e) => setPassword(e.target.value)} />
              <span className="muted small-text">Used only to open this file. It is never saved.</span>
            </label>
          )}
          {error && <p className="error">{error}</p>}
          <button className="btn primary block" disabled={!file || loading}>
            <Upload size={16} />{loading ? 'Reading statement…' : 'Read statement'}
          </button>
        </form>
      </Modal>
    )
  }

  const duplicates = rows.filter((r) => r.duplicate).length
  return (
    <Modal title="Review transactions" onClose={onClose} wide>
      <div className="form">
        <div className="statement-meta">
          <span className="muted small-text">
            {preview.bank_name && <strong className="statement-bank">{preview.bank_name} · </strong>}
            {preview.period_start && `${formatDate(preview.period_start)} – ${formatDate(preview.period_end)}`}
          </span>
          {preview.totals_match === true && (
            <span className="statement-badge ok">
              <CheckCircle2 size={13} />{source === 'bank' ? 'Every balance adds up' : 'Matches statement totals'}
            </span>
          )}
          {preview.totals_match === false && (
            <span className="statement-badge warn" title="Some rows may not have been read. Check against the statement.">
              <TriangleAlert size={13} />
              {source === 'bank'
                ? `${preview.balance_mismatches} balance gap${preview.balance_mismatches === 1 ? '' : 's'}, check the statement`
                : 'Totals differ from statement'}
            </span>
          )}
        </div>

        <div className="summary-strip statement-summary">
          <div><span>{config.labels.income}</span><strong className="income">{formatMoney(sum('income'))}</strong></div>
          <div><span>{config.labels.expense}</span><strong>{formatMoney(sum('expense'))}</strong></div>
          <div><span>Selected</span><strong>{chosen.length} of {rows.length}</strong></div>
        </div>

        {(duplicates > 0 || preview.skipped_transfers > 0) && (
          <p className="muted small-text">
            {duplicates > 0 && `${duplicates} already imported and unselected. `}
            {preview.skipped_transfers > 0 && `${preview.skipped_transfers} self transfer${preview.skipped_transfers === 1 ? '' : 's'} left out.`}
          </p>
        )}

        <div className="row-between">
          <div className="segmented" role="group" aria-label="Show">
            {config.views.map((v) => (
              <button key={v.value} type="button" className={view === v.value ? 'active' : ''} onClick={() => setView(v.value)}>
                {view === v.value && <motion.span layoutId="statement-view-pill" className="segment-pill" transition={springs.pill} />}
                <span className="segment-label">{v.label}</span>
              </button>
            ))}
          </div>
          <button type="button" className="btn ghost small" onClick={() => {
            const keys = new Set(visible.filter((r) => !r.duplicate).map((r) => r.key))
            setRows((all) => all.map((r) => (keys.has(r.key) ? { ...r, selected: !allVisibleSelected } : r)))
          }}>
            {allVisibleSelected ? 'Select none' : 'Select all'}
          </button>
        </div>

        <div className="list statement-list">
          {visible.map((r) => {
            const options = categories.filter((c) => c.type === r.type)
            const category = categoryById[r.category_id]
            return (
              <div key={r.key} className={`statement-row${r.selected ? '' : ' off'}`}>
                <input type="checkbox" checked={r.selected} aria-label={`Import ${r.note}`}
                  onChange={(e) => update(r.key, { selected: e.target.checked })} />
                <CategoryIcon name={category?.name || 'Other'} size={32} />
                <div className="row-main">
                  <div className="row-title" title={r.note}>{r.note}</div>
                  <div className="row-sub">
                    {formatDate(r.date)}{r.time ? ` · ${r.time}` : ''}
                    {r.duplicate && <span className="statement-dup">Already imported</span>}
                  </div>
                  {r.narration && r.narration !== r.party && (
                    <div className="statement-narration" title={r.narration}>{r.narration}</div>
                  )}
                  <select aria-label="Category" value={r.category_id}
                    onChange={(e) => update(r.key, { category_id: Number(e.target.value) || '' })}>
                    <option value="">Choose…</option>
                    {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div className={`row-amount ${r.type}`}>{r.type === 'expense' ? '−' : '+'}{formatMoney(r.amount)}</div>
              </div>
            )
          })}
        </div>

        {error && <p className="error">{error}</p>}
        <div className="form-buttons">
          <button className="btn primary block" disabled={loading || chosen.length === 0 || missingCategory} onClick={save}>
            {loading ? 'Importing…' : `Import ${chosen.length} transaction${chosen.length === 1 ? '' : 's'}`}
          </button>
          {missingCategory && <span className="muted small-text">Choose a category for every selected row.</span>}
          <button className="btn block" onClick={() => { setPreview(null); setRows([]); setFile(null); setNeedsPassword(false); setPassword('') }}>Choose another file</button>
        </div>
      </div>
    </Modal>
  )
}
