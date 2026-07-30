"use client";

import { Button } from "@/components/ui/button";
import { Dropzone } from "@/features/analyze/dropzone";
import { DiscoverPanel } from "@/features/analyze/discover-panel";
import type { UseCaseOption } from "@/constants/upload";
import type { DiscoverResponse } from "@/types/migration";

interface UploadStepProps {
  useCase: UseCaseOption;
  file: File | null;
  fileError: string | null;
  onFileSelect: (file: File) => void;
  discovered: DiscoverResponse | null;
  onDiscovered: (data: DiscoverResponse) => void;
  submitError: string | null;
  canSubmit: boolean;
  onSubmit: () => void;
  onBack: () => void;
}

export function UploadStep({
  useCase,
  file,
  fileError,
  onFileSelect,
  discovered,
  onDiscovered,
  submitError,
  canSubmit,
  onSubmit,
  onBack,
}: UploadStepProps) {
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 p-6">
      <div className="animate-fade-up text-center">
        <h1 className="text-3xl font-bold">
          {useCase.isDiscover ? "Discover infrastructure" : "Upload your source"}
        </h1>
        <p className="mt-2 text-muted-foreground">
          {useCase.isDiscover
            ? "Live AWS discovery — no file needed."
            : "Terraform state, HCL, or an inventory export."}
        </p>
      </div>

      <div className="animate-fade-up">
        {useCase.isDiscover ? (
          <DiscoverPanel discovered={discovered} onDiscovered={onDiscovered} />
        ) : (
          <Dropzone file={file} onFileSelect={onFileSelect} error={fileError} />
        )}
      </div>

      {submitError && (
        <p className="animate-fade-up rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {submitError}
        </p>
      )}

      <div className="animate-fade-up flex gap-2">
        <Button variant="outline" onClick={onBack} className="h-12 flex-1 rounded-xl">
          ← Back
        </Button>
        <Button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="h-12 flex-[2] gap-2 rounded-xl bg-gradient-to-r from-[var(--cyan)] to-[#0066ff] text-base font-bold text-black disabled:from-[var(--dim)] disabled:to-[var(--dim)] disabled:text-muted-foreground"
        >
          🚀 Analyze Infrastructure
        </Button>
      </div>
    </div>
  );
}
