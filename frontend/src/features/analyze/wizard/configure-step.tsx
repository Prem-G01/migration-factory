"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { UseCaseId } from "@/constants/upload";

const AWS_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1", "ap-southeast-1"];
const GCP_REGIONS = ["us-central1", "us-east1", "europe-west1", "asia-south1", "asia-southeast1"];
const ENVIRONMENTS = ["dev", "staging", "prod"] as const;

export interface WizardConfig {
  region: string;
  environment: (typeof ENVIRONMENTS)[number];
  gcpProjectId: string;
}

interface ConfigureStepProps {
  useCaseId: UseCaseId;
  value: WizardConfig;
  onChange: (config: WizardConfig) => void;
  onNext: () => void;
  onBack: () => void;
}

function fieldLabelClass() {
  return "mb-2 block font-mono text-xs tracking-wider text-muted-foreground uppercase";
}

export function ConfigureStep({ useCaseId, value, onChange, onNext, onBack }: ConfigureStepProps) {
  const sourceIsGcp = useCaseId === "gcp_to_aws" || useCaseId === "gcp_analysis";
  const involvesGcp = sourceIsGcp || useCaseId === "aws_to_gcp";
  const regions = sourceIsGcp ? GCP_REGIONS : AWS_REGIONS;

  // Switching AWS<->GCP mid-wizard swaps this list out from under the
  // picked value (e.g. "us-east-1" isn't a GCP region) — keep it in sync.
  useEffect(() => {
    if (!regions.includes(value.region)) {
      onChange({ ...value, region: regions[0] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regions]);

  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 p-6">
      <div className="animate-fade-up text-center">
        <h1 className="text-3xl font-bold">Configure</h1>
        <p className="mt-2 text-muted-foreground">Set the target region and environment.</p>
      </div>

      <GlassCard hoverElevate={false} className="animate-fade-up flex flex-col gap-4">
        <div>
          <label className={fieldLabelClass()}>{sourceIsGcp ? "GCP Region" : "AWS Region"}</label>
          <Select
            value={value.region}
            onValueChange={(region: string | null) => region && onChange({ ...value, region })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {regions.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {involvesGcp && (
          <div>
            <label className={fieldLabelClass()}>GCP Project ID</label>
            <input
              value={value.gcpProjectId}
              onChange={(e) => onChange({ ...value, gcpProjectId: e.target.value })}
              placeholder="my-gcp-project-id"
              className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--glass-1)] px-3 py-2.5 font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-[var(--cyan)]/60"
            />
          </div>
        )}

        <div>
          <label className={fieldLabelClass()}>Environment</label>
          <Select
            value={value.environment}
            onValueChange={(environment: WizardConfig["environment"] | null) =>
              environment && onChange({ ...value, environment })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENVIRONMENTS.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <p className="rounded-lg border border-[var(--glass-border-soft)] bg-[var(--glass-1)] px-3 py-2 text-[11px] text-muted-foreground">
          Preview only — the actual target region{involvesGcp ? " and project" : ""} is inferred
          automatically from your source infrastructure during analysis, not from this selection.
        </p>
      </GlassCard>

      <div className="animate-fade-up flex gap-2">
        <Button variant="outline" onClick={onBack} className="h-12 flex-1 rounded-xl">
          ← Back
        </Button>
        <Button
          onClick={onNext}
          className="h-12 flex-[2] gap-2 rounded-xl bg-gradient-to-r from-[var(--cyan)] to-[#0066ff] text-base font-bold text-black"
        >
          Continue →
        </Button>
      </div>
    </div>
  );
}
