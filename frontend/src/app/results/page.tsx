"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ResultsPage } from "@/features/results/results-page";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

// A dynamic /results/[runId] path segment can't be statically exported —
// Next.js static export requires build-time-known params for every
// dynamic route, but run_id is created at runtime by the backend. Using
// a query param instead keeps this as a single static page (out/results/
// index.html) whose content resolves entirely client-side, same as every
// other data fetch in this app.
function ResultsPageContent() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");

  if (!runId) {
    return <EmptyState icon="⚠️" message="No run specified." />;
  }

  return <ResultsPage runId={runId} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-64 rounded-xl" />}>
      <ResultsPageContent />
    </Suspense>
  );
}
