import { useState, useRef } from 'react'
import { analyzeFile, analyzeRawData, discoverAws } from '../api'

const TARGETS = [
  { value: 'gcp', label: 'AWS → GCP', name: 'Migrate to GCP', cls: 'active-aws' },
  { value: 'aws', label: 'GCP → AWS', name: 'Migrate to AWS', cls: 'active-gcp' },
  { value: 'analyze_only', label: 'Analysis', name: 'Analyze Only', cls: 'active-analyze' },
]

export default function UploadForm({ onResult }) {
  const [file, setFile] = useState(null)
  const [target, setTarget] = useState('gcp')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [mode, setMode] = useState('upload')
  const [region, setRegion] = useState('ap-south-1')
  const [discovered, setDiscovered] = useState(null)
  const inputRef = useRef()

  const handleFile = (f) => {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    const ok = ['tfstate', 'json', 'csv', 'xlsx', 'tf', 'log', 'yaml', 'yml']
    if (!ok.includes(ext)) { setError(`Unsupported: .${ext}`); return }
    setFile(f); setError('')
  }

  const handleSubmit = async () => {
    if (!file) { setError('Drop a file first'); return }
    setLoading(true); setError('')
    try {
      const result = await analyzeFile(file, target)
      onResult(result)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Analysis failed')
    } finally { setLoading(false) }
  }

  const handleDiscover = async () => {
    setLoading(true); setError('')
    try {
      const data = await discoverAws(region)
      setDiscovered(data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Discovery failed')
    } finally { setLoading(false) }
  }

  const handleDiscoverAnalyze = async () => {
    if (!discovered?.raw_data) return
    setLoading(true); setError('')
    try {
      const result = await analyzeRawData(discovered.raw_data, target)
      onResult(result)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Analysis failed')
    } finally { setLoading(false) }
  }

  return (
    <div className="left-panel" style={{ height: '100%' }}>
      <div>
        <div className="section-label">Infrastructure Input</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <button className={`tab-btn ${mode === 'upload' ? 'active' : ''}`} onClick={() => setMode('upload')}>
            📁 Upload File
          </button>
          <button className={`tab-btn ${mode === 'discover' ? 'active' : ''}`} onClick={() => setMode('discover')}>
            🔍 Discover Live
          </button>
        </div>
      </div>

      {mode === 'upload' && (
        <>
          <div
            className={`upload-zone ${dragging ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]) }}
            onClick={() => inputRef.current.click()}
          >
            <input
              ref={inputRef}
              type="file"
              style={{ display: 'none' }}
              accept=".tfstate,.json,.csv,.xlsx,.tf,.log,.yaml,.yml"
              onChange={(e) => handleFile(e.target.files[0])}
            />
            <div className="upload-orbit">
              <span style={{ fontSize: 18 }}>{file ? '✅' : '📁'}</span>
            </div>
            {file ? (
              <>
                <div style={{ fontSize: 13, color: '#34d399', fontFamily: 'JetBrains Mono', fontWeight: 500 }}>{file.name}</div>
                <div style={{ fontSize: 11, color: '#4a6fa5', fontFamily: 'JetBrains Mono', marginTop: 4 }}>{(file.size / 1024).toFixed(1)} KB · click to change</div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>Drop infrastructure file here</div>
                <div style={{ fontSize: 11, color: '#2d4a7a', fontFamily: 'JetBrains Mono' }}>.tfstate · .json · .csv · .xlsx · .tf · .yaml</div>
              </>
            )}
          </div>

          <div>
            <div className="section-label" style={{ marginTop: 12 }}>Migration Target</div>
            <div className="targets-grid">
              {TARGETS.map((t) => (
                <div
                  key={t.value}
                  className={`target-card ${target === t.value ? t.cls : ''}`}
                  onClick={() => setTarget(t.value)}
                >
                  <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: target === t.value ? (t.value === 'gcp' ? '#34d399' : t.value === 'aws' ? '#fb923c' : '#a78bfa') : '#2d4a7a', marginBottom: 4 }}>{t.label}</div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: target === t.value ? '#e2e8f0' : '#4a6fa5' }}>{t.name}</div>
                </div>
              ))}
            </div>
          </div>

          {error && <div style={{ padding: '8px 12px', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, fontSize: 12, color: '#f87171' }}>{error}</div>}

          <button className="btn-primary" onClick={handleSubmit} disabled={loading || !file}>
            {loading ? '⏳ Analyzing···' : '🚀 Analyze Infrastructure'}
          </button>
        </>
      )}

      {mode === 'discover' && (
        <>
          <div>
            <div className="section-label">AWS Region</div>
            <input
              type="text"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              style={{ width: '100%', padding: '10px 14px', borderRadius: 10, background: 'rgba(10,20,50,0.6)', border: '1px solid rgba(99,179,237,0.2)', color: '#e2e8f0', fontFamily: 'JetBrains Mono', fontSize: 13, outline: 'none', marginBottom: 12 }}
            />
          </div>

          {discovered && (
            <div style={{ padding: 14, background: 'rgba(52,211,153,0.05)', border: '1px solid rgba(52,211,153,0.2)', borderRadius: 12, marginBottom: 12 }}>
              <div style={{ fontSize: 28, fontFamily: 'JetBrains Mono', color: '#34d399', fontWeight: 600 }}>{discovered.resources_discovered}</div>
              <div style={{ fontSize: 11, color: '#4a6fa5', fontFamily: 'JetBrains Mono' }}>resources · {region}</div>
              <div style={{ fontSize: 11, color: '#2d4a7a', marginTop: 4 }}>{discovered.resource_types?.length || 0} resource types</div>
              <div>
                <div className="section-label" style={{ marginTop: 12 }}>Analyze discovered infrastructure</div>
                <div className="targets-grid">
                  {TARGETS.map((t) => (
                    <div key={t.value} className={`target-card ${target === t.value ? t.cls : ''}`} onClick={() => setTarget(t.value)}>
                      <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: '#2d4a7a', marginBottom: 4 }}>{t.label}</div>
                      <div style={{ fontSize: 11, fontWeight: 500, color: '#4a6fa5' }}>{t.name}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && <div style={{ padding: '8px 12px', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, fontSize: 12, color: '#f87171', marginBottom: 8 }}>{error}</div>}

          {!discovered ? (
            <button className="btn-primary" onClick={handleDiscover} disabled={loading}>
              {loading ? '⏳ Discovering···' : '🔍 Discover AWS Infrastructure'}
            </button>
          ) : (
            <button className="btn-primary" onClick={handleDiscoverAnalyze} disabled={loading}>
              {loading ? '⏳ Analyzing···' : `🚀 Analyze → ${target.toUpperCase()}`}
            </button>
          )}
        </>
      )}

      <div style={{ marginTop: 'auto', paddingTop: 16 }}>
        <div className="section-label">Quick Actions</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div style={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: '#2d4a7a', padding: '6px 10px', borderRadius: 6, background: 'rgba(10,20,50,0.4)', border: '1px solid rgba(99,179,237,0.06)' }}>
            migration-factory poc infra.tfstate --target gcp
          </div>
          <div style={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: '#2d4a7a', padding: '6px 10px', borderRadius: 6, background: 'rgba(10,20,50,0.4)', border: '1px solid rgba(99,179,237,0.06)' }}>
            GET /api/v1/discover/aws?region=ap-south-1
          </div>
        </div>
      </div>
    </div>
  )
}
