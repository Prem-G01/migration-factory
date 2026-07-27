import { useState, useEffect } from 'react'
import { getRuns, deleteRun } from '../api'

export default function HistoryPage({ onViewRun, onNewAnalysis }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getRuns().then((d) => setRuns(d.runs || [])).finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id) => {
    if (!confirm('Delete this run?')) return
    await deleteRun(id)
    setRuns((r) => r.filter((x) => x.run_id !== id))
  }

  const dirStyle = (dir) => {
    if (!dir) return { bg: 'rgba(139,92,246,0.08)', b: 'rgba(139,92,246,0.25)', c: '#a78bfa' }
    if (dir.includes('AWS') && dir.includes('GCP') && dir.indexOf('AWS') < dir.indexOf('GCP')) {
      return { bg: 'rgba(52,211,153,0.08)', b: 'rgba(52,211,153,0.25)', c: '#34d399' }
    }
    if (dir.includes('GCP') && dir.includes('AWS') && dir.indexOf('GCP') < dir.indexOf('AWS')) {
      return { bg: 'rgba(251,146,60,0.08)', b: 'rgba(251,146,60,0.25)', c: '#fb923c' }
    }
    return { bg: 'rgba(139,92,246,0.08)', b: 'rgba(139,92,246,0.25)', c: '#a78bfa' }
  }

  return (
    <div className="right-panel" style={{ height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0' }}>Analysis History</div>
          <div style={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>{runs.length} runs</div>
        </div>
        <button onClick={onNewAnalysis} style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid rgba(99,179,237,0.25)', background: 'rgba(99,179,237,0.05)', color: '#60a5fa', fontSize: 12, cursor: 'pointer' }}>+ New Analysis</button>
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: '#2d4a7a', fontFamily: 'JetBrains Mono' }}>Loading···</div>}

      {!loading && runs.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: '#2d4a7a', marginBottom: 8 }}>$ migration-factory poc --help</div>
          <div style={{ fontSize: 13, color: '#4a6fa5', marginBottom: 16 }}>No analyses yet. Upload a file to get started.</div>
          <button onClick={onNewAnalysis} className="btn-primary" style={{ width: 'auto', padding: '8px 20px' }}>New Analysis →</button>
        </div>
      )}

      {runs.map((run) => {
        const ds = dirStyle(run.direction)
        return (
          <div key={run.run_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 10, background: 'rgba(10,20,50,0.5)', border: '1px solid rgba(99,179,237,0.07)', borderLeft: `3px solid ${ds.c}`, marginBottom: 6, transition: 'all 0.2s' }}>
            <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: 10, fontFamily: 'JetBrains Mono', background: ds.bg, border: `1px solid ${ds.b}`, color: ds.c, flexShrink: 0 }}>{run.direction || 'Analysis'}</span>
            <span style={{ flex: 1, fontSize: 11, fontFamily: 'JetBrains Mono', color: '#4a6fa5' }}>{run.resources ?? '—'} resources</span>
            <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: '#34d399' }}>${run.monthly_savings ?? 0}/mo</span>
            <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>{run.duration_seconds != null ? `${run.duration_seconds.toFixed(1)}s` : '—'}</span>
            <button onClick={() => onViewRun(run.run_id)} style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid rgba(99,179,237,0.2)', background: 'transparent', color: '#60a5fa', fontSize: 11, cursor: 'pointer' }}>View</button>
            <button onClick={() => handleDelete(run.run_id)} style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(99,179,237,0.08)', background: 'transparent', color: '#2d4a7a', fontSize: 11, cursor: 'pointer' }}>✕</button>
          </div>
        )
      })}
    </div>
  )
}
