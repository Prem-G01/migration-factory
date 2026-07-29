export function PipelineProgress({
  stages,
  stageIndex,
}: {
  stages: readonly string[];
  stageIndex: number;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      {stages.map((label, i) => (
        <div
          key={label}
          className="flex items-center gap-2 py-1 font-mono text-sm"
          style={{
            color:
              i < stageIndex
                ? "var(--green)"
                : i === stageIndex
                  ? "var(--cyan)"
                  : "var(--muted-c)",
          }}
        >
          <span className="w-4 text-center">
            {i < stageIndex ? "✓" : i === stageIndex ? "⏳" : "○"}
          </span>
          <span>{label}</span>
          {i === stageIndex && (
            <span className="ml-1 flex gap-0.5">
              {[0, 1, 2].map((d) => (
                <span
                  key={d}
                  className="inline-block size-1 rounded-full bg-[var(--cyan)]"
                  style={{ animation: `bounceDots 1.2s ease-in-out ${d * 0.15}s infinite` }}
                />
              ))}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
