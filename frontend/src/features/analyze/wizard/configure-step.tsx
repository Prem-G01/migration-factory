"use client";

import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import type { UseCaseId } from "@/constants/upload";

const AWS_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1", "ap-southeast-1"];
const GCP_REGIONS = ["us-central1", "us-east1", "europe-west1", "asia-south1", "asia-southeast1"];
const ENVIRONMENTS = ["dev", "staging", "prod"] as const;

export interface WizardConfig {
  region: string;
  environment: (typeof ENVIRONMENTS)[number];
}

interface ConfigureStepProps {
  useCaseId: UseCaseId;
  value: WizardConfig;
  onChange: (config: WizardConfig) => void;
  onNext: () => void;
  onBack: () => void;
}

function selectClass() {
  return "w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 font-mono text-sm text-foreground outline-none focus:border-[var(--cyan)]/50";
}

export function ConfigureStep({ useCaseId, value, onChange, onNext, onBack }: ConfigureStepProps) {
  const regions = useCaseId === "gcp_to_aws" || useCaseId === "gcp_analysis" ? GCP_REGIONS : AWS_REGIONS;

  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 p-6">
      <div className="animate-fade-up text-center">
        <h1 className="text-3xl font-bold">Configure</h1>
        <p className="mt-2 text-muted-foreground">Set the target region and environment.</p>
      </div>

      <GlassCard hoverElevate={false} className="animate-fade-up flex flex-col gap-4">
        <div>
          <label className="mb-2 block font-mono text-xs tracking-wider text-muted-foreground uppercase">
            Region
          </label>
          <select
            value={value.region}
            onChange={(e) => onChange({ ...value, region: e.target.value })}
            className={selectClass()}
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-2 block font-mono text-xs tracking-wider text-muted-foreground uppercase">
            Environment
          </label>
          <select
            value={value.environment}
            onChange={(e) => onChange({ ...value, environment: e.target.value as WizardConfig["environment"] })}
            className={selectClass()}
          >
            {ENVIRONMENTS.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>

        <p className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 text-[11px] text-muted-foreground">
          Preview only — the actual target region is inferred automatically from your
          source infrastructure during analysis, not from this selection.
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
