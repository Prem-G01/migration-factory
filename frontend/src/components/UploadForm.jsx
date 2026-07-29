import { useEffect, useRef, useState } from 'react'
import { analyzeFile, analyzeRawData, discoverAws } from '../api'

const TARGETS = [
  { value: 'gcp', label: 'AWS → GCP', name: 'Migrate to GCP', cls: 'active-aws' },
  { value: 'aws', label: 'GCP → AWS', name: 'Migrate to AWS', cls: 'active-gcp' },
  { value: 'analyze_only', label: 'Analysis', name: 'Analyze Only', cls: 'active-analyze' },
]

const TARGET_DESCRIPTIONS = {
  gcp: 'Generate GCP Terraform from AWS infrastructure',
  aws: 'Generate AWS Terraform from GCP infrastructure',
  analyze_only: 'Security, compliance and cost analysis without migration',
}

const FILE_ICONS = {
  tfstate: '🗺️', json: '🔧', csv: '📊', xlsx: '📈',
  tf: '📄', log: '📜', yaml: '📄', yml: '📄',
}

const PARSE_HINTS = {
  tfstate: '.tfstate detected — Terraform state format',
  json: '.json detected — JSON inventory format',
  csv: '.csv detected — CSV inventory format',
  xlsx: '.xlsx detected — Excel inventory format',
  tf: '.tf detected — Terraform HCL format',
  log: '.log detected — Terraform plan log format',
  yaml: '.yaml detected — YAML inventory format',
  yml: '.yml detected — YAML inventory format',
}

const ALL_STAGES = ['Parsing infrastructure', 'Translating resources', 'Assessing complexity', 'Generating Terraform']
// analyze_only mode never generates Terraform server-side, so the simulated
// stage list shouldn't promise a step that won't actually happen.
const getStages = (target) => (target === 'analyze_only' ? ALL_STAGES.slice(0, 3) : ALL_STAGES)

// import.meta.env.BASE_URL (not a hardcoded "/") so these still resolve
// correctly once deployed under a subpath, e.g. GitHub Pages'
// /migration-factory/ base — a bare "/samples/..." would 404 there.
const SAMPLES = [
  { label: 'Try AWS sample', url: `${import.meta.env.BASE_URL}samples/aws-sample.tfstate`, filename: 'aws-sample.tfstate', target: 'gcp' },
  { label: 'Try GCP sample', url: `${import.meta.env.BASE_URL}samples/gcp-sample.tfstate`, filename: 'gcp-sample.tfstate', target: 'aws' },
  { label: 'Try complex estate', url: `${import.meta.env.BASE_URL}samples/complex-estate.tfstate`, filename: 'complex-estate.tfstate', target: 'gcp' },
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
  const [hoveredTarget, setHoveredTarget] = useState(null)
  const [stageIndex, setStageIndex] = useState(0)
  const [loadingSample, setLoadingSample] = useState(null)
  const inputRef = useRef()
  const stageTimersRef = useRef([])

  const clearStageTimers = () => {
    stageTimersRef.current.forEach(clearTimeout)
    stageTimersRef.current = []
  }
  useEffect(() => clearStageTimers, [])

  // Cosmetic only — there's no real progress channel from the API, so this
  // just gives the ~1s wait some visual life. The real result always wins:
  // handleSubmit clears these timers and calls onResult() the moment the
  // actual API response lands, it never waits for the simulation to finish.
  const runStageSimulation = (count) => {
    clearStageTimers()
    setStageIndex(0)
    const step = 4000 / count
    for (let i = 1; i < count; i++) {
      stageTimersRef.current.push(setTimeout(() => setStageIndex(i), Math.round(step * i)))
    }
  }

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
    runStageSimulation(getStages(target).length)
    try {
      const result = await analyzeFile(file, target)
      onResult(result)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Analysis failed')
    } finally {
      clearStageTimers()
      setLoading(false)
    }
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

  const loadSample = async (sample) => {
    setLoadingSample(sample.url); setError('')
    try {
      const resp = await fetch(sample.url)
      if (!resp.ok) throw new Error(`Could not load sample (HTTP ${resp.status})`)
      const blob = await resp.blob()
      setMode('upload')
      handleFile(new File([blob], sample.filename))
      setTarget(sample.target)
    } catch (e) {
      setError(e.message || 'Failed to load sample file')
    } finally {
      setLoadingSample(null)
    }
  }

  const fileExt = file?.name.split('.').pop().toLowerCase()

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
              <span style={{ fontSize: 18 }}>{file ? (FILE_ICONS[fileExt] || '✅') : '📁'}</span>
            </div>
            {file ? (
              <>
                <div style={{ fontSize: 13, color: '#34d399', fontFamily: 'JetBrains Mono', fontWeight: 500 }}>{file.name}</div>
                <div style={{ fontSize: 11, color: '#4a6fa5', fontFamily: 'JetBrains Mono', marginTop: 4 }}>{(file.size / 1024).toFixed(1)} KB · click to change</div>
                <span style={{ display: 'inline-block', marginTop: 8, padding: '2px 10px', borderRadius: 20, fontSize: 10, fontFamily: 'JetBrains Mono', background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.25)', color: '#34d399' }}>
                  ● Ready to analyze
                </span>
                {PARSE_HINTS[fileExt] && (
                  <div style={{ fontSize: 10, color: '#2d4a7a', fontFamily: 'JetBrains Mono', marginTop: 8 }}>{PARSE_HINTS[fileExt]}</div>
                )}
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
                  onMouseEnter={() => setHoveredTarget(t.value)}
                  onMouseLeave={() => setHoveredTarget((h) => (h === t.value ? null : h))}
                >
                  <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: target === t.value ? (t.value === 'gcp' ? '#34d399' : t.value === 'aws' ? '#fb923c' : '#a78bfa') : '#2d4a7a', marginBottom: 4 }}>{t.label}</div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: target === t.value ? '#e2e8f0' : '#4a6fa5' }}>{t.name}</div>
                </div>
              ))}
            </div>
            <div style={{ minHeight: 30, marginTop: 6 }}>
              {hoveredTarget && (
                <div style={{ padding: '6px 10px', background: 'rgba(10,20,50,0.7)', border: '1px solid rgba(99,179,237,0.15)', borderRadius: 8, fontSize: 11, color: '#94a3b8', lineHeight: 1.4 }}>
                  {TARGET_DESCRIPTIONS[hoveredTarget]}
                </div>
              )}
            </div>
          </div>

          {error && <div style={{ padding: '8px 12px', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, fontSize: 12, color: '#f87171' }}>{error}</div>}

          {loading && (
            <div style={{ padding: '10px 12px', background: 'rgba(10,20,50,0.5)', border: '1px solid rgba(99,179,237,0.1)', borderRadius: 10 }}>
              {getStages(target).map((label, i) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontSize: 11, fontFamily: 'JetBrains Mono', color: i < stageIndex ? '#34d399' : i === stageIndex ? '#60a5fa' : '#2d4a7a' }}>
                  <span style={{ width: 12, textAlign: 'center' }}>{i < stageIndex ? '✓' : i === stageIndex ? '⏳' : '○'}</span>
                  <span>{label}{i === stageIndex ? '···' : ''}</span>
                </div>
              ))}
            </div>
          )}

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
        <div className="section-label">Quick Start</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {SAMPLES.map((sample) => (
            <button
              key={sample.url}
              className="sample-btn"
              onClick={() => loadSample(sample)}
              disabled={loadingSample !== null}
            >
              {loadingSample === sample.url ? '⏳ loading···' : sample.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
