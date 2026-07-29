import { motion } from "motion/react";

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
        <motion.div
          key={label}
          initial={{ opacity: 0.4 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 py-0.5 font-mono text-xs"
          style={{
            color:
              i < stageIndex
                ? "#34d399"
                : i === stageIndex
                  ? "var(--color-primary)"
                  : "var(--color-muted-foreground)",
          }}
        >
          <span className="w-3 text-center">
            {i < stageIndex ? "✓" : i === stageIndex ? "⏳" : "○"}
          </span>
          <span>
            {label}
            {i === stageIndex ? "···" : ""}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
