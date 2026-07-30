const STEPS = [
  { id: "cloud", label: "Cloud" },
  { id: "configure", label: "Configure" },
  { id: "upload", label: "Source" },
  { id: "progress", label: "Analyze" },
  { id: "results", label: "Results" },
] as const;

export type WizardStepId = (typeof STEPS)[number]["id"];

export function StepIndicator({ current }: { current: WizardStepId }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current);

  return (
    <div className="flex items-center justify-center gap-1.5">
      {STEPS.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <div key={step.id} className="flex items-center gap-1.5">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className="flex size-6 items-center justify-center rounded-full font-mono text-[11px] font-semibold transition-colors"
                style={{
                  background: done || active ? "var(--cyan)" : "rgba(255,255,255,0.06)",
                  color: done || active ? "var(--void)" : "var(--muted-c)",
                  boxShadow: active ? "0 0 12px rgba(0,212,255,0.5)" : undefined,
                }}
              >
                {done ? "✓" : i + 1}
              </div>
              <span
                className="font-mono text-[10px] tracking-wider uppercase"
                style={{ color: active ? "var(--cyan)" : "var(--muted-c)" }}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className="mb-[18px] h-px w-8 transition-colors"
                style={{ background: done ? "var(--cyan)" : "rgba(255,255,255,0.08)" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
