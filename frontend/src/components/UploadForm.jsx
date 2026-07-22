import { useRef, useState } from "react";
import { analyzeFile } from "../api";

const TARGET_OPTIONS = [
  { value: "gcp", label: "GCP Migration" },
  { value: "aws", label: "AWS Migration" },
  { value: "analyze_only", label: "Analyze Only" },
];

export default function UploadForm({ onResult }) {
  const [file, setFile] = useState(null);
  const [target, setTarget] = useState("gcp");
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(selected) {
    if (!selected) return;
    setFile(selected);
    setError(null);
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    pickFile(dropped);
  }

  function handleDragOver(event) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(event) {
    event.preventDefault();
    setIsDragging(false);
  }

  function handleBrowseChange(event) {
    pickFile(event.target.files?.[0]);
  }

  async function handleAnalyze() {
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await analyzeFile(file, target);
      onResult(result.run_id, result);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : err.message || "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold text-gray-900">Analyze Infrastructure</h1>
      <p className="mb-8 text-gray-500">
        Upload a Terraform state, JSON, or CSV inventory file to assess and plan a cloud migration.
      </p>

      <div
        onClick={() => fileInputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-gray-50 hover:bg-gray-100"
        }`}
      >
        <svg
          className="mb-4 h-12 w-12 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"
          />
        </svg>
        <p className="font-medium text-gray-700">Drop .tfstate .json .csv here</p>
        <p className="mt-1 text-sm text-gray-400">or click to browse files</p>
        {file && (
          <p className="mt-4 rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-700">
            {file.name}
          </p>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".tfstate,.json,.csv"
          className="hidden"
          onChange={handleBrowseChange}
        />
      </div>

      <div className="mt-6">
        <label className="mb-1 block text-sm font-medium text-gray-700" htmlFor="target-select">
          Target
        </label>
        <select
          id="target-select"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {TARGET_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <button
        onClick={handleAnalyze}
        disabled={loading}
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-6 py-4 text-lg font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
      >
        {loading ? (
          <>
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Analyzing…
          </>
        ) : (
          "Analyze Infrastructure"
        )}
      </button>
    </div>
  );
}
