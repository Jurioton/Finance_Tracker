import { useState } from 'react'
import { FileImage, ScanLine, Upload } from 'lucide-react'
import api, { errorMessage } from '../api'
import Modal from './Modal'

export default function ReceiptScanner({ onClose, onScanned }) {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const scan = async (event) => {
    event.preventDefault()
    if (!file) return
    setLoading(true)
    setError('')
    const body = new FormData()
    body.append('file', file)
    try {
      const response = await api.post('/receipts/scan', body)
      setResult(response.data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="Scan a receipt" onClose={onClose}>
      {!result ? (
        <form className="form" onSubmit={scan}>
          <div className="hint">Upload a clear receipt photo. We'll extract the merchant, amount and date, then let you review everything before saving.</div>
          <label className="receipt-upload">
            <FileImage size={28} />
            <strong>{file ? file.name : 'Choose receipt image'}</strong>
            <span className="muted small-text">JPG, PNG or WebP · up to 5 MB</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              required
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="btn primary block" disabled={!file || loading}>
            <ScanLine size={16} />{loading ? 'Scanning…' : 'Scan receipt'}
          </button>
        </form>
      ) : (
        <div className="form">
          <div className="hint">We found some details. Check them in the transaction form before saving; OCR can make mistakes.</div>
          <div className="receipt-result">
            <div><span>Merchant</span><strong>{result.merchant || 'Not detected'}</strong></div>
            <div><span>Amount</span><strong>{result.amount == null ? 'Not detected' : result.amount.toLocaleString('en-IN', { style: 'currency', currency: 'INR' })}</strong></div>
            <div><span>Date</span><strong>{result.date || 'Not detected'}</strong></div>
            <div><span>Suggested category</span><strong>{result.suggested_category || 'Choose manually'}</strong></div>
          </div>
          <details className="receipt-text">
            <summary>View extracted text</summary>
            <pre>{result.extracted_text}</pre>
          </details>
          <button className="btn primary block" onClick={() => onScanned(result)}>
            <Upload size={16} />Review transaction details
          </button>
          <button className="btn block" onClick={() => setResult(null)}>Scan another receipt</button>
        </div>
      )}
    </Modal>
  )
}
