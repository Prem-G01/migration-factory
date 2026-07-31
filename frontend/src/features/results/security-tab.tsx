import { DisclosureNote } from "@/components/ui/disclosure-note";
import { EmptyState } from "@/components/ui/empty-state";
import { ScoreRing } from "@/components/data/score-ring";
import { COLORS } from "@/constants/theme";
import type { SecurityFinding } from "@/types/migration";

function severityColor(severity: string): string {
  return severity === "high" || severity === "critical" ? COLORS.red : COLORS.yellow;
}

export function SecurityTab({
  score,
  findings,
}: {
  score: number;
  findings: (SecurityFinding & { category: string })[];
}) {
  return (
    <div>
      <DisclosureNote>
        * Based on configuration analysis. Runtime threats require AWS GuardDuty or
        GCP Security Command Center.
      </DisclosureNote>

      <div className="mb-4 flex items-center gap-4 rounded-xl border border-[var(--glass-border-soft)] bg-[var(--glass-1)] p-4">
        <ScoreRing score={score} size={88} strokeWidth={7} />
        <div>
          <div className="text-base text-foreground/90">Security Score</div>
          <div className="font-mono text-sm text-muted-foreground">
            {score >= 80 ? "Good posture" : "Needs attention"}
          </div>
        </div>
      </div>

      {findings.length === 0 ? (
        <EmptyState icon="🛡️" message="No security findings detected." />
      ) : (
        <div className="flex flex-col gap-1.5">
          {findings.slice(0, 8).map((f, i) => (
            <div
              key={i}
              className="flex items-center gap-2 rounded-lg border border-[var(--glass-border-soft)] bg-[var(--glass-1)] px-3 py-2.5 text-sm"
            >
              <span
                className="rounded-full px-2 py-0.5 font-mono text-[10px]"
                style={{ color: severityColor(f.severity), background: `${severityColor(f.severity)}1a` }}
              >
                {f.severity.toUpperCase()}
              </span>
              <span className="flex-1 text-muted-foreground">{f.message.slice(0, 70)}</span>
              <span className="font-mono text-[11px] text-muted-foreground/60">{f.category}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
