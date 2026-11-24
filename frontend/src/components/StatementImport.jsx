import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CheckCircle2, FileText, TriangleAlert, Upload } from 'lucide-react'
import api, { errorMessage } from '../api'
import CategoryIcon from './CategoryIcon'
import Modal from './Modal'
import { formatDate, formatMoney } from '../format'
import { springs } from '../motion'

const VIEWS = [{ value: '', label: 'All' }, { value: 'expense', label: 'Paid' }, { value: 'income', label: 'Received' }]

// Import a Google Pay statement PDF in three steps: upload -> review -> done.
// "Paid to ..." rows become expenses and "Received from ..." rows become income.
export default function StatementImport({ categories, onClose, onImported }) {
  const [file, setFile] = useState(null)
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
    try {
      const { data } = await api.post('/statements/gpay/preview', body)
      setPreview(data)
      setRows(data.transactions.map((t, i) => ({
        ...t, key: t.upi_id || `row-${i}`, selected: !t.duplicate, category_id: t.suggested_category_id || '',
      })))
    } catch (err) {
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
      const { data } = await api.post('/statements/gpay/import', {
        transactions: chosen.map((r) => ({
          date: r.date, type: r.type, amount: r.amount, note: r.note,
          category_id: Number(r.category_id), upi_id: r.upi_id,
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
      <Modal title="Import Google Pay statement" onClose={onClose}>
        <form className="form" onSubmit={read}>
          <div className="hint">
            In Google Pay, open your profile and download a transaction statement as PDF. We'll read each payment and
            let you review everything before anything is saved.
          </div>
          <label className="receipt-upload">
            <FileText size={28} />
            <strong>{file ? file.name : 'Choose statement PDF'}</strong>
            <span className="muted small-text">PDF · up to 10 MB</span>
            <input type="file" accept="application/pdf,.pdf" required
              onChange={(event) => setFile(event.target.files?.[0] || null)} />
          </label>
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
          {preview.period_start && (
            <span className="muted small-text">{formatDate(preview.period_start)} – {formatDate(preview.period_end)}</span>
          )}
          {preview.totals_match === true && (
            <span className="statement-badge ok"><CheckCircle2 size={13} />Matches statement totals</span>
          )}
          {preview.totals_match === false && (
            <span className="statement-badge warn" title="Some rows may not have been read. Check against the PDF.">
              <TriangleAlert size={13} />Totals differ from statement
            </span>
          )}
        </div>

        <div className="summary-strip statement-summary">
          <div><span>Received</span><strong className="income">{formatMoney(sum('income'))}</strong></div>
          <div><span>Paid</span><strong>{formatMoney(sum('expense'))}</strong></div>
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
            {VIEWS.map((v) => (
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
                  <div className="row-title" title={r.party}>{r.party}</div>
                  <div className="row-sub">
                    {formatDate(r.date)}{r.time ? ` · ${r.time}` : ''}
                    {r.duplicate && <span className="statement-dup">Already imported</span>}
                  </div>
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
          <button className="btn block" onClick={() => { setPreview(null); setRows([]); setFile(null) }}>Choose another file</button>
        </div>
      </div>
    </Modal>
  )
}
