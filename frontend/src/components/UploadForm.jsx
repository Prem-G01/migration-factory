import { useState, useRef } from 'react'
import { analyzeFile, analyzeRawData, discoverAws } from '../api'

const TARGETS = [
  { value: 'gcp', label: '☁️ Migrate to GCP', desc: 'AWS → GCP' },
  { value: 'aws', label: '🔶 Migrate to AWS', desc: 'GCP → AWS' },
  { value: 'analyze_only', label: '🔍 Analyze Only', desc: 'No migration' },
]

export default function UploadForm({ onResult }) {
  const [mode, setMode] = useState('upload') // 'upload' | 'discover'
  const [file, setFile] = useState(null)
  const [target, setTarget] = useState('gcp')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

  const [region, setRegion] = useState('us-east-1')
  const [discovering, setDiscovering] = useState(false)
  const [discovered, setDiscovered] = useState(null)

  const handleDiscover = async () => {
    setDiscovering(true)
    setError('')
    setDiscovered(null)
    try {
      const result = await discoverAws(region)
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

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            🏭 Migration Factory
          </h1>
          <p className="text-gray-400">
            AI-Powered Multi-Cloud Infrastructure Migration
          </p>
        </div>

        <div className="bg-gray-900 rounded-2xl p-8 shadow-xl border border-gray-800">
          {/* Mode toggle */}
          <div className="grid grid-cols-2 gap-2 mb-6 p-1 bg-gray-800 rounded-xl">
            <button
              onClick={() => setMode('upload')}
              className={`py-2 rounded-lg text-sm font-medium transition-all
                ${mode === 'upload' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              📁 Upload File
            </button>
            <button
              onClick={() => setMode('discover')}
              className={`py-2 rounded-lg text-sm font-medium transition-all
                ${mode === 'discover' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              🔎 Discover Live
            </button>
          </div>

          {mode === 'discover' ? (
            <div className="mb-6">
              <label className="block text-gray-400 text-sm font-medium mb-3">
                AWS Region
              </label>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="us-east-1"
                className="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white
                  placeholder-gray-500 mb-4 focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={handleDiscover}
                disabled={discovering}
                className="w-full py-3 rounded-xl font-semibold text-white transition-all
                  bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500"
              >
                {discovering ? '⏳ Discovering...' : '🔎 Discover AWS Infrastructure'}
              </button>

              {discovered && (
                <div className="mt-4 p-4 rounded-xl bg-gray-800 border border-gray-700">
                  <p className="text-white font-medium">
                    Found {discovered.resources_discovered} resources in {discovered.region}
                  </p>
                  <p className="text-gray-400 text-sm mt-1">
                    {discovered.resource_types?.join(', ')}
                  </p>
                </div>
              )}
            </div>
          ) : (
          /* Drop zone */
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current.click()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all mb-6
              ${dragging ? 'border-blue-400 bg-blue-950' : 'border-gray-700 hover:border-gray-500 hover:bg-gray-800'}`}
          >
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept=".tfstate,.json,.csv,.xlsx,.tf,.log,.yaml,.yml"
              onChange={(e) => handleFile(e.target.files[0])}
            />
            <div className="text-4xl mb-3">
              {file ? '✅' : '📁'}
            </div>
            {file ? (
              <div>
                <p className="text-white font-medium">{file.name}</p>
                <p className="text-gray-400 text-sm mt-1">
                  {(file.size / 1024).toFixed(1)} KB — click to change
                </p>
              </div>
            ) : (
              <div>
                <p className="text-gray-300 font-medium">
                  Drop your infrastructure file here
                </p>
                <p className="text-gray-500 text-sm mt-1">
                  .tfstate .json .csv .xlsx .tf .yaml
                </p>
              </div>
            )}
          </div>
          )}

          {/* Target selector */}
          <div className="mb-6">
            <label className="block text-gray-400 text-sm font-medium mb-3">
              Migration Target
            </label>
            <div className="grid grid-cols-3 gap-3">
              {TARGETS.map(t => (
                <button
                  key={t.value}
                  onClick={() => setTarget(t.value)}
                  className={`p-3 rounded-xl border text-sm font-medium transition-all text-left
                    ${target === t.value
                      ? 'border-blue-500 bg-blue-900 text-white'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-500'}`}
                >
                  <div>{t.label}</div>
                  <div className="text-xs opacity-70 mt-1">{t.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-red-900 border border-red-700 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={mode === 'discover' ? handleAnalyzeDiscovered : handleSubmit}
            disabled={loading || (mode === 'discover' ? !discovered : !file)}
            className="w-full py-4 rounded-xl font-semibold text-white transition-all
              bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
              disabled:text-gray-500 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10"
                    stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor"
                    d="M4 12a8 8 0 018-8v8z"/>
                </svg>
                Analyzing infrastructure...
              </span>
            ) : mode === 'discover' && discovered ? (
              `🚀 Analyze ${discovered.resources_discovered} Resources → ${target === 'gcp' ? 'GCP' : target === 'aws' ? 'AWS' : 'Report'}`
            ) : (
              '🚀 Analyze Infrastructure'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
