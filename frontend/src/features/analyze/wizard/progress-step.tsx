export function ProgressStep({ stages, stageIndex }: { stages: readonly string[]; stageIndex: number }) {
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-8 p-6">
      <div className="animate-fade-up text-center">
        <h1 className="text-3xl font-bold">Analyzing</h1>
        <p className="mt-2 text-muted-foreground">This usually takes a few seconds.</p>
      </div>

      <div className="animate-fade-up w-full rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        {stages.map((label, i) => (
          <div
            key={label}
            className="flex items-center gap-3 py-2.5 font-mono text-sm"
            style={{
              color: i < stageIndex ? "var(--green)" : i === stageIndex ? "var(--cyan)" : "var(--muted-c)",
            }}
          >
            <span className="flex size-6 items-center justify-center rounded-full border text-xs"
              style={{
                borderColor: i < stageIndex ? "var(--green)" : i === stageIndex ? "var(--cyan)" : "rgba(255,255,255,0.1)",
              }}
            >
              {i < stageIndex ? "✓" : i + 1}
            </span>
            <span>{label}</span>
            {i === stageIndex && (
              <span className="ml-auto flex gap-0.5">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="inline-block size-1.5 rounded-full bg-current"
                    style={{ animation: `bounceDots 1.2s ease-in-out ${d * 0.15}s infinite` }}
                  />
                ))}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
