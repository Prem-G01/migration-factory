import type { ReactNode } from "react";

/** Honest-labeling callout — used anywhere the UI presents an estimate
 * or a configuration-based check as if it were live/authoritative data. */
export function DisclosureNote({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 font-mono text-[11px] text-muted-foreground">
      ⓘ {children}
    </div>
  );
}
