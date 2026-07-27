import { useState, useEffect } from 'react'
import { getRuns, deleteRun } from '../api'

const riskColor = (r) => ({ low: 'text-green bg-green-10', medium: 'text-yellow bg-yellow-10', high: 'text-red bg-red-10', critical: 'text-red bg-red-10' }[r] || 'text-text-secondary bg-raised')

const directionAccent = (direction) => {
  if (!direction) return 'border-l-border'
  if (direction.startsWith('AWS') && direction.includes('GCP')) return 'border-l-cyan'
  if (direction.startsWith('GCP') && direction.includes('AWS')) return 'border-l-orange'
  return 'border-l-border'
}

const directionBadge = (direction) => {
  if (!direction) return 'text-text-secondary bg-raised border-border'
  if (direction.startsWith('AWS') && direction.includes('GCP')) return 'text-cyan bg-cyan-10 border-cyan/30'
  if (direction.startsWith('GCP') && direction.includes('AWS')) return 'text-orange bg-orange-10 border-orange/30'
  return 'text-text-secondary bg-raised border-border'
}

export default function HistoryPage({ onViewRun, onNewAnalysis }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchRuns = async () => {
    setLoading(true)
    try {
      const data = await getRuns()
      setRuns(data.runs || [])
    } catch {
      setError('Failed to load run history')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchRuns() }, [])

  const handleDelete = async (runId) => {
    if (!confirm('Delete this run?')) return
    try {
      await deleteRun(runId)
      setRuns(runs.filter((r) => r.run_id !== runId))
    } catch {
      alert('Failed to delete run')
    }
  }

  return (
    <div className="min-h-screen bg-void text-text-primary">
      <div className="sticky top-0 z-20 bg-surface border-b border-border px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg">🏭</span>
          <span className="font-semibold text-sm">Migration Factory</span>
        </div>
        <button
          onClick={onNewAnalysis}
          className="px-3 py-1.5 rounded-lg border border-border text-text-secondary hover:border-cyan hover:text-text-primary text-xs font-medium transition-colors"
        >
          New Analysis
        </button>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-lg font-semibold">Analysis History</h2>
          {!loading && (
            <span className="mono text-[11px] text-text-muted border border-border rounded-full px-2 py-0.5">
              {runs.length} run{runs.length === 1 ? '' : 's'}
            </span>
          )}
        </div>

        {loading && <div className="text-center py-16 text-text-muted mono text-sm">loading…</div>}

        {error && (
          <div className="p-4 bg-red-10 border border-red/30 rounded-xl text-red text-sm">{error}</div>
        )}

        {!loading && !error && runs.length === 0 && (
          <div className="text-center py-20 bg-surface border border-border rounded-xl">
            <p className="mono text-text-secondary text-sm mb-2">$ migration-factory poc --help</p>
            <p className="text-text-muted text-sm mb-6">No analyses found. Upload a file to get started.</p>
            <button
              onClick={onNewAnalysis}
              className="px-5 py-2.5 rounded-lg font-medium text-sm transition-colors border"
              style={{ background: 'linear-gradient(135deg, #00E5FF22, #00E5FF11)', borderColor: '#00E5FF44', color: '#00E5FF' }}
            >
              New Analysis →
            </button>
          </div>
        )}

        {!loading && runs.length > 0 && (
          <div className="bg-surface border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-muted text-xs mono uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">Direction</th>
                  <th className="text-right px-4 py-3 font-medium">Resources</th>
                  <th className="text-left px-4 py-3 font-medium">Risk</th>
                  <th className="text-right px-4 py-3 font-medium">Savings</th>
                  <th className="text-right px-4 py-3 font-medium">Duration</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className={`border-l-2 ${directionAccent(run.direction)} border-b border-border last:border-b-0 hover:bg-raised transition-colors`}
                  >
                    <td className="px-4 py-3">
                      <span className={`mono px-2 py-0.5 rounded-full text-[11px] border ${directionBadge(run.direction)}`}>
                        {run.direction || 'Analysis'}
                      </span>
                    </td>
                    <td className="mono px-4 py-3 text-right text-text-secondary">{run.resources ?? '—'}</td>
                    <td className="px-4 py-3">
                      {run.risk_level && (
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${riskColor(run.risk_level)}`}>
                          {run.risk_level.toUpperCase()}
                        </span>
                      )}
                    </td>
                    <td className="mono px-4 py-3 text-right text-green">
                      {run.monthly_savings != null ? `$${run.monthly_savings}/mo` : '—'}
                    </td>
                    <td className="mono px-4 py-3 text-right text-text-muted">
                      {run.duration_seconds != null ? `${run.duration_seconds.toFixed(1)}s` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-3 justify-end">
                        <button onClick={() => onViewRun(run.run_id)} className="text-cyan hover:opacity-80 text-xs font-medium">
                          View
                        </button>
                        <button onClick={() => handleDelete(run.run_id)} className="text-text-muted hover:text-red text-xs font-medium">
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
