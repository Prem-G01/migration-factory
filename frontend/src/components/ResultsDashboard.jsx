import { useEffect, useState } from 'react'
import { downloadTerraform, getHtmlReport } from '../api'

const scoreColor = (s, invert = false) => {
  if (invert) return s <= 30 ? '#34d399' : s <= 60 ? '#fbbf24' : '#f87171'
  return s >= 70 ? '#34d399' : s >= 40 ? '#fbbf24' : '#f87171'
}

const riskColor = (r) => ({ low: '#34d399', medium: '#fbbf24', high: '#f87171', critical: '#ef4444' }[r?.toLowerCase()] || '#64748b')

const frameworkColor = (s) => (s >= 80 ? '#34d399' : s >= 60 ? '#fbbf24' : '#f87171')

const strategyBorderColor = { rehost: '#34d399', replatform: '#fbbf24', manual: '#fb923c', unsupported: '#f87171' }

// downloadTerraform requests responseType: 'blob', and browsers apply that
// responseType uniformly regardless of status code — so an error response's
// body arrives as a Blob too, not parsed JSON. e.response.data.detail would
// silently be undefined in that case; read the blob as text first.
const extractErrorDetail = async (e) => {
  const data = e.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return parsed.detail || e.message || 'Download failed'
    } catch {
      return e.message || 'Download failed'
    }
  }
  return data?.detail || e.message || 'Download failed'
}

// Animates from 0 to `value` over `duration`ms using requestAnimationFrame.
// Re-runs whenever `value` changes (e.g. a new run's results load in).
function CountUp({ value, duration = 800, prefix = '' }) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const target = Number(value) || 0
    let raf
    const start = performance.now()
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - (1 - progress) ** 3
      setDisplay(target * eased)
      if (progress < 1) raf = requestAnimationFrame(tick)
      else setDisplay(target)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return <>{prefix}{Math.round(display)}</>
}

function SecurityRing({ score }) {
  const [animated, setAnimated] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 50)
    return () => clearTimeout(t)
  }, [])

  const radius = 30
  const circumference = 2 * Math.PI * radius
  const pct = score ?? 0
  const color = scoreColor(pct)
  const offset = circumference * (1 - (animated ? pct : 0) / 100)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <svg width={72} height={72} viewBox="0 0 72 72">
        <circle cx={36} cy={36} r={radius} fill="none" stroke="rgba(99,179,237,0.1)" strokeWidth={6} />
        <circle
          cx={36} cy={36} r={radius} fill="none" stroke={color} strokeWidth={6} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 36 36)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x={36} y={41} textAnchor="middle" fontSize={18} fontWeight={600} fontFamily="'JetBrains Mono', monospace" fill={color}>
          {score ?? '—'}
        </text>
      </svg>
      <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>
        {pct >= 80 ? 'Good posture' : 'Needs attention'}
      </div>
    </div>
  )
}

function EmptyState({ icon, message }) {
  return (
    <div style={{ textAlign: 'center', padding: 24, color: '#4a6fa5', fontSize: 12, lineHeight: 1.6 }}>
      <div style={{ fontSize: 22, marginBottom: 6 }}>{icon}</div>
      {message}
    </div>
  )
}

export default function ResultsDashboard({ result, onNewAnalysis, onHistory }) {
  const [activeTab, setActiveTab] = useState('waves')
  const [downloading, setDownloading] = useState(false)
  const [dlError, setDlError] = useState('')
  const [aiExpanded, setAiExpanded] = useState(false)
  const [complianceAnimated, setComplianceAnimated] = useState(false)

  // `result` here IS the full report object returned by GET /api/v1/report/{id}
  // (assessment/security/compliance/plan/ai_analysis all live at the top level,
  // not nested under a "report" key).
  const s = result?.summary || {}
  const assessment = result?.assessment || {}
  const compliance = result?.compliance || {}
  const security = result?.security || {}
  const plan = result?.plan || {}
  const ai = result?.ai_analysis
  const waves = plan?.waves || []
  const frameworks = compliance?.framework_results || []
  const resources = assessment?.resource_assessments || []
  const blockers = assessment?.blockers || []
  const secFindings = [
    ...(security?.iam_findings || []).map((f) => ({ ...f, cat: 'IAM' })),
    ...(security?.firewall_findings || []).map((f) => ({ ...f, cat: 'Firewall' })),
    ...(security?.secret_findings || []).map((f) => ({ ...f, cat: 'Secrets' })),
  ]

  // Compliance bars animate from 0% to their value each time the tab is
  // shown, not just on first mount — reset then re-trigger on tab switch.
  useEffect(() => {
    if (activeTab !== 'compliance') {
      setComplianceAnimated(false)
      return
    }
    const t = setTimeout(() => setComplianceAnimated(true), 30)
    return () => clearTimeout(t)
  }, [activeTab])

  // Authoritative: the backend already knows whether Terraform was generated
  // for this run (analyze_only mode skips generation entirely) and reports
  // it directly, so there's no need to guess from the `direction` string.
  const isAnalyzeOnly = result?.terraform_available === false

  const handleDownload = async () => {
    setDlError('')
    if (isAnalyzeOnly) {
      setDlError('Select "Migrate to GCP" or "Migrate to AWS" as target to generate Terraform')
      return
    }
    setDownloading(true)
    try {
      await downloadTerraform(result.run_id)
    } catch (e) {
      setDlError(await extractErrorDetail(e))
    } finally {
      setDownloading(false)
    }
  }

  const handleReport = async () => {
    const html = await getHtmlReport(result.run_id)
    const w = window.open(); w.document.write(html); w.document.close()
  }

  // Keyboard shortcuts, scoped to this component's lifetime (i.e. only
  // active while the results page is showing). Ignored while a form field
  // elsewhere in the app has focus, so typing "n"/"h"/"d"/"r" in an input
  // doesn't accidentally trigger navigation.
  useEffect(() => {
    const onKeyDown = (e) => {
      const tag = document.activeElement?.tagName
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable
      if (typing) return

      if (e.key === 'n' || e.key === 'N') onNewAnalysis?.()
      else if (e.key === 'h' || e.key === 'H') onHistory?.()
      else if (e.key === 'd' || e.key === 'D') handleDownload()
      else if (e.key === 'r' || e.key === 'R') handleReport()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.run_id, isAnalyzeOnly])

  const TABS = ['waves', 'resources', 'compliance', 'security', 'blockers']

  const direction = result?.direction || ''
  const dirColor = direction.includes('AWS') && direction.includes('GCP') && direction.indexOf('AWS') < direction.indexOf('GCP')
    ? { bg: 'rgba(52,211,153,0.08)', border: 'rgba(52,211,153,0.25)', color: '#34d399' }
    : direction.includes('GCP') && direction.includes('AWS') && direction.indexOf('GCP') < direction.indexOf('AWS')
    ? { bg: 'rgba(251,146,60,0.08)', border: 'rgba(251,146,60,0.25)', color: '#fb923c' }
    : { bg: 'rgba(139,92,246,0.08)', border: 'rgba(139,92,246,0.25)', color: '#a78bfa' }

  return (
    <div className="right-panel" style={{ height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 11, fontFamily: 'JetBrains Mono', background: dirColor.bg, border: `1px solid ${dirColor.border}`, color: dirColor.color }}>
            {result?.direction || 'Analysis'}
          </span>
          <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>{result?.run_id?.slice(0, 8)}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={onHistory} style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid rgba(99,179,237,0.1)', background: 'transparent', color: '#4a6fa5', fontSize: 11, cursor: 'pointer' }}>History</button>
          <button onClick={onNewAnalysis} style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid rgba(99,179,237,0.25)', background: 'rgba(99,179,237,0.05)', color: '#60a5fa', fontSize: 11, cursor: 'pointer' }}>+ New</button>
        </div>
      </div>

      <div className="metrics-grid">
        {[
          { label: 'Complexity', raw: s.complexity_score, sub: '/100', cls: 'green', color: scoreColor(s.complexity_score, true), countUp: true },
          { label: 'Risk', raw: null, display: (s.risk_level || '—').toUpperCase(), sub: 'level', cls: 'yellow', color: riskColor(s.risk_level) },
          { label: 'Confidence', raw: s.confidence_score, sub: '/100', cls: 'blue', color: scoreColor(s.confidence_score), countUp: true },
          { label: 'Security', raw: s.security_score, sub: '/100', cls: 'cyan', color: scoreColor(s.security_score), countUp: true },
          { label: 'Savings', raw: s.monthly_savings, prefix: '$', sub: '/month', cls: 'green', color: '#34d399', countUp: true },
          { label: 'Downtime', raw: null, display: `${s.downtime_minutes ?? '—'}`, sub: 'minutes', cls: 'yellow', color: s.downtime_minutes < 10 ? '#34d399' : s.downtime_minutes < 60 ? '#fbbf24' : '#f87171' },
        ].map((m, i) => (
          <div key={i} className={`metric-card ${m.cls}`}>
            <div className="section-label" style={{ marginBottom: 2 }}>{m.label}</div>
            <div className="metric-value" style={{ color: m.color, fontSize: 20 }}>
              {m.countUp && m.raw != null ? <CountUp value={m.raw} prefix={m.prefix || ''} /> : (m.display ?? (m.raw ?? '—'))}
            </div>
            <div style={{ fontSize: 10, color: '#2d4a7a', fontFamily: 'JetBrains Mono' }}>{m.sub}</div>
          </div>
        ))}
      </div>

      <div className="result-tabs">
        {TABS.map((tab) => (
          <button key={tab} className={`result-tab ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
            {tab}
            {tab === 'blockers' && blockers.length > 0 && <span style={{ marginLeft: 4, background: 'rgba(251,191,36,0.2)', color: '#fbbf24', borderRadius: 10, padding: '0 5px', fontSize: 9 }}>{blockers.length}</span>}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeTab === 'waves' && (
          <div>
            {waves.length === 0 ? (
              <EmptyState icon="🌊" message='No waves — analysis-only mode. Select GCP or AWS target to get migration plan.' />
            ) : (
              <div style={{ position: 'relative' }}>
                <div style={{ position: 'absolute', left: 23, top: 19, bottom: 19, width: 2, background: 'rgba(99,179,237,0.15)', zIndex: 0 }} />
                {waves.map((w, i) => (
                  <div key={i} className="wave-item" style={{ position: 'relative', zIndex: 1 }}>
                    <div className="wave-num">{w.wave_number}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, color: '#94a3b8' }}>{w.name}</div>
                      <div style={{ fontSize: 10, color: '#4a6fa5', fontFamily: 'JetBrains Mono' }}>{w.resource_ids?.length || 0} resources</div>
                    </div>
                    <span style={{
                      padding: '2px 8px', borderRadius: 20, fontSize: 10, fontFamily: 'JetBrains Mono',
                      background: w.can_parallelize ? 'rgba(52,211,153,0.08)' : 'rgba(251,191,36,0.08)',
                      color: w.can_parallelize ? '#34d399' : '#fbbf24',
                      border: `1px solid ${w.can_parallelize ? 'rgba(52,211,153,0.2)' : 'rgba(251,191,36,0.2)'}`,
                    }}>
                      {w.can_parallelize ? '⚡ Parallel' : '→ Sequential'}
                    </span>
                    <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a', marginLeft: 6 }}>
                      {w.estimated_duration_hours < 1 ? `${Math.round(w.estimated_duration_hours * 60)}m` : `${w.estimated_duration_hours.toFixed(1)}h`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'resources' && (
          <div style={{ overflowX: 'auto' }}>
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Type</th>
                  <th>Score</th>
                  <th>Strategy</th>
                  <th>Target</th>
                </tr>
              </thead>
              <tbody>
                {resources.map((r, i) => (
                  <tr key={i} style={{ borderLeft: `2px solid ${strategyBorderColor[r.strategy] || 'transparent'}` }}>
                    <td style={{ fontFamily: 'JetBrains Mono', color: '#94a3b8', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.resource_name}</td>
                    <td style={{ fontFamily: 'JetBrains Mono', color: '#2d4a7a', fontSize: 10 }}>{r.canonical_type?.split('.')[1] || r.canonical_type}</td>
                    <td style={{ fontFamily: 'JetBrains Mono', color: scoreColor(r.complexity_score, true), fontWeight: 500 }}>{r.complexity_score}</td>
                    <td><span className={`strategy-badge badge-${r.strategy}`}>{r.strategy}</span></td>
                    <td style={{ fontFamily: 'JetBrains Mono', color: '#4a6fa5', fontSize: 10, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.target_service || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'compliance' && (
          <div>
            {frameworks.map((f, i) => {
              const pct = Math.round(f.compliance_score)
              const color = frameworkColor(pct)
              return (
                <div key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontFamily: 'JetBrains Mono', color: '#64748b' }}>{f.framework}</span>
                    <span style={{ fontSize: 12, fontFamily: 'JetBrains Mono', color, fontWeight: 500 }}>{pct}%</span>
                  </div>
                  <div className="compliance-track">
                    <div className="compliance-fill" style={{ width: complianceAnimated ? `${pct}%` : '0%', background: color }}></div>
                  </div>
                  {f.failed_check_ids?.length > 0 && (
                    <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a', marginTop: 2 }}>
                      Failed: {f.failed_check_ids.slice(0, 3).join(', ')}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {activeTab === 'security' && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12, padding: '10px 14px', background: 'rgba(10,20,50,0.5)', borderRadius: 10, border: '1px solid rgba(99,179,237,0.08)' }}>
              <SecurityRing score={s.security_score} />
              <div style={{ fontSize: 11, color: '#64748b' }}>Security Score</div>
            </div>
            {secFindings.slice(0, 8).map((f, i) => (
              <div key={i} className="wave-item" style={{ marginBottom: 5 }}>
                <span style={{
                  padding: '2px 7px', borderRadius: 20, fontSize: 10, fontFamily: 'JetBrains Mono',
                  background: f.severity === 'high' || f.severity === 'critical' ? 'rgba(248,113,113,0.1)' : 'rgba(251,191,36,0.1)',
                  color: f.severity === 'high' || f.severity === 'critical' ? '#f87171' : '#fbbf24',
                  border: `1px solid ${f.severity === 'high' || f.severity === 'critical' ? 'rgba(248,113,113,0.2)' : 'rgba(251,191,36,0.2)'}`,
                }}>
                  {f.severity?.toUpperCase()}
                </span>
                <div style={{ flex: 1, fontSize: 11, color: '#64748b' }}>{f.message?.slice(0, 60)}</div>
                <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>{f.cat}</span>
              </div>
            ))}
            {secFindings.length === 0 && <EmptyState icon="🛡️" message="No security findings detected." />}
          </div>
        )}

        {activeTab === 'blockers' && (
          <div>
            {blockers.length === 0 ? (
              <EmptyState icon="✅" message="No blockers found. Infrastructure is ready to migrate." />
            ) : blockers.map((b, i) => (
              <div key={i} className="blocker-item">⚠ {b}</div>
            ))}
          </div>
        )}
      </div>

      {ai?.risks && (
        <div className="ai-section" style={{ marginTop: 12 }}>
          <button className="ai-header" onClick={() => setAiExpanded((v) => !v)}>
            <span style={{ fontSize: 10, color: '#a78bfa', width: 10 }}>{aiExpanded ? '▾' : '▸'}</span>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'ai-pulse 2s ease infinite' }}></div>
            <span style={{ fontSize: 11, fontWeight: 500, color: '#a78bfa' }}>AI Analysis</span>
            <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#4a1d96', marginLeft: 'auto' }}>{ai.fallback ? 'Rule-based' : 'Claude'}</span>
          </button>
          <div className={`ai-content ${aiExpanded ? 'open' : ''}`}>
            <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.7, paddingTop: 8 }}>{ai.risks?.slice(0, 250)}</div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button
          className="act-btn dl"
          onClick={handleDownload}
          disabled={downloading || isAnalyzeOnly}
          title={isAnalyzeOnly ? 'No Terraform was generated for this run — analyze-only mode has no infrastructure target' : undefined}
          style={isAnalyzeOnly ? { borderColor: 'rgba(99,179,237,0.1)', color: '#2d4a7a', cursor: 'not-allowed' } : undefined}
        >
          {downloading ? '···' : '⬇ Terraform'}
        </button>
        <button className="act-btn rp" onClick={handleReport}>📄 Report</button>
        <button className="act-btn cp" onClick={() => navigator.clipboard.writeText(result?.run_id || '')}>⎘ ID</button>
      </div>
      <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a', textAlign: 'center' }}>
        n new · h history · d download · r report
      </div>
      {dlError && (
        <div style={{ marginTop: 8, padding: '8px 12px', background: 'rgba(248,113,113,0.07)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, fontSize: 12, color: '#f87171' }}>
          {dlError}
        </div>
      )}
    </div>
  )
}
