import { useState, useEffect } from 'react'
import { getRuns, deleteRun } from '../api'

export default function HistoryPage({ onViewRun, onNewAnalysis }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchRuns = async () => {
    setLoading(true)
    try {
      const data = await getRuns()
      setRuns(data.runs || [])
    } catch (e) {
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
      setRuns(runs.filter(r => r.run_id !== runId))
    } catch (e) {
      alert('Failed to delete run')
    }
  }

  const riskBadge = (r) => {
    const colors = {
      low: 'text-green-400 bg-green-900',
      medium: 'text-yellow-400 bg-yellow-900',
      high: 'text-red-400 bg-red-900'
    }
    return `px-2 py-0.5 rounded text-xs font-bold ${colors[r] || 'text-gray-400 bg-gray-800'}`
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-4
        flex items-center justify-between">
        <span className="text-xl font-bold">🏭 Migration Factory</span>
        <button onClick={onNewAnalysis}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium">
          + New Analysis
        </button>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <h2 className="text-xl font-semibold mb-6">Analysis History</h2>

        {loading && (
          <div className="text-center py-16 text-gray-500">Loading...</div>
        )}

        {error && (
          <div className="p-4 bg-red-900 border border-red-700 rounded-xl text-red-300">
            {error}
          </div>
        )}

        {!loading && runs.length === 0 && (
          <div className="text-center py-16">
            <div className="text-5xl mb-4">📭</div>
            <p className="text-gray-400">No previous analyses.</p>
            <button onClick={onNewAnalysis}
              className="mt-4 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 font-medium">
              Upload a file to get started
            </button>
          </div>
        )}

        {runs.length > 0 && (
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="text-left px-4 py-3">Direction</th>
                  <th className="text-right px-4 py-3">Resources</th>
                  <th className="text-left px-4 py-3">Risk</th>
                  <th className="text-right px-4 py-3">Savings</th>
                  <th className="text-right px-4 py-3">Duration</th>
                  <th className="text-right px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id}
                    className="border-b border-gray-800 last:border-0 hover:bg-gray-800">
                    <td className="px-4 py-3 font-medium">
                      {run.direction || 'Analysis'}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400">
                      {run.resources ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      {run.risk_level && (
                        <span className={riskBadge(run.risk_level)}>
                          {run.risk_level.toUpperCase()}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-green-400">
                      {run.monthly_savings != null
                        ? `$${run.monthly_savings}/mo` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500">
                      {run.duration_seconds != null
                        ? `${run.duration_seconds.toFixed(1)}s` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => onViewRun(run.run_id)}
                          className="px-3 py-1 rounded bg-blue-800 hover:bg-blue-700
                            text-blue-300 text-xs font-medium">
                          View
                        </button>
                        <button
                          onClick={() => handleDelete(run.run_id)}
                          className="px-3 py-1 rounded bg-gray-800 hover:bg-red-900
                            text-gray-400 hover:text-red-300 text-xs font-medium">
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
