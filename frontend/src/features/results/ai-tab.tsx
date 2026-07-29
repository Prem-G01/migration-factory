import type { AIAnalysis } from "@/types/migration";
import { EmptyState } from "@/components/ui/empty-state";

function AISection({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <div className="mb-1 font-mono text-xs tracking-wider text-[var(--purple)] uppercase">
        {title}
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{content}</p>
    </div>
  );
}

export function AITab({ ai }: { ai: AIAnalysis | null }) {
  if (!ai?.risks) {
    return <EmptyState icon="🤖" message="No AI analysis available for this run." />;
  }

  return (
    <div className="rounded-xl border border-[rgba(139,92,246,0.18)] bg-[rgba(139,92,246,0.06)] p-5">
      <div className="mb-4 flex items-center gap-2">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-[var(--purple)] opacity-75" />
          <span className="relative inline-flex size-2 rounded-full bg-[var(--purple)]" />
        </span>
        <span className="text-sm font-medium text-[var(--purple)]">AI Analysis</span>
      </div>

      <div className="flex flex-col gap-4">
        <AISection title="Architecture" content={ai.summary} />
        <AISection title="Risks" content={ai.risks} />
        <AISection title="Optimizations" content={ai.optimizations} />
      </div>

      <div className="mt-4 font-mono text-[11px] text-muted-foreground">
        {ai.mode === "rule_based" ? "Rule-based analysis" : "Powered by Claude"}
      </div>
    </div>
  );
}
