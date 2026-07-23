import { useState } from 'react'
import UploadForm from './components/UploadForm'
import ResultsDashboard from './components/ResultsDashboard'
import HistoryPage from './components/HistoryPage'
import { getReport } from './api'

export default function App() {
  const [page, setPage] = useState('upload')
  const [currentResult, setCurrentResult] = useState(null)

  const handleResult = async (result) => {
    // POST /analyze returns a compact summary only (run_id, direction,
    // summary) — the dashboard needs the full report (assessment,
    // security, compliance, plan...), so fetch it once analysis
    // completes. Same shape handleViewRun already loads from history.
    try {
      const report = await getReport(result.run_id)
      setCurrentResult(report)
      setPage('results')
    } catch (e) {
      alert('Failed to load report: ' + e.message)
    }
  }

  const handleViewRun = async (runId) => {
    try {
      const report = await getReport(runId)
      setCurrentResult(report)
      setPage('results')
    } catch (e) {
      alert('Failed to load run: ' + e.message)
    }
  }

  return (
    <div>
      {page === 'upload' && (
        <UploadForm onResult={handleResult} />
      )}
      {page === 'results' && currentResult && (
        <ResultsDashboard
          result={currentResult}
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
  )
}
