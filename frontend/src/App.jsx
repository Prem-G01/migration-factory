import { useState } from "react";
import UploadForm from "./components/UploadForm";
import ResultsDashboard from "./components/ResultsDashboard";
import HistoryPage from "./components/HistoryPage";

export default function App() {
  const [page, setPage] = useState("upload");
  const [runId, setRunId] = useState(null);
  const [report, setReport] = useState(null);

  function handleResult(newRunId, newReport) {
    setRunId(newRunId);
    setReport(newReport);
    setPage("results");
  }

  function handleViewRun(existingRunId, existingReport) {
    setRunId(existingRunId);
    setReport(existingReport);
    setPage("results");
  }

  function handleNewAnalysis() {
    setRunId(null);
    setReport(null);
    setPage("upload");
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <span className="text-lg font-bold text-gray-900">Migration Factory</span>
          <div className="flex gap-2">
            <NavLink label="Analyze" active={page === "upload" || page === "results"} onClick={handleNewAnalysis} />
            <NavLink label="History" active={page === "history"} onClick={() => setPage("history")} />
          </div>
        </div>
      </nav>

      {page === "upload" && <UploadForm onResult={handleResult} />}
      {page === "results" && report && (
        <ResultsDashboard report={report} runId={runId} onNewAnalysis={handleNewAnalysis} />
      )}
      {page === "history" && <HistoryPage onViewRun={handleViewRun} />}
    </div>
  );
}

function NavLink({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
        active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-100"
      }`}
    >
      {label}
    </button>
  );
}
