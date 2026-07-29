"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/features/upload/dropzone";
import { TargetSelector } from "@/features/upload/target-selector";
import { DiscoverPanel } from "@/features/upload/discover-panel";
import { PipelineProgress } from "@/features/upload/pipeline-progress";
import { ALLOWED_EXTENSIONS, SAMPLE_FILES, getPipelineStages } from "@/constants/upload";
import { usePipelineStages } from "@/hooks/use-pipeline-stages";
import { useAnalyzeFile, useAnalyzeRawData } from "@/hooks/use-migration-queries";
import { ApiError } from "@/services/migration-api";
import type { DiscoverResponse, MigrationTarget } from "@/types/migration";

type Mode = "upload" | "discover";

function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

export function UploadPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [target, setTarget] = useState<MigrationTarget>("gcp");
  const [discovered, setDiscovered] = useState<DiscoverResponse | null>(null);
  const [loadingSample, setLoadingSample] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { stageIndex, start: startStages, clear: clearStages } = usePipelineStages();
  const analyzeFile = useAnalyzeFile();
  const analyzeRawData = useAnalyzeRawData();

  const loading = analyzeFile.isPending || analyzeRawData.isPending;

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
    router.push(`/results?run=${runId}`);
  };

  const handleSubmit = async () => {
    if (!file) {
      setFileError("Drop a file first");
      return;
    }
    setSubmitError(null);
    startStages(getPipelineStages(target).length);
    try {
      const result = await analyzeFile.mutateAsync({ file, target });
      goToResult(result.run_id);
    } catch (error) {
      clearStages();
      setSubmitError(extractErrorMessage(error));
    }
  };

  const handleAnalyzeDiscovered = async () => {
    if (!discovered) return;
    setSubmitError(null);
    startStages(getPipelineStages(target).length);
    try {
      const result = await analyzeRawData.mutateAsync({
        rawData: discovered.raw_data,
        target,
      });
      goToResult(result.run_id);
    } catch (error) {
      clearStages();
      setSubmitError(extractErrorMessage(error));
    }
  };

  const loadSample = async (sample: (typeof SAMPLE_FILES)[number]) => {
    setLoadingSample(sample.url);
    setSubmitError(null);
    try {
      const response = await fetch(sample.url);
      if (!response.ok) throw new Error(`Could not load sample (HTTP ${response.status})`);
      const blob = await response.blob();
      setMode("upload");
      handleFileSelect(new File([blob], sample.filename));
      setTarget(sample.target);
    } catch (error) {
      setSubmitError(extractErrorMessage(error));
    } finally {
      setLoadingSample(null);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-xl flex-col justify-center gap-6 px-6 py-10">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className="text-xl font-semibold tracking-tight">
          Analyze your infrastructure
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          aws → gcp · gcp → aws · analyze
        </p>
      </motion.div>

      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-1">
        <div className="grid grid-cols-2 gap-1 p-1">
          <button
            onClick={() => setMode("upload")}
            className={`rounded-lg py-2 text-sm font-medium transition-colors ${
              mode === "upload"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            📁 Upload File
          </button>
          <button
            onClick={() => setMode("discover")}
            className={`rounded-lg py-2 text-sm font-medium transition-colors ${
              mode === "discover"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            🔍 Discover Live
          </button>
        </div>

        <div className="flex flex-col gap-4 p-4 pt-2">
          {mode === "upload" ? (
            <>
              <Dropzone file={file} onFileSelect={handleFileSelect} error={fileError} />
              <TargetSelector value={target} onChange={setTarget} />
              {loading && (
                <PipelineProgress stages={getPipelineStages(target)} stageIndex={stageIndex} />
              )}
              {submitError && (
                <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                  {submitError}
                </p>
              )}
              <Button onClick={handleSubmit} disabled={loading || !file} className="h-11">
                {loading ? "⏳ Analyzing···" : "🚀 Analyze Infrastructure"}
              </Button>
            </>
          ) : (
            <>
              <DiscoverPanel
                target={target}
                onTargetChange={setTarget}
                discovered={discovered}
                onDiscovered={setDiscovered}
              />
              {discovered && (
                <>
                  {loading && (
                    <PipelineProgress
                      stages={getPipelineStages(target)}
                      stageIndex={stageIndex}
                    />
                  )}
                  {submitError && (
                    <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                      {submitError}
                    </p>
                  )}
                  <Button onClick={handleAnalyzeDiscovered} disabled={loading} className="h-11">
                    {loading ? "⏳ Analyzing···" : `🚀 Analyze → ${target.toUpperCase()}`}
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div>
        <div className="mb-2 text-center font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
          Quick Start
        </div>
        <div className="flex flex-col gap-1.5">
          {SAMPLE_FILES.map((sample) => (
            <button
              key={sample.url}
              onClick={() => loadSample(sample)}
              disabled={loadingSample !== null}
              className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-left font-mono text-xs text-muted-foreground transition-colors hover:border-white/20 hover:text-foreground disabled:opacity-50"
            >
              {loadingSample === sample.url ? "⏳ loading···" : sample.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
