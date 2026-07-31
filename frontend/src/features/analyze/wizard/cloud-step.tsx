"use client";

import type { ComponentType } from "react";
import { ArrowRightLeft, Cloud, Radar, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { USE_CASES, type UseCaseId } from "@/constants/upload";
import { cn } from "@/lib/utils";

const ICONS: Record<UseCaseId, ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  aws_to_gcp: ArrowRightLeft,
  gcp_to_aws: ArrowRightLeft,
  aws_analysis: Search,
  gcp_analysis: Search,
  discover: Radar,
};

interface CloudStepProps {
  value: UseCaseId;
  onChange: (id: UseCaseId) => void;
  onNext: () => void;
}

export function CloudStep({ value, onChange, onNext }: CloudStepProps) {
  const selected = USE_CASES.find((u) => u.id === value)!;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-8 p-6">
      <div className="animate-fade-up flex flex-col items-center gap-3 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--cyan)]/20 to-[#0066ff]/20 text-[var(--cyan)]">
          <Cloud className="size-6" />
        </div>
        <h1 className="text-3xl font-bold">What are you migrating?</h1>
        <p className="text-muted-foreground">Pick a direction to get started.</p>
      </div>

      <div className="grid w-full grid-cols-2 gap-3">
        {USE_CASES.map((useCase, i) => {
          const active = useCase.id === value;
          const Icon = ICONS[useCase.id];
          return (
            <button
              key={useCase.id}
              type="button"
              onClick={() => onChange(useCase.id)}
              className={cn(
                "animate-fade-up opacity-0 text-left",
                useCase.id === "discover" && "col-span-2",
              )}
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <GlassCard
                accent={active ? useCase.color : undefined}
                hoverElevate
                className={cn("h-full border-2 p-5", active ? "border-transparent" : "border-[var(--glass-border)]")}
                style={active ? { borderColor: useCase.color, boxShadow: `0 0 24px ${useCase.color}22` } : undefined}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg"
                    style={{
                      background: `${useCase.color}1a`,
                      color: useCase.color,
                    }}
                  >
                    <Icon className="size-4.5" />
                  </div>
                  <div>
                    <div className="font-semibold" style={{ color: active ? useCase.color : undefined }}>
                      {useCase.label}
                    </div>
                    {useCase.analyzeOnly && (
                      <div className="mt-0.5 font-mono text-[11px] text-[var(--purple)]">
                        Analysis only · no Terraform
                      </div>
                    )}
                    {useCase.isDiscover && (
                      <div className="mt-0.5 font-mono text-[11px] text-[var(--yellow)]">
                        Live AWS discovery, no file needed
                      </div>
                    )}
                  </div>
                </div>
              </GlassCard>
            </button>
          );
        })}
      </div>

      <Button
        onClick={onNext}
        className="h-12 w-full max-w-xs gap-2 rounded-xl bg-gradient-to-r from-[var(--cyan)] to-[#0066ff] text-base font-bold text-black"
      >
        Continue with {selected.label} →
      </Button>
    </div>
  );
}
