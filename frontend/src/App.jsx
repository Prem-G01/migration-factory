import { useState, useEffect, useCallback } from 'react'
import UploadForm from './components/UploadForm'
import ResultsDashboard from './components/ResultsDashboard'
import HistoryPage from './components/HistoryPage'
import { getReport } from './api'

const TRANSITION_MS = 150

export default function App() {
  const [page, setPage] = useState('upload')
  const [currentResult, setCurrentResult] = useState(null)
  const [visible, setVisible] = useState(true)

  const navigateTo = useCallback((nextPage) => {
    setVisible(false)
    setTimeout(() => {
      setPage(nextPage)
      setVisible(true)
    }, TRANSITION_MS)
  }, [])

  const handleResult = async (result) => {
    // POST /analyze returns a compact summary only (run_id, direction,
    // summary) — the dashboard needs the full report (assessment,
    // security, compliance, plan...), so fetch it once analysis
    // completes. Same shape handleViewRun already loads from history.
    try {
      const report = await getReport(result.run_id)
      setCurrentResult(report)
      navigateTo('results')
    } catch (e) {
      alert('Failed to load report: ' + e.message)
    }
  }

  const handleViewRun = async (runId) => {
    try {
      const report = await getReport(runId)
      setCurrentResult(report)
      navigateTo('results')
    } catch (e) {
      alert('Failed to load run: ' + e.message)
    }
  }

  // Keyboard shortcuts: 'n' -> new analysis, 'h' -> history, Escape ->
  // back to upload from results. Ignored while typing in a form field so
  // e.g. the Discover tab's region input can contain the letter "n".
  useEffect(() => {
    const onKeyDown = (e) => {
      const tag = document.activeElement?.tagName
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable
      if (typing) return

      if (e.key === 'n' || e.key === 'N') {
        navigateTo('upload')
      } else if (e.key === 'h' || e.key === 'H') {
        navigateTo('history')
      } else if (e.key === 'Escape' && page === 'results') {
        navigateTo('upload')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [page, navigateTo])

  return (
    <div className={visible ? 'page-transition-in' : 'page-transition-out'}>
      {page === 'upload' && (
        <UploadForm onResult={handleResult} />
      )}
      {page === 'results' && currentResult && (
        <ResultsDashboard
          result={currentResult}
          onNewAnalysis={() => navigateTo('upload')}
          onHistory={() => navigateTo('history')}
        />
      )}
      {page === 'history' && (
        <HistoryPage
          onViewRun={handleViewRun}
          onNewAnalysis={() => navigateTo('upload')}
        />
      )}
    </div>
  )
}
