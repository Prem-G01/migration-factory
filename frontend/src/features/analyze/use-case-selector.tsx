"use client";

import { USE_CASES, type UseCaseId } from "@/constants/upload";
import { cn } from "@/lib/utils";

interface UseCaseSelectorProps {
  value: UseCaseId;
  onChange: (id: UseCaseId) => void;
}

export function UseCaseSelector({ value, onChange }: UseCaseSelectorProps) {
  const selected = USE_CASES.find((u) => u.id === value)!;
  const row1 = USE_CASES.slice(0, 3);
  const row2 = USE_CASES.slice(3);

  const renderCard = (useCase: (typeof USE_CASES)[number]) => {
    const active = useCase.id === value;
    return (
      <button
        key={useCase.id}
        type="button"
        onClick={() => onChange(useCase.id)}
        className={cn(
          "flex h-[60px] items-center justify-center rounded-xl border px-3 text-center text-sm font-medium transition-all",
          active
            ? "border-2 bg-white/[0.04] text-foreground"
            : "border-white/10 text-muted-foreground hover:border-white/20",
        )}
        style={
          active
            ? { borderColor: useCase.color, boxShadow: `0 0 16px ${useCase.color}33` }
            : undefined
        }
      >
        {useCase.label}
      </button>
    );
  };

  return (
    <div>
      <div className="mb-2 font-mono text-xs tracking-wider text-muted-foreground uppercase">
        Use Case
      </div>
      <div className="grid grid-cols-3 gap-2">{row1.map(renderCard)}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">{row2.map(renderCard)}</div>

      {selected.analyzeOnly && (
        <p className="mt-2 font-mono text-[11px] text-[var(--purple)]">
          No Terraform generated · Config analysis only
        </p>
      )}
    </div>
  );
}
