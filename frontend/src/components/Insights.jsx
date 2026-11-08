import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api'

import { BarChart3, Check, Lightbulb, Sparkles, TriangleAlert } from 'lucide-react'
import { SYSTEM } from '../categories'

const ICONS = {
  positive: { Icon: Check, color: SYSTEM.green },
  warning: { Icon: TriangleAlert, color: SYSTEM.orange },
  info: { Icon: BarChart3, color: SYSTEM.blue },
  tip: { Icon: Lightbulb, color: SYSTEM.yellow },
}

// "Monthly insights" card on the dashboard. Uses Claude when the backend has an API key,
// otherwise the backend's built-in rules.
export default function Insights({ month }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.get('/ai/insights', { params: { month } })
      .then((r) => !cancelled && setData(r.data))
      .catch((e) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [month])

  return (
    <div className="card insights">
      <div className="card-title">
        <h3><Sparkles size={18} color={SYSTEM.purple} />Monthly insights</h3>
        {data && (
          <span className={`badge ${data.engine === 'ai' ? 'ai' : 'rules'}`}
            title={data.engine === 'ai' ? 'Written by Claude' : 'Add an API key to the backend to get AI-written insights'}>
            {data.engine === 'ai' ? 'AI' : 'Smart rules'}
          </span>
        )}
      </div>
      {loading && <p className="muted">Analysing your month…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && data && !error && (
        <>
          <p>{data.summary}</p>
          <ul className="insight-list">
            {data.insights.map((i, idx) => {
              const { Icon, color } = ICONS[i.kind] || ICONS.info
              return (
              <li key={idx} className={`insight ${i.kind}`}>
                <span className="insight-icon" style={{ background: color }}><Icon size={15} strokeWidth={2.5} /></span>
                <div>
                  <strong>{i.title}</strong>
                  <p>{i.text}</p>
                </div>
              </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
