import { useState } from 'react'
import { downloadTerraform, getHtmlReport } from '../api'

const scoreColor = (s, invert = false) => {
  if (s == null) return 'text-text-secondary'
  if (invert) return s < 30 ? 'text-green' : s < 60 ? 'text-yellow' : 'text-red'
  return s >= 70 ? 'text-green' : s >= 40 ? 'text-yellow' : 'text-red'
}

const riskTextColor = (r) => ({ low: 'text-green', medium: 'text-yellow', high: 'text-red', critical: 'text-red' }[r] || 'text-text-secondary')

const strategyBadge = (s) => ({
  rehost: 'text-green border-green/20 bg-green-10',
  replatform: 'text-yellow border-yellow/20 bg-yellow-10',
  manual: 'text-orange border-orange/20 bg-orange-10',
  unsupported: 'text-red border-red/20 bg-red-10',
}[s] || 'text-text-secondary border-border bg-raised')

const TABS = ['Waves', 'Resources', 'Compliance', 'Security', 'Blockers']

function SummaryCard({ label, value, sub, color = 'text-text-primary', bar }) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4 min-w-[140px] shrink-0">
      <div className="mono text-[10px] uppercase tracking-wider text-text-muted mb-2">{label}</div>
      <div className={`text-[28px] font-bold leading-none ${color}`}>{value}</div>
      {sub && <div className="text-xs text-text-secondary mt-1.5">{sub}</div>}
      {bar != null && (
        <div className="h-1 bg-border rounded-full overflow-hidden mt-2.5">
          <div
            className={bar >= 70 ? 'bg-green h-full' : bar >= 40 ? 'bg-yellow h-full' : 'bg-red h-full'}
            style={{ width: `${Math.max(0, Math.min(100, bar))}%`, transition: 'width 0.6s ease' }}
          />
        </div>
      )}
    </div>
  )
}

function DirectionBadge({ direction }) {
  if (!direction) return null
  const isAwsToGcp = direction.startsWith('AWS') && direction.includes('GCP')
  const isGcpToAws = direction.startsWith('GCP') && direction.includes('AWS')
  const cls = isAwsToGcp
    ? 'bg-cyan-10 text-cyan border-cyan/30'
    : isGcpToAws
      ? 'bg-orange-10 text-orange border-orange/30'
      : 'bg-raised text-text-secondary border-border'
  return (
    <span className={`mono px-2.5 py-1 rounded-full text-[11px] font-medium border ${cls}`}>
      {direction}
    </span>
  )
}

function SecurityMeter({ score }) {
  const [mounted, setMounted] = useState(false)
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(100, score ?? 0))
  const offset = circumference - (mounted ? pct : 0) / 100 * circumference
  const color = pct >= 70 ? '#39D353' : pct >= 40 ? '#E3B341' : '#F85149'

  useState(() => { const t = setTimeout(() => setMounted(true), 50); return () => clearTimeout(t) })

  return (
    <div className="flex items-center justify-center py-6">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="#21262D" strokeWidth="10" />
        <circle
          cx="70" cy="70" r={radius} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 70 70)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x="70" y="65" textAnchor="middle" className="mono" fill="#E6EDF3" fontSize="28" fontWeight="600">
          {score ?? '—'}
        </text>
        <text x="70" y="84" textAnchor="middle" fill="#8B949E" fontSize="11">/ 100</text>
      </svg>
    </div>
  )
}

export default function ResultsDashboard({ result, onNewAnalysis, onHistory }) {
  const [downloading, setDownloading] = useState(false)
  const [activeTab, setActiveTab] = useState('Waves')
  const [aiExpanded, setAiExpanded] = useState(false)

  const s = result.summary || {}
  const report = result
  const assessment = report.assessment || {}
  const security = report.security || {}
  const compliance = report.compliance || {}
  const ai = report.ai_analysis

  const handleDownload = async () => {
    setDownloading(true)
    try { await downloadTerraform(result.run_id) }
    catch { alert('Terraform not available for analyze-only runs') }
    finally { setDownloading(false) }
  }

  const handleHtmlReport = async () => {
    const html = await getHtmlReport(result.run_id)
    const w = window.open()
    w.document.write(html)
    w.document.close()
  }

  const copyRunId = () => {
    navigator.clipboard.writeText(result.run_id).then(() => alert('Run ID copied!'))
  }

  const frameworks = compliance.framework_results || []
  const resourceAssessments = assessment.resource_assessments || []
  const waves = (report.plan || {}).waves || []
  const blockers = assessment.blockers || []
  const securityFindings = [
    ...(security.iam_findings || []).map((f) => ({ ...f, category: 'IAM' })),
    ...(security.firewall_findings || []).map((f) => ({ ...f, category: 'Firewall' })),
    ...(security.secret_findings || []).map((f) => ({ ...f, category: 'Secret', message: 'Potential secret detected' })),
  ]

  const tabIndex = TABS.indexOf(activeTab)

  return (
    <div className="min-h-screen bg-void text-text-primary pb-20">
      {/* Topbar */}
      <div className="sticky top-0 z-20 bg-surface border-b border-border px-6 py-3.5 flex items-center justify-between backdrop-blur">
        <div className="flex items-center gap-3">
          <span className="text-lg">🏭</span>
          <span className="font-semibold text-sm">Migration Factory</span>
          <DirectionBadge direction={result.direction} />
        </div>
        <div className="flex items-center gap-3">
          <span className="mono text-text-muted text-xs">{(result.run_id || '').slice(0, 8)}</span>
          <button
            onClick={onNewAnalysis}
            className="px-3 py-1.5 rounded-lg border border-border text-text-secondary hover:border-cyan hover:text-text-primary text-xs font-medium transition-colors"
          >
            New Analysis
          </button>
          <button onClick={onHistory} className="text-text-muted hover:text-text-primary text-xs font-medium transition-colors">
            History
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* Summary row */}
        <div className="flex gap-3 overflow-x-auto pb-1 mb-6 animate-fade-up">
          <SummaryCard
            label="Complexity" value={s.complexity_score ?? '—'}
            sub={`/ 100 · ${(s.risk_level || '—').toUpperCase()}`}
            color={scoreColor(s.complexity_score, true)}
          />
          <SummaryCard
            label="Risk" value={<span className="text-[20px]">{(s.risk_level || '—').toUpperCase()}</span>}
            color={riskTextColor(s.risk_level)}
          />
          <SummaryCard
            label="Confidence" value={s.confidence_score ?? '—'} sub="/ 100"
            color={scoreColor(s.confidence_score)}
          />
          <SummaryCard
            label="Security" value={s.security_score ?? '—'} sub="/ 100"
            color={scoreColor(s.security_score)} bar={s.security_score}
          />
          <SummaryCard
            label="Savings" value={`$${s.monthly_savings ?? 0}`} sub="/ month"
            color={(s.monthly_savings || 0) >= 0 ? 'text-green' : 'text-red'}
          />
          <SummaryCard
            label="Downtime" value={s.downtime_minutes ?? '—'} sub="minutes"
            color={s.downtime_minutes < 10 ? 'text-green' : s.downtime_minutes < 60 ? 'text-yellow' : 'text-red'}
          />
        </div>

        {/* Tabs */}
        <div className="relative flex border-b border-border mb-6">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors
                ${activeTab === tab ? 'text-text-primary' : 'text-text-muted hover:text-text-secondary'}`}
            >
              {tab}
              {tab === 'Blockers' && blockers.length > 0 && (
                <span className="ml-1.5 mono text-[10px] text-red">({blockers.length})</span>
              )}
            </button>
          ))}
          <div
            className="absolute bottom-0 h-[2px] bg-cyan"
            style={{ width: `${100 / TABS.length}%`, left: `${(100 / TABS.length) * tabIndex}%`, transition: 'left 0.2s ease' }}
          />
        </div>

        {/* Tab content */}
        <div className="animate-fade-up">
          {activeTab === 'Waves' && (
            <div className="relative pl-8">
              <div className="absolute left-[13px] top-2 bottom-2 w-px bg-border" />
              {waves.length === 0 && <p className="text-text-muted text-sm">No migration waves.</p>}
              {waves.map((w) => (
                <div key={w.wave_number} className="relative flex items-center gap-4 py-3">
                  <div className="absolute -left-8 w-7 h-7 rounded-full bg-raised border border-border flex items-center justify-center mono text-[11px] text-text-muted">
                    {w.wave_number}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{w.name}</div>
                    <div className="text-xs text-text-secondary">{w.resource_ids?.length ?? 0} resources</div>
                  </div>
                  <span className={`mono text-[10px] px-2 py-0.5 rounded border
                    ${w.can_parallelize ? 'text-cyan border-cyan/30 bg-cyan-10' : 'text-yellow border-yellow/30 bg-yellow-10'}`}>
                    {w.can_parallelize ? '⚡ Parallel' : '→ Sequential'}
                  </span>
                  <span className="mono text-xs text-text-secondary w-14 text-right">
                    {w.estimated_duration_hours < 1 ? `${Math.round(w.estimated_duration_hours * 60)}m` : `${w.estimated_duration_hours.toFixed(1)}h`}
                  </span>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'Resources' && (
            <div className="bg-surface border border-border rounded-xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-xs mono uppercase tracking-wider">
                    <th className="text-left px-4 py-3 font-medium">Resource</th>
                    <th className="text-left px-4 py-3 font-medium">Type</th>
                    <th className="text-right px-4 py-3 font-medium">Score</th>
                    <th className="text-left px-4 py-3 font-medium">Strategy</th>
                    <th className="text-left px-4 py-3 font-medium">Target</th>
                    <th className="text-right px-4 py-3 font-medium">Blockers</th>
                  </tr>
                </thead>
                <tbody>
                  {resourceAssessments.map((r, i) => (
                    <tr key={i} className={`${i % 2 ? 'bg-surface' : 'bg-void'} hover:bg-raised transition-colors`}>
                      <td className="mono px-4 py-2.5 text-xs">{r.resource_name}</td>
                      <td className="px-4 py-2.5 text-text-secondary text-xs">{r.canonical_type}</td>
                      <td className={`px-4 py-2.5 text-right font-bold ${scoreColor(r.complexity_score, true)}`}>{r.complexity_score}</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-2 py-0.5 rounded border text-xs font-medium ${strategyBadge(r.strategy)}`}>{r.strategy}</span>
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary text-xs">{r.target_service || '—'}</td>
                      <td className={`px-4 py-2.5 text-right text-xs ${r.blockers?.length > 0 ? 'text-red' : 'text-green'}`}>
                        {r.blockers?.length ?? 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'Compliance' && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {frameworks.map((f, i) => {
                const pct = Math.round(f.compliance_score)
                const color = pct >= 80 ? 'bg-green' : pct >= 60 ? 'bg-yellow' : 'bg-red'
                const text = pct >= 80 ? 'text-green' : pct >= 60 ? 'text-yellow' : 'text-red'
                return (
                  <div key={i} className="bg-surface border border-border rounded-xl p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-semibold text-sm">{f.framework}</span>
                      <span className={`mono font-bold text-lg ${text}`}>{pct}%</span>
                    </div>
                    <div className="h-1.5 bg-border rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%`, transition: 'width 0.6s ease' }} />
                    </div>
                    <div className={`text-xs mt-2 font-medium ${text}`}>{pct >= 80 ? 'Compliant' : 'Non-compliant'}</div>
                    {f.failed_check_ids?.length > 0 && (
                      <div className="mono text-[11px] text-red mt-2 space-y-0.5">
                        {f.failed_check_ids.slice(0, 3).map((c) => <div key={c}>✗ {c}</div>)}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {activeTab === 'Security' && (
            <div>
              <div className="bg-surface border border-border rounded-xl">
                <SecurityMeter score={security.security_score} />
              </div>
              {securityFindings.length > 0 && (
                <div className="bg-surface border border-border rounded-xl overflow-hidden mt-4">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-text-muted text-xs mono uppercase tracking-wider">
                        <th className="text-left px-4 py-3 font-medium">Severity</th>
                        <th className="text-left px-4 py-3 font-medium">Type</th>
                        <th className="text-left px-4 py-3 font-medium">Resource</th>
                        <th className="text-left px-4 py-3 font-medium">Finding</th>
                      </tr>
                    </thead>
                    <tbody>
                      {securityFindings.slice(0, 10).map((f, i) => (
                        <tr key={i} className={`${i % 2 ? 'bg-surface' : 'bg-void'}`}>
                          <td className={`px-4 py-2.5 font-bold text-xs uppercase ${riskTextColor(f.severity?.toLowerCase())}`}>{f.severity}</td>
                          <td className="px-4 py-2.5 text-text-secondary text-xs">{f.category}</td>
                          <td className="mono px-4 py-2.5 text-xs">{f.resource_name}</td>
                          <td className="px-4 py-2.5 text-text-secondary text-xs">{f.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'Blockers' && (
            <div className="space-y-3">
              {blockers.length === 0 && <p className="text-text-muted text-sm">No blockers — clear to migrate.</p>}
              {blockers.map((b, i) => (
                <div key={i} className="relative bg-surface border border-border rounded-xl p-4 pl-5 overflow-hidden">
                  <span className="absolute left-0 top-0 bottom-0 w-[3px] bg-yellow" />
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2">
                      <span className="text-yellow">⚠</span>
                      <p className="text-sm text-text-secondary">{b}</p>
                    </div>
                    <span className="mono text-[10px] text-text-muted border border-border rounded px-1.5 py-0.5 shrink-0">
                      blocker
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* AI Analysis */}
        {ai && (
          <div className="mt-6 bg-surface border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setAiExpanded((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-4 text-left"
            >
              <span className="font-semibold text-sm flex items-center gap-2">
                🤖 AI Analysis
                <span className="mono text-[10px] text-text-muted border border-border rounded px-1.5 py-0.5">
                  {ai.mode === 'ai' ? 'claude' : 'rule-based'}
                </span>
              </span>
              <span className={`text-text-muted transition-transform ${aiExpanded ? 'rotate-180' : ''}`}>▾</span>
            </button>
            {aiExpanded && (
              <div className="px-5 pb-5 space-y-3">
                {[
                  ['Architecture', ai.summary],
                  ['Risks', ai.risks],
                  ['Optimizations', ai.optimizations],
                ].map(([label, content]) => content && (
                  <div key={label} className="bg-raised border border-border rounded-lg p-4 relative">
                    <div className="mono text-[10px] uppercase tracking-wider text-text-muted mb-2">{label}</div>
                    <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{content}</p>
                  </div>
                ))}
                <div className="text-right mono text-[10px] text-text-muted">
                  {ai.mode === 'ai' ? 'Powered by Claude' : 'Rule-based fallback (no API key configured)'}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-surface border-t border-border px-6 py-3 flex items-center justify-between z-20">
        <span className="mono text-text-muted text-xs">{result.run_id}</span>
        <div className="flex gap-2">
          <button
            onClick={handleDownload} disabled={downloading}
            className="px-4 py-2 rounded-lg border border-green/30 text-green text-xs font-medium hover:bg-green-10 transition-colors disabled:opacity-50"
          >
            {downloading ? 'Downloading…' : 'Download Terraform'}
          </button>
          <button
            onClick={handleHtmlReport}
            className="px-4 py-2 rounded-lg border border-cyan/30 text-cyan text-xs font-medium hover:bg-cyan-10 transition-colors"
          >
            View Report
          </button>
          <button
            onClick={copyRunId}
            className="px-4 py-2 rounded-lg border border-border text-text-muted text-xs font-medium hover:text-text-primary hover:border-text-muted transition-colors"
          >
            Copy Run ID
          </button>
        </div>
      </div>
    </div>
  )
}
