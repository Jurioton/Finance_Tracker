import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api'

// Shared layout for the Login and Register pages
export default function AuthForm({ title, fields, submitLabel, onSubmit, footer }) {
  const [values, setValues] = useState(Object.fromEntries(fields.map((f) => [f.name, ''])))
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await onSubmit(values)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h1>💰 Finance Tracker</h1>
        <h2>{title}</h2>
        {fields.map((f) => (
          <label key={f.name}>
            {f.label}
            <input
              type={f.type || 'text'}
              required
              minLength={f.minLength}
              value={values[f.name]}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          </label>
        ))}
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={loading}>{loading ? 'Please wait…' : submitLabel}</button>
        <p className="muted">
          {footer.text} <Link to={footer.to}>{footer.link}</Link>
        </p>
      </form>
    </div>
  )
}
