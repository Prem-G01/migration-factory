import { useState } from 'react'
import { downloadTerraform, getHtmlReport } from '../api'

const scoreColor = (s, invert = false) => {
  if (invert) return s <= 30 ? '#34d399' : s <= 60 ? '#fbbf24' : '#f87171'
  return s >= 70 ? '#34d399' : s >= 40 ? '#fbbf24' : '#f87171'
}

const riskColor = (r) => ({ low: '#34d399', medium: '#fbbf24', high: '#f87171', critical: '#ef4444' }[r?.toLowerCase()] || '#64748b')

const frameworkColor = (s) => (s >= 80 ? '#34d399' : s >= 60 ? '#fbbf24' : '#f87171')

export default function ResultsDashboard({ result, onNewAnalysis, onHistory }) {
  const [activeTab, setActiveTab] = useState('waves')
  const [downloading, setDownloading] = useState(false)

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

  const handleDownload = async () => {
    setDownloading(true)
    try { await downloadTerraform(result.run_id) }
    catch { alert('Not available for analyze-only') }
    finally { setDownloading(false) }
  }

  const handleReport = async () => {
    const html = await getHtmlReport(result.run_id)
    const w = window.open(); w.document.write(html); w.document.close()
  }

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
          { label: 'Complexity', value: `${s.complexity_score ?? '—'}`, sub: '/100', cls: 'green', color: scoreColor(s.complexity_score, true) },
          { label: 'Risk', value: (s.risk_level || '—').toUpperCase(), sub: 'level', cls: 'yellow', color: riskColor(s.risk_level) },
          { label: 'Confidence', value: `${s.confidence_score ?? '—'}`, sub: '/100', cls: 'blue', color: scoreColor(s.confidence_score) },
          { label: 'Security', value: `${s.security_score ?? '—'}`, sub: '/100', cls: 'cyan', color: scoreColor(s.security_score) },
          { label: 'Savings', value: `$${s.monthly_savings ?? 0}`, sub: '/month', cls: 'green', color: '#34d399' },
          { label: 'Downtime', value: `${s.downtime_minutes ?? '—'}`, sub: 'minutes', cls: 'yellow', color: s.downtime_minutes < 10 ? '#34d399' : s.downtime_minutes < 60 ? '#fbbf24' : '#f87171' },
        ].map((m, i) => (
          <div key={i} className={`metric-card ${m.cls}`}>
            <div className="section-label" style={{ marginBottom: 2 }}>{m.label}</div>
            <div className="metric-value" style={{ color: m.color, fontSize: 20 }}>{m.value}</div>
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
              <div style={{ textAlign: 'center', padding: '24px', color: '#2d4a7a', fontFamily: 'JetBrains Mono', fontSize: 12 }}>No migration waves (analyze-only mode)</div>
            ) : waves.map((w, i) => (
              <div key={i} className="wave-item">
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
                  <tr key={i}>
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
                    <div className="compliance-fill" style={{ width: `${pct}%`, background: color }}></div>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, padding: '10px 14px', background: 'rgba(10,20,50,0.5)', borderRadius: 10, border: '1px solid rgba(99,179,237,0.08)' }}>
              <div style={{ fontSize: 28, fontFamily: 'JetBrains Mono', fontWeight: 600, color: scoreColor(s.security_score) }}>{s.security_score ?? '—'}</div>
              <div>
                <div style={{ fontSize: 11, color: '#64748b' }}>Security Score</div>
                <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a' }}>{s.security_score >= 80 ? 'Good posture' : 'Needs attention'}</div>
              </div>
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
            {secFindings.length === 0 && <div style={{ textAlign: 'center', padding: 20, color: '#2d4a7a', fontFamily: 'JetBrains Mono', fontSize: 12 }}>No security findings</div>}
          </div>
        )}

        {activeTab === 'blockers' && (
          <div>
            {blockers.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: '#34d399', fontFamily: 'JetBrains Mono', fontSize: 12 }}>✓ No blockers — ready to migrate</div>
            ) : blockers.map((b, i) => (
              <div key={i} className="blocker-item">⚠ {b}</div>
            ))}
          </div>
        )}
      </div>

      {ai?.risks && (
        <div className="ai-section" style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'ai-pulse 2s ease infinite' }}></div>
            <span style={{ fontSize: 11, fontWeight: 500, color: '#a78bfa' }}>AI Analysis</span>
            <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#4a1d96', marginLeft: 'auto' }}>{ai.fallback ? 'Rule-based' : 'Claude'}</span>
          </div>
          <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.7 }}>{ai.risks?.slice(0, 250)}</div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="act-btn dl" onClick={handleDownload} disabled={downloading}>
          {downloading ? '···' : '⬇ Terraform'}
        </button>
        <button className="act-btn rp" onClick={handleReport}>📄 Report</button>
        <button className="act-btn cp" onClick={() => navigator.clipboard.writeText(result?.run_id || '')}>⎘ ID</button>
      </div>
    </div>
  )
}
