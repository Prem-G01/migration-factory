"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/features/analyze/dropzone";
import { UseCaseSelector } from "@/features/analyze/use-case-selector";
import { DiscoverPanel } from "@/features/analyze/discover-panel";
import { PipelineProgress } from "@/features/analyze/pipeline-progress";
import { ReadyState } from "@/features/analyze/ready-state";
import { ResultsView } from "@/features/results/results-view";
import { ALLOWED_EXTENSIONS, USE_CASES, getPipelineStages, type UseCaseId } from "@/constants/upload";
import { usePipelineStages } from "@/hooks/use-pipeline-stages";
import { useAnalyzeFile, useAnalyzeRawData } from "@/hooks/use-migration-queries";
import { ApiError } from "@/services/migration-api";
import type { DiscoverResponse } from "@/types/migration";

function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

function AnalyzePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const runFromQuery = searchParams.get("run");

  const [activeRunId, setActiveRunId] = useState<string | null>(runFromQuery);
  const [useCaseId, setUseCaseId] = useState<UseCaseId>("aws_to_gcp");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoverResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const useCase = USE_CASES.find((u) => u.id === useCaseId)!;
  const { stageIndex, start: startStages, clear: clearStages } = usePipelineStages();
  const analyzeFile = useAnalyzeFile();
  const analyzeRawData = useAnalyzeRawData();
  const loading = analyzeFile.isPending || analyzeRawData.isPending;

  // Deep link from Dashboard's "View" button: /?run=<id>.
  useEffect(() => {
    if (runFromQuery) setActiveRunId(runFromQuery);
  }, [runFromQuery]);

  const handleFileSelect = (selected: File) => {
    const ext = selected.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED_EXTENSIONS.includes(ext as (typeof ALLOWED_EXTENSIONS)[number])) {
      setFileError(`.${ext} not supported. Use: ${ALLOWED_EXTENSIONS.join(", ")}`);
      return;
    }
    setFile(selected);
    setFileError(null);
  };

  const goToResult = (runId: string) => {
    clearStages();
    setActiveRunId(runId);
    router.replace(`/?run=${runId}`);
  };

  const startNewAnalysis = () => {
    setActiveRunId(null);
    setFile(null);
    setDiscovered(null);
    setSubmitError(null);
    router.replace("/");
  };

  const handleSubmit = async () => {
    setSubmitError(null);
    startStages(getPipelineStages(useCase).length);
    try {
      if (useCase.isDiscover) {
        if (!discovered) return;
        const result = await analyzeRawData.mutateAsync({
          rawData: discovered.raw_data,
          target: useCase.target,
        });
        goToResult(result.run_id);
        return;
      }
      if (!file) {
        setFileError("Drop a file first");
        clearStages();
        return;
      }
      const result = await analyzeFile.mutateAsync({ file, target: useCase.target });
      goToResult(result.run_id);
    } catch (error) {
      clearStages();
      setSubmitError(extractErrorMessage(error));
    }
  };

  const canSubmit = useCase.isDiscover ? discovered !== null : file !== null;

  return (
    <div className="grid h-full grid-cols-[400px_1fr]">
      {/* Left: input panel */}
      <div className="flex flex-col gap-5 overflow-y-auto border-r border-white/5 bg-black/10 p-6">
        <h1 className="animate-fade-up text-2xl font-bold">Analyze Infrastructure</h1>

        <UseCaseSelector value={useCaseId} onChange={setUseCaseId} />

        {useCase.isDiscover ? (
          <DiscoverPanel discovered={discovered} onDiscovered={setDiscovered} />
        ) : (
          <Dropzone file={file} onFileSelect={handleFileSelect} error={fileError} />
        )}

        {loading && (
          <PipelineProgress stages={getPipelineStages(useCase)} stageIndex={stageIndex} />
        )}

        {submitError && (
          <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {submitError}
          </p>
        )}

        <Button
          onClick={handleSubmit}
          disabled={loading || !canSubmit}
          className="h-14 gap-2 rounded-xl bg-gradient-to-r from-[var(--cyan)] to-[#0066ff] text-lg font-bold text-black disabled:from-[var(--dim)] disabled:to-[var(--dim)] disabled:text-muted-foreground"
        >
          {loading ? (
            <>
              ⏳ Analyzing
              <span className="flex gap-0.5">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="inline-block size-1.5 rounded-full bg-current"
                    style={{ animation: `bounceDots 1.2s ease-in-out ${d * 0.15}s infinite` }}
                  />
                ))}
              </span>
            </>
          ) : (
            "🚀 Analyze Infrastructure"
          )}
        </Button>
      </div>

      {/* Right: empty state or results */}
      <div className="overflow-hidden">
        {activeRunId ? (
          <ResultsView runId={activeRunId} onNewAnalysis={startNewAnalysis} />
        ) : (
          <ReadyState />
        )}
      </div>
    </div>
  );
}

export function AnalyzePage() {
  return (
    <Suspense fallback={<div className="h-full" />}>
      <AnalyzePageInner />
    </Suspense>
  );
}
