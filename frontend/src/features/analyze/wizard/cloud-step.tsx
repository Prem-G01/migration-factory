"use client";

import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { USE_CASES, type UseCaseId } from "@/constants/upload";
import { cn } from "@/lib/utils";

interface CloudStepProps {
  value: UseCaseId;
  onChange: (id: UseCaseId) => void;
  onNext: () => void;
}

export function CloudStep({ value, onChange, onNext }: CloudStepProps) {
  const selected = USE_CASES.find((u) => u.id === value)!;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-8 p-6">
      <div className="animate-fade-up text-center">
        <h1 className="text-3xl font-bold">What are you migrating?</h1>
        <p className="mt-2 text-muted-foreground">Pick a direction to get started.</p>
      </div>

      <div className="grid w-full grid-cols-2 gap-3">
        {USE_CASES.map((useCase, i) => {
          const active = useCase.id === value;
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
                className={cn("h-full border-2", active ? "border-transparent" : "border-white/10")}
                style={active ? { borderColor: useCase.color, boxShadow: `0 0 20px ${useCase.color}22` } : undefined}
              >
                <div className="font-semibold" style={{ color: active ? useCase.color : undefined }}>
                  {useCase.label}
                </div>
                {useCase.analyzeOnly && (
                  <div className="mt-1 font-mono text-[11px] text-[var(--purple)]">
                    Analysis only · no Terraform
                  </div>
                )}
                {useCase.isDiscover && (
                  <div className="mt-1 font-mono text-[11px] text-[var(--yellow)]">
                    Live AWS discovery, no file needed
                  </div>
                )}
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
