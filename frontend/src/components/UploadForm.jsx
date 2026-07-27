import { useState, useRef, useEffect } from 'react'
import { analyzeFile, analyzeRawData, discoverAws } from '../api'

const TARGETS = [
  { value: 'gcp', direction: 'AWS → GCP', label: 'Migrate to GCP', accent: 'cyan' },
  { value: 'aws', direction: 'GCP → AWS', label: 'Migrate to AWS', accent: 'orange' },
  { value: 'analyze_only', direction: 'ANALYZE', label: 'Analyze Only', accent: 'gray' },
]

const ACCENT_CLASSES = {
  cyan: { border: 'border-cyan', bar: 'bg-cyan', label: 'text-cyan' },
  orange: { border: 'border-orange', bar: 'bg-orange', label: 'text-orange' },
  gray: { border: 'border-text-muted', bar: 'bg-[#8B949E]', label: 'text-text-secondary' },
}

function AnalyzingDots() {
  const [dots, setDots] = useState('')
  useEffect(() => {
    const id = setInterval(() => setDots((d) => (d.length >= 3 ? '' : d + '.')), 350)
    return () => clearInterval(id)
  }, [])
  return <span className="mono">Analyzing{dots}</span>
}

export default function UploadForm({ onResult }) {
  const [mode, setMode] = useState('upload') // 'upload' | 'discover'
  const [file, setFile] = useState(null)
  const [target, setTarget] = useState('gcp')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [justDropped, setJustDropped] = useState(false)
  const inputRef = useRef()

  const [region, setRegion] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [discovered, setDiscovered] = useState(null)

  const handleFile = (f) => {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    const allowed = ['tfstate', 'json', 'csv', 'xlsx', 'tf', 'log', 'yaml', 'yml']
    if (!allowed.includes(ext)) {
      setError(`Unsupported format .${ext}. Use: ${allowed.join(', ')}`)
      return
    }
    setFile(f)
    setError('')
    setJustDropped(true)
    setTimeout(() => setJustDropped(false), 650)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const handleSubmit = async () => {
    if (!file) { setError('Please select a file first'); return }
    setLoading(true)
    setError('')
    try {
      const result = await analyzeFile(file, target)
      onResult(result)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const handleDiscover = async () => {
    setDiscovering(true)
    setError('')
    setDiscovered(null)
    try {
      const result = await discoverAws(region || 'us-east-1')
      setDiscovered(result)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Discovery failed')
    } finally {
      setDiscovering(false)
    }
  }

  const handleAnalyzeDiscovered = async () => {
    if (!discovered?.raw_data) return
    setLoading(true)
    setError('')
    try {
      const result = await analyzeRawData(discovered.raw_data, target)
      onResult(result)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const ready = mode === 'discover' ? !!discovered : !!file
  const onSubmit = mode === 'discover' ? handleAnalyzeDiscovered : handleSubmit

  return (
    <div className="min-h-screen bg-void flex items-center justify-center p-6">
      <div className="w-full max-w-[520px]">
        {/* Header */}
        <div className="flex flex-col items-center mb-8 animate-fade-up">
          <div className="flex items-center gap-2.5 mb-2">
            <span
              className="w-7 h-7 rounded flex items-center justify-center text-sm"
              style={{ background: 'linear-gradient(135deg, #00E5FF33, #00E5FF11)', border: '1px solid #00E5FF44' }}
            >
              🏭
            </span>
            <h1 className="text-lg font-semibold text-text-primary tracking-tight">Migration Factory</h1>
          </div>
          <p className="mono text-[11px] text-text-muted tracking-wide">
            aws → gcp · gcp → aws · analyze
          </p>
        </div>

        {/* Card */}
        <div className="bg-surface border border-border rounded-xl overflow-hidden animate-fade-up">
          {/* Tabs */}
          <div className="flex border-b border-border">
            <button
              onClick={() => setMode('upload')}
              className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors
                ${mode === 'upload' ? 'border-cyan text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'}`}
            >
              Upload File
            </button>
            <button
              onClick={() => setMode('discover')}
              className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors
                ${mode === 'discover' ? 'border-cyan text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'}`}
            >
              Discover Live
            </button>
          </div>

          <div className="p-6">
            {mode === 'upload' ? (
              <div className={`rounded-xl mb-6 ${justDropped ? 'pulse-once' : ''}`}>
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => inputRef.current.click()}
                  className={`animated-border rounded-xl p-10 text-center cursor-pointer transition-all
                    ${dragging ? 'bg-cyan-10' : 'hover:opacity-90'}`}
                  style={dragging ? { background: 'linear-gradient(#0d1a1f, #0d1a1f) padding-box, conic-gradient(from var(--angle), transparent 20%, var(--accent-cyan), transparent 80%) border-box' } : undefined}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    className="hidden"
                    accept=".tfstate,.json,.csv,.xlsx,.tf,.log,.yaml,.yml"
                    onChange={(e) => handleFile(e.target.files[0])}
                  />
                  <div className="text-4xl mb-3 text-text-muted">{file ? '✅' : '📁'}</div>
                  {file ? (
                    <div>
                      <p className="mono text-cyan text-sm">{file.name}</p>
                      <p className="text-text-secondary text-xs mt-1">
                        {(file.size / 1024).toFixed(1)} KB — click to change
                      </p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-text-secondary font-medium">Drop infrastructure file here</p>
                      <p className="mono text-text-muted text-[11px] mt-1">
                        .tfstate .json .csv .xlsx .tf
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mb-6">
                <label className="block text-text-muted text-[11px] mono uppercase tracking-wider mb-2">
                  AWS Region
                </label>
                <input
                  type="text"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  placeholder="us-east-1"
                  className="mono w-full px-4 py-3 rounded-lg bg-raised border border-border text-text-primary
                    placeholder-text-muted mb-4 focus:outline-none focus:border-cyan transition-colors"
                />
                <button
                  onClick={handleDiscover}
                  disabled={discovering}
                  className="w-full py-3 rounded-lg font-medium transition-all border"
                  style={
                    discovering
                      ? { background: 'var(--bg-raised)', color: 'var(--text-muted)', borderColor: 'var(--bg-border)', cursor: 'not-allowed' }
                      : { background: 'linear-gradient(135deg, #00E5FF22, #00E5FF11)', borderColor: '#00E5FF44', color: '#00E5FF' }
                  }
                >
                  {discovering ? <AnalyzingDots /> : '🔎 Discover Infrastructure'}
                </button>

                {discovered && (
                  <div className="mt-5 p-5 rounded-xl bg-raised border border-border text-center animate-count">
                    <div className="mono text-cyan text-4xl font-medium">{discovered.resources_discovered}</div>
                    <div className="text-text-secondary text-xs mt-1">resources discovered</div>
                    <div className="mono text-text-muted text-[11px] mt-2">
                      {discovered.region} · {discovered.resource_types?.length ?? 0} resource types
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Target selector */}
            <div className="mb-6">
              <label className="block text-text-muted text-[11px] mono uppercase tracking-wider mb-3">
                Migration Target
              </label>
              <div className="grid grid-cols-3 gap-2">
                {TARGETS.map((t) => {
                  const a = ACCENT_CLASSES[t.accent]
                  const selected = target === t.value
                  return (
                    <button
                      key={t.value}
                      onClick={() => setTarget(t.value)}
                      className={`relative overflow-hidden text-left rounded-lg border p-3 transition-all
                        ${selected ? `${a.border} bg-raised` : 'border-border bg-raised hover:border-text-muted'}`}
                    >
                      {selected && <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${a.bar}`} />}
                      <div className={`mono text-[10px] tracking-wide ${selected ? a.label : 'text-text-muted'}`}>
                        {t.direction}
                      </div>
                      <div className="text-[13px] font-semibold text-text-primary mt-1 leading-tight">
                        {t.label}
                      </div>
                      <div className="text-xs mt-1.5 opacity-70">
                        {t.value === 'gcp' ? '☁️ → 🔶' : t.value === 'aws' ? '🔶 → ☁️' : '🔍'}
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-10 border border-red/30 rounded-lg text-red text-sm">
                {error}
              </div>
            )}

            <button
              onClick={onSubmit}
              disabled={loading || !ready}
              className="w-full py-4 rounded-lg font-semibold transition-all border"
              style={
                loading || !ready
                  ? { background: 'var(--bg-raised)', color: 'var(--text-muted)', borderColor: 'var(--bg-border)', cursor: 'not-allowed' }
                  : { background: 'linear-gradient(135deg, #00E5FF22, #00E5FF11)', borderColor: '#00E5FF44', color: '#00E5FF' }
              }
              onMouseEnter={(e) => { if (!loading && ready) { e.currentTarget.style.borderColor = '#00E5FF'; e.currentTarget.style.color = '#E6EDF3' } }}
              onMouseLeave={(e) => { if (!loading && ready) { e.currentTarget.style.borderColor = '#00E5FF44'; e.currentTarget.style.color = '#00E5FF' } }}
            >
              {loading ? <AnalyzingDots /> : mode === 'discover' ? '🚀 Analyze →' : '🚀 Analyze Infrastructure'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
