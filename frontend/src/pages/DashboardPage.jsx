import { useState, useEffect } from 'react'
import { getRuns } from '../api'

export default function DashboardPage({ onNew, onView }) {
  const [runs,    setRuns]    = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getRuns()
      .then(d => setRuns(d.runs || []))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ fontFamily:'JetBrains Mono', fontSize:13, color:'#2d4a7a' }}>Loading···</div>
    </div>
  )

  // Compute stats
  const total       = runs.length
  const totalRes    = runs.reduce((s,r) => s + (r.resources||0), 0)
  const totalSavings= runs.reduce((s,r) => s + (r.monthly_savings||0), 0)
  const avgDuration = total ? (runs.reduce((s,r) => s + (r.duration_seconds||0), 0) / total) : 0

  const riskCounts  = {low:0, medium:0, high:0, critical:0}
  runs.forEach(r => { if (r.risk_level) riskCounts[r.risk_level.toLowerCase()] = (riskCounts[r.risk_level.toLowerCase()]||0)+1 })

  const dirCounts   = {}
  runs.forEach(r => { const d = r.direction||'Unknown'; dirCounts[d] = (dirCounts[d]||0)+1 })

  const maxDirCount = Math.max(...Object.values(dirCounts), 1)

  const riskColors  = { low:'#34d399', medium:'#fbbf24', high:'#f87171', critical:'#ef4444' }

  const StatCard = ({ label, value, sub, color='#60a5fa', large=false }) => (
    <div style={{ background:'rgba(10,20,50,0.6)', border:'1px solid rgba(99,179,237,0.1)', borderRadius:12, padding:'16px', position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:2, background:`linear-gradient(90deg,transparent,${color},transparent)` }} />
      <div style={{ fontSize:10, fontFamily:'JetBrains Mono', color:'#2d4a7a', textTransform:'uppercase', letterSpacing:'0.1em', marginBottom:6 }}>{label}</div>
      <div style={{ fontSize: large ? 32 : 24, fontWeight:600, fontFamily:'JetBrains Mono', color, lineHeight:1 }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:'#4a6fa5', marginTop:4 }}>{sub}</div>}
    </div>
  )

  return (
    <div style={{ flex:1, overflowY:'auto', padding:'24px' }} className="animate-in">

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24 }}>
        <div>
          <div style={{ fontSize:18, fontWeight:600 }}>Dashboard</div>
          <div style={{ fontSize:11, fontFamily:'JetBrains Mono', color:'#2d4a7a', marginTop:2 }}>
            {total} total analyses
          </div>
        </div>
        <button onClick={onNew} style={{ padding:'7px 18px', borderRadius:9, border:'1px solid rgba(99,179,237,0.25)', background:'rgba(99,179,237,0.07)', color:'#60a5fa', fontSize:12, cursor:'pointer', fontFamily:'Inter' }}>
          + New Analysis
        </button>
      </div>

      {total === 0 ? (
        <div style={{ textAlign:'center', padding:'80px 0' }}>
          <div style={{ fontSize:48, opacity:0.15, marginBottom:16 }}>📊</div>
          <div style={{ fontSize:14, color:'#4a6fa5', marginBottom:8 }}>No analyses yet</div>
          <div style={{ fontSize:12, color:'#2d4a7a', fontFamily:'JetBrains Mono', marginBottom:24 }}>Run your first analysis to see statistics here</div>
          <button onClick={onNew} style={{ padding:'9px 22px', borderRadius:9, border:'1px solid rgba(99,179,237,0.25)', background:'rgba(99,179,237,0.07)', color:'#60a5fa', fontSize:13, cursor:'pointer' }}>
            Start Analyzing →
          </button>
        </div>
      ) : (<>

        {/* Top stats */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:24 }}>
          <StatCard label="Total Analyses"   value={total}                          sub="all time"          color="#60a5fa" large />
          <StatCard label="Resources Analyzed" value={totalRes.toLocaleString()}    sub="across all runs"   color="#a78bfa" large />
          <StatCard label="Total Savings"    value={`$${totalSavings.toLocaleString()}`} sub="per month if migrated" color="#34d399" large />
          <StatCard label="Avg Duration"     value={`${avgDuration.toFixed(1)}s`}   sub="per analysis"     color="#fbbf24" large />
        </div>

        {/* Two column section */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:24 }}>

          {/* Risk distribution */}
          <div style={{ background:'rgba(10,20,50,0.6)', border:'1px solid rgba(99,179,237,0.1)', borderRadius:12, padding:20 }}>
            <div style={{ fontSize:11, fontFamily:'JetBrains Mono', color:'#2d4a7a', textTransform:'uppercase', letterSpacing:'0.1em', marginBottom:16 }}>Risk Distribution</div>
            {Object.entries(riskCounts).filter(([,v])=>v>0).map(([risk, count]) => (
              <div key={risk} style={{ marginBottom:10 }}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                  <span style={{ fontSize:12, fontFamily:'JetBrains Mono', color:riskColors[risk]||'#94a3b8', textTransform:'uppercase' }}>{risk}</span>
                  <span style={{ fontSize:12, fontFamily:'JetBrains Mono', color:'#4a6fa5' }}>{count} run{count>1?'s':''}</span>
                </div>
                <div style={{ height:4, background:'rgba(99,179,237,0.08)', borderRadius:2, overflow:'hidden' }}>
                  <div style={{ height:'100%', width:`${(count/total)*100}%`, background:riskColors[risk]||'#94a3b8', borderRadius:2, transition:'width 0.8s ease' }} />
                </div>
              </div>
            ))}
            {Object.values(riskCounts).every(v=>v===0) && (
              <div style={{ fontSize:12, color:'#2d4a7a', fontFamily:'JetBrains Mono' }}>No risk data yet</div>
            )}
          </div>

          {/* Direction breakdown */}
          <div style={{ background:'rgba(10,20,50,0.6)', border:'1px solid rgba(99,179,237,0.1)', borderRadius:12, padding:20 }}>
            <div style={{ fontSize:11, fontFamily:'JetBrains Mono', color:'#2d4a7a', textTransform:'uppercase', letterSpacing:'0.1em', marginBottom:16 }}>Migration Directions</div>
            {Object.entries(dirCounts).map(([dir, count]) => {
              const c = dir.includes('AWS') && dir.includes('GCP') && dir.indexOf('AWS') < dir.indexOf('GCP') ? '#34d399'
                      : dir.includes('GCP') && dir.includes('AWS') ? '#fb923c' : '#a78bfa'
              return (
                <div key={dir} style={{ marginBottom:10 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                    <span style={{ fontSize:12, fontFamily:'JetBrains Mono', color:c }}>{dir}</span>
                    <span style={{ fontSize:12, fontFamily:'JetBrains Mono', color:'#4a6fa5' }}>{count}</span>
                  </div>
                  <div style={{ height:4, background:'rgba(99,179,237,0.08)', borderRadius:2, overflow:'hidden' }}>
                    <div style={{ height:'100%', width:`${(count/maxDirCount)*100}%`, background:c, borderRadius:2, transition:'width 0.8s ease' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Recent runs timeline */}
        <div style={{ background:'rgba(10,20,50,0.6)', border:'1px solid rgba(99,179,237,0.1)', borderRadius:12, padding:20 }}>
          <div style={{ fontSize:11, fontFamily:'JetBrains Mono', color:'#2d4a7a', textTransform:'uppercase', letterSpacing:'0.1em', marginBottom:16 }}>Recent Analyses</div>
          {runs.slice(0,6).map((run, i) => {
            const dc = run.direction?.includes('AWS') && run.direction?.includes('GCP') && run.direction?.indexOf('AWS') < run.direction?.indexOf('GCP') ? '#34d399'
                     : run.direction?.includes('GCP') && run.direction?.includes('AWS') ? '#fb923c' : '#a78bfa'
            const rc = riskColors[run.risk_level?.toLowerCase()] || '#4a6fa5'
            return (
              <div key={run.run_id} onClick={() => onView(run.run_id)}
                style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 0', borderBottom: i < runs.slice(0,6).length-1 ? '1px solid rgba(99,179,237,0.05)' : 'none', cursor:'pointer', transition:'all 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.paddingLeft='8px'}
                onMouseLeave={e => e.currentTarget.style.paddingLeft='0'}
              >
                <div style={{ width:8, height:8, borderRadius:'50%', background:dc, flexShrink:0, boxShadow:`0 0 6px ${dc}` }} />
                <span style={{ padding:'2px 8px', borderRadius:20, fontSize:10, fontFamily:'JetBrains Mono', background:`${dc}10`, border:`1px solid ${dc}25`, color:dc, flexShrink:0 }}>
                  {run.direction || 'Analysis'}
                </span>
                <span style={{ fontSize:12, color:'#64748b', flex:1 }}>
                  {run.resources || 0} resources
                </span>
                <span style={{ fontSize:11, fontFamily:'JetBrains Mono', color:rc }}>
                  {run.risk_level?.toUpperCase() || '—'}
                </span>
                <span style={{ fontSize:12, fontFamily:'JetBrains Mono', color:'#34d399' }}>
                  ${run.monthly_savings || 0}/mo
                </span>
                <span style={{ fontSize:11, fontFamily:'JetBrains Mono', color:'#2d4a7a' }}>
                  {run.duration_seconds?.toFixed(1)}s
                </span>
                <span style={{ fontSize:11, color:'#60a5fa' }}>View →</span>
              </div>
            )
          })}
        </div>

      </>)}
    </div>
  )
}
