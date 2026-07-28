import { useState } from 'react'
import UploadForm from './components/UploadForm'
import ResultsDashboard from './components/ResultsDashboard'
import HistoryPage from './components/HistoryPage'
import DashboardPage from './pages/DashboardPage'
import { getReport } from './api'

const NAV_ITEMS = [
  { id: 'upload', label: 'Analyze' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'history', label: 'History' },
]

export default function App() {
  const [page, setPage] = useState('upload')
  const [result, setResult] = useState(null)

  // POST /analyze returns a compact summary only (run_id, direction, summary)
  // — the dashboard needs the full report (assessment, security, compliance,
  // plan, ai_analysis...), so fetch it once analysis completes.
  const handleResult = async (r) => {
    try {
      const full = await getReport(r.run_id)
      setResult(full)
      setPage('results')
    } catch (e) {
      alert('Failed to load report: ' + e.message)
    }
  }

  const handleViewRun = async (id) => {
    try {
      const full = await getReport(id)
      setResult(full)
      setPage('results')
    } catch (e) {
      alert('Failed: ' + e.message)
    }
  }

  return (
    <div className="app">
      <div className="topbar">
        <div className="logo">
          <div className="logo-icon">🏭</div>
          Migration Factory
          <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a', marginLeft: 4 }}>v2.0.3</span>
        </div>
        <nav style={{ display: 'flex', gap: 4, marginLeft: 24 }}>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`tab-btn ${page === item.id || (item.id === 'upload' && page === 'results') ? 'active' : ''}`}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          {result && <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 10, fontFamily: 'JetBrains Mono', background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.2)', color: '#34d399' }}>{result.direction || 'Analysis'}</span>}
          <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>aws · gcp</span>
        </div>
      </div>

      <div className="main-layout">
        <UploadForm onResult={handleResult} />

        <div className="right-panel" style={{ height: '100%', overflowY: 'auto' }}>
          {page === 'upload' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 16 }}>
              <div style={{ fontSize: 48, opacity: 0.3 }}>🌌</div>
              <div style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: '#2d4a7a', textAlign: 'center', lineHeight: 2 }}>
                <div>Drop a .tfstate file to analyze</div>
                <div>or use Discover Live to query AWS directly</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                {['AWS→GCP', 'GCP→AWS', 'AWS Analysis', 'GCP Analysis'].map((t) => (
                  <span key={t} style={{ padding: '4px 12px', borderRadius: 20, fontSize: 11, fontFamily: 'JetBrains Mono', background: 'rgba(99,179,237,0.05)', border: '1px solid rgba(99,179,237,0.1)', color: '#4a6fa5' }}>{t}</span>
                ))}
              </div>
              <button onClick={() => setPage('history')} style={{ marginTop: 16, padding: '7px 18px', borderRadius: 9, border: '1px solid rgba(99,179,237,0.15)', background: 'transparent', color: '#4a6fa5', fontSize: 12, cursor: 'pointer', fontFamily: 'JetBrains Mono' }}>
                📋 View History
              </button>
            </div>
          )}

          {page === 'dashboard' && (
            <DashboardPage onNew={() => setPage('upload')} onView={handleViewRun} />
          )}

          {page === 'results' && result && (
            <ResultsDashboard
              result={result}
              onNewAnalysis={() => setPage('upload')}
              onHistory={() => setPage('history')}
            />
          )}

          {page === 'history' && (
            <HistoryPage
              onViewRun={handleViewRun}
              onNewAnalysis={() => setPage('upload')}
            />
          )}
        </div>
      </div>
    </div>
  )
}
