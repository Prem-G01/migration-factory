import { useCallback, useEffect, useState } from "react";
import { deleteRun, getReport, getRuns } from "../api";

const RISK_COLORS = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-red-100 text-red-800",
  critical: "bg-red-200 text-red-900",
};

export default function HistoryPage({ onViewRun }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyRunId, setBusyRunId] = useState(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuns();
      setRuns(data.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)));
    } catch (err) {
      setError(err.message || "Failed to load run history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  async function handleView(runId) {
    setBusyRunId(runId);
    try {
      const report = await getReport(runId);
      onViewRun(runId, report);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load report.");
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleDelete(runId) {
    setBusyRunId(runId);
    try {
      await deleteRun(runId);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete run.");
    } finally {
      setBusyRunId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Run History</h1>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : runs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-12 text-center text-gray-500">
          No previous analyses. Upload a file to get started.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Direction</th>
                <th className="px-4 py-3">Resources</th>
                <th className="px-4 py-3">Risk</th>
                <th className="px-4 py-3">Savings</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="border-b border-gray-100">
                  <td className="px-4 py-3 text-gray-500">{new Date(run.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 font-medium">{run.direction}</td>
                  <td className="px-4 py-3">{run.resources}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${RISK_COLORS[run.risk_level] || "bg-gray-100 text-gray-700"}`}>
                      {run.risk_level}
                    </span>
                  </td>
                  <td className={`px-4 py-3 font-medium ${run.monthly_savings >= 0 ? "text-green-600" : "text-red-600"}`}>
                    ${run.monthly_savings.toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleView(run.run_id)}
                        disabled={busyRunId === run.run_id}
                        className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        View
                      </button>
                      <button
                        onClick={() => handleDelete(run.run_id)}
                        disabled={busyRunId === run.run_id}
                        className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
