export default function ProgressBar({ percent, status = 'ok' }) {
  return (
    <div className="progress">
      <div className={`progress-fill ${status}`} style={{ width: `${Math.min(percent, 100)}%` }} />
    </div>
  )
}
