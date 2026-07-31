"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ResultsView } from "@/features/results/results-view";
import { StepIndicator, type WizardStepId } from "@/features/analyze/wizard/step-indicator";
import { CloudStep } from "@/features/analyze/wizard/cloud-step";
import { ConfigureStep, type WizardConfig } from "@/features/analyze/wizard/configure-step";
import { UploadStep } from "@/features/analyze/wizard/upload-step";
import { ProgressStep } from "@/features/analyze/wizard/progress-step";
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

  const [step, setStep] = useState<WizardStepId>(runFromQuery ? "results" : "cloud");
  const [activeRunId, setActiveRunId] = useState<string | null>(runFromQuery);
  const [useCaseId, setUseCaseId] = useState<UseCaseId>("aws_to_gcp");
  const [config, setConfig] = useState<WizardConfig>({ region: "us-east-1", environment: "dev", gcpProjectId: "" });
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoverResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const useCase = USE_CASES.find((u) => u.id === useCaseId)!;
  const { stageIndex, start: startStages, clear: clearStages } = usePipelineStages();
  const analyzeFile = useAnalyzeFile();
  const analyzeRawData = useAnalyzeRawData();

  // Deep link from Dashboard's "View" button: /?run=<id>.
  useEffect(() => {
    if (runFromQuery) {
      setActiveRunId(runFromQuery);
      setStep("results");
    }
  }, [runFromQuery]);

  // TopNav's logo/Home button — resets the wizard even when we're
  // already on "/" (a plain route change wouldn't touch this state).
  useEffect(() => {
    const onGoHome = () => startNewAnalysis();
    window.addEventListener("mf:go-home", onGoHome);
    return () => window.removeEventListener("mf:go-home", onGoHome);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    setStep("results");
    router.replace(`/?run=${runId}`);
  };

  const startNewAnalysis = () => {
    setActiveRunId(null);
    setFile(null);
    setDiscovered(null);
    setSubmitError(null);
    setStep("cloud");
    router.replace("/");
  };

  const handleSubmit = async () => {
    setSubmitError(null);
    setStep("progress");
    startStages(getPipelineStages(useCase).length);
    try {
      if (useCase.isDiscover) {
        if (!discovered) {
          setStep("upload");
          return;
        }
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
        setStep("upload");
        return;
      }
      const result = await analyzeFile.mutateAsync({ file, target: useCase.target });
      goToResult(result.run_id);
    } catch (error) {
      clearStages();
      setSubmitError(extractErrorMessage(error));
      setStep("upload");
    }
  };

  const canSubmit = useCase.isDiscover ? discovered !== null : file !== null;

  if (step === "results" && activeRunId) {
    return <ResultsView runId={activeRunId} onNewAnalysis={startNewAnalysis} />;
  }

  return (
    <div className="flex h-full flex-col">
      {step !== "progress" && (
        <div className="animate-fade-up flex justify-center border-b border-[var(--glass-border-soft)] bg-[var(--nav-bg-soft)] py-4">
          <StepIndicator current={step} />
        </div>
      )}

      {step === "cloud" && (
        <CloudStep value={useCaseId} onChange={setUseCaseId} onNext={() => setStep("configure")} />
      )}

      {step === "configure" && (
        <ConfigureStep
          useCaseId={useCaseId}
          value={config}
          onChange={setConfig}
          onNext={() => setStep("upload")}
          onBack={() => setStep("cloud")}
        />
      )}

      {step === "upload" && (
        <UploadStep
          useCase={useCase}
          file={file}
          fileError={fileError}
          onFileSelect={handleFileSelect}
          discovered={discovered}
          onDiscovered={setDiscovered}
          submitError={submitError}
          canSubmit={canSubmit}
          onSubmit={handleSubmit}
          onBack={() => setStep("configure")}
        />
      )}

      {step === "progress" && (
        <ProgressStep stages={getPipelineStages(useCase)} stageIndex={stageIndex} />
      )}
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
