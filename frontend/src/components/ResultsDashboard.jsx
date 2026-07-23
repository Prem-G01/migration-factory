import { useState } from 'react'
import { downloadTerraform, getHtmlReport } from '../api'

const riskColor = (r) =>
  r === 'low' ? 'text-green-400 bg-green-900 border-green-700'
  : r === 'medium' ? 'text-yellow-400 bg-yellow-900 border-yellow-700'
  : 'text-red-400 bg-red-900 border-red-700'

const scoreColor = (s, invert = false) => {
  if (invert) return s <= 30 ? 'text-green-400' : s <= 60 ? 'text-yellow-400' : 'text-red-400'
  return s >= 70 ? 'text-green-400' : s >= 40 ? 'text-yellow-400' : 'text-red-400'
}

const strategyBadge = (s) => {
  const styles = {
    rehost: 'bg-green-900 text-green-300 border-green-700',
    replatform: 'bg-yellow-900 text-yellow-300 border-yellow-700',
    manual: 'bg-orange-900 text-orange-300 border-orange-700',
    unsupported: 'bg-red-900 text-red-300 border-red-700',
  }
  return styles[s] || 'bg-gray-800 text-gray-300 border-gray-600'
}

export default function ResultsDashboard({ result, onNewAnalysis, onHistory }) {
  const [downloading, setDownloading] = useState(false)
  const s = result.summary || {}
  // `result` is always the API's GET /report/{id} shape here (fresh from
  // App.jsx's post-analyze fetch, or from History's "View" button) —
  // assessment/security/compliance/plan already live at the top level,
  // not nested under a separate "report" key.
  const report = result
  const assessment = report.assessment || {}
  const security = report.security || {}
  const compliance = report.compliance || {}

  const handleDownload = async () => {
    setDownloading(true)
    try { await downloadTerraform(result.run_id) }
    catch (e) { alert('Terraform not available for analyze-only runs') }
    finally { setDownloading(false) }
  }

  const handleHtmlReport = async () => {
    const html = await getHtmlReport(result.run_id)
    const w = window.open()
    w.document.write(html)
    w.document.close()
  }

  const copyRunId = () => {
    navigator.clipboard.writeText(result.run_id)
      .then(() => alert('Run ID copied!'))
  }

  const frameworks = compliance.framework_results || []
  const resourceAssessments = assessment.resource_assessments || []
  const waves = (report.plan || {}).waves || []
  const blockers = assessment.blockers || []
  const securityFindings = [
    ...(security.iam_findings || []).map(f => ({...f, category: 'IAM'})),
    ...(security.firewall_findings || []).map(f => ({...f, category: 'Firewall'})),
    ...(security.secret_findings || []).map(f => ({...f, category: 'Secret', message: 'Potential secret detected'})),
  ]

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Navbar */}
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold">🏭 Migration Factory</span>
          <span className={`px-3 py-1 rounded-full text-xs font-bold border
            ${result.direction?.includes('→')
              ? result.direction.includes('GCP') && result.direction.startsWith('AWS')
                ? 'bg-blue-900 text-blue-300 border-blue-700'
                : 'bg-orange-900 text-orange-300 border-orange-700'
              : 'bg-gray-800 text-gray-300 border-gray-600'}`}>
            {result.direction || 'Analysis'}
          </span>
        </div>
        <div className="flex gap-3">
          <button onClick={onHistory}
            className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 text-sm">
            📋 History
          </button>
          <button onClick={onNewAnalysis}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium">
            + New Analysis
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
          {[
            { label: 'Complexity', value: `${s.complexity_score ?? '—'}/100`,
              color: scoreColor(s.complexity_score, true) },
            { label: 'Risk Level', value: (s.risk_level || '—').toUpperCase(),
              color: riskColor(s.risk_level) },
            { label: 'Confidence', value: `${s.confidence_score ?? '—'}/100`,
              color: scoreColor(s.confidence_score) },
            { label: 'Security', value: `${s.security_score ?? '—'}/100`,
              color: scoreColor(s.security_score) },
            { label: 'Savings', value: `$${s.monthly_savings ?? 0}/mo`,
              color: (s.monthly_savings || 0) > 0 ? 'text-green-400' : 'text-red-400' },
            { label: 'Downtime', value: `${s.downtime_minutes ?? '—'} min`,
              color: 'text-white' },
          ].map(card => (
            <div key={card.label}
              className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
              <div className={`text-xl font-bold ${typeof card.color === 'string' && card.color.includes('bg-')
                ? '' : card.color}`}>
                {card.value}
              </div>
              <div className="text-gray-500 text-xs mt-1">{card.label}</div>
            </div>
          ))}
        </div>

        {/* Blockers */}
        {blockers.length > 0 && (
          <div className="mb-6 bg-yellow-900 border border-yellow-700 rounded-xl p-4">
            <h3 className="text-yellow-300 font-semibold mb-2">
              ⚠️ {blockers.length} Blocker{blockers.length > 1 ? 's' : ''} — resolve before migration
            </h3>
            <ul className="space-y-1">
              {blockers.map((b, i) => (
                <li key={i} className="text-yellow-200 text-sm">• {b}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Waves */}
        {waves.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold mb-3">Migration Waves</h2>
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="text-left px-4 py-3">Wave</th>
                    <th className="text-left px-4 py-3">Name</th>
                    <th className="text-right px-4 py-3">Resources</th>
                    <th className="text-left px-4 py-3">Mode</th>
                    <th className="text-right px-4 py-3">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {waves.map((w, i) => (
                    <tr key={i} className="border-b border-gray-800 last:border-0">
                      <td className="px-4 py-3 text-gray-500">#{w.wave_number}</td>
                      <td className="px-4 py-3">{w.name}</td>
                      <td className="px-4 py-3 text-right">{w.resource_ids?.length ?? 0}</td>
                      <td className="px-4 py-3">
                        {w.can_parallelize
                          ? <span className="text-cyan-400">⚡ Parallel</span>
                          : <span className="text-yellow-400">→ Sequential</span>}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-400">
                        {w.estimated_duration_hours < 1
                          ? `${Math.round(w.estimated_duration_hours * 60)}m`
                          : `${w.estimated_duration_hours.toFixed(1)}h`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Resource table */}
        {resourceAssessments.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold mb-3">
              Resource Assessment ({resourceAssessments.length})
            </h2>
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="text-left px-4 py-3">Resource</th>
                    <th className="text-left px-4 py-3">Type</th>
                    <th className="text-right px-4 py-3">Score</th>
                    <th className="text-left px-4 py-3">Strategy</th>
                    <th className="text-left px-4 py-3">Target Service</th>
                    <th className="text-right px-4 py-3">Blockers</th>
                  </tr>
                </thead>
                <tbody>
                  {resourceAssessments.map((r, i) => (
                    <tr key={i} className="border-b border-gray-800 last:border-0">
                      <td className="px-4 py-3 font-mono text-xs">{r.resource_name}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{r.canonical_type}</td>
                      <td className={`px-4 py-3 text-right font-bold
                        ${scoreColor(r.complexity_score, true)}`}>
                        {r.complexity_score}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded border text-xs font-medium
                          ${strategyBadge(r.strategy)}`}>
                          {r.strategy}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {r.target_service || '—'}
                      </td>
                      <td className={`px-4 py-3 text-right text-xs
                        ${r.blockers?.length > 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {r.blockers?.length ?? 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Compliance */}
        {frameworks.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold mb-3">Compliance</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {frameworks.map((f, i) => {
                const pct = Math.round(f.compliance_score)
                const color = pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                const textColor = pct >= 80 ? 'text-green-400' : pct >= 60 ? 'text-yellow-400' : 'text-red-400'
                return (
                  <div key={i} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium text-sm">{f.framework}</span>
                      <span className={`font-bold text-sm ${textColor}`}>{pct}%</span>
                    </div>
                    <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${color}`}
                        style={{ width: `${pct}%` }} />
                    </div>
                    <div className={`text-xs mt-2 ${textColor}`}>
                      {pct >= 80 ? '✓ Compliant' : '✗ Non-compliant'}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Security findings */}
        {securityFindings.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold mb-3">
              Security Findings ({securityFindings.length})
            </h2>
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="text-left px-4 py-3">Severity</th>
                    <th className="text-left px-4 py-3">Type</th>
                    <th className="text-left px-4 py-3">Resource</th>
                    <th className="text-left px-4 py-3">Finding</th>
                  </tr>
                </thead>
                <tbody>
                  {securityFindings.slice(0, 10).map((f, i) => {
                    const sevColor = {
                      critical: 'text-red-400', high: 'text-orange-400',
                      medium: 'text-yellow-400', low: 'text-gray-400'
                    }[f.severity?.toLowerCase()] || 'text-gray-400'
                    return (
                      <tr key={i} className="border-b border-gray-800 last:border-0">
                        <td className={`px-4 py-3 font-bold text-xs uppercase ${sevColor}`}>
                          {f.severity}
                        </td>
                        <td className="px-4 py-3 text-gray-400 text-xs">{f.category}</td>
                        <td className="px-4 py-3 font-mono text-xs">{f.resource_name}</td>
                        <td className="px-4 py-3 text-gray-300 text-xs">{f.message}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 flex-wrap">
          <button onClick={handleDownload} disabled={downloading}
            className="px-6 py-3 rounded-xl bg-green-700 hover:bg-green-600
              disabled:bg-gray-700 disabled:text-gray-500 font-medium transition-all">
            {downloading ? '⏳ Downloading...' : '⬇️ Download Terraform'}
          </button>
          <button onClick={handleHtmlReport}
            className="px-6 py-3 rounded-xl bg-blue-700 hover:bg-blue-600
              font-medium transition-all">
            📄 View Full Report
          </button>
          <button onClick={copyRunId}
            className="px-6 py-3 rounded-xl border border-gray-700
              hover:border-gray-500 text-gray-400 hover:text-white font-medium transition-all">
            📋 Copy Run ID
          </button>
        </div>
      </div>
    </div>
  )
}
