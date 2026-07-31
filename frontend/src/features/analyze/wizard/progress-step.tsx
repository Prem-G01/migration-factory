"use client";

import { useEffect, useState, type ComponentType } from "react";
import { FileSearch2, Shuffle, Gauge, FileCode2, Check, Loader2, type LucideProps } from "lucide-react";
import { cn } from "@/lib/utils";

const STAGE_ICONS: Record<string, ComponentType<LucideProps>> = {
  "Parsing infrastructure": FileSearch2,
  "Translating resources": Shuffle,
  "Assessing complexity": Gauge,
  "Generating Terraform": FileCode2,
};

function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Horizontal connected-stage pipeline — same visual language as a
 * Jenkins/CI pipeline graph (nodes + flowing connectors) rather than a
 * plain vertical checklist, since that's what reads as "real infra
 * automation running" instead of a generic loading spinner. */
export function ProgressStep({ stages, stageIndex }: { stages: readonly string[]; stageIndex: number }) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsedMs(Date.now() - start), 250);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center gap-12 p-6">
      <div className="animate-fade-up flex flex-col items-center gap-2 text-center">
        <div className="mb-1 flex items-center gap-2 rounded-full border border-[var(--glass-border)] bg-[var(--glass-1)] px-3 py-1 font-mono text-xs text-muted-foreground">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-[var(--cyan)] opacity-60" />
            <span className="relative inline-flex size-2 rounded-full bg-[var(--cyan)]" />
          </span>
          RUNNING · {formatElapsed(elapsedMs)}
        </div>
        <h1 className="text-3xl font-bold">Analyzing your infrastructure</h1>
        <p className="text-muted-foreground">Real assessment running server-side — usually a few seconds.</p>
      </div>

      <div className="animate-fade-up w-full rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-1)] p-8 pb-10 backdrop-blur-xl md:p-10">
        <div className="flex w-full items-start">
          {stages.map((label, i) => {
            const done = i < stageIndex;
            const active = i === stageIndex;
            const Icon = STAGE_ICONS[label] ?? Gauge;
            const color = done ? "var(--green)" : active ? "var(--cyan)" : "var(--glass-border)";

            return (
              <div key={label} className={cn("flex items-center", i < stages.length - 1 && "flex-1")}>
                <div className="flex shrink-0 flex-col items-center gap-3">
                  <div
                    className="relative flex size-14 items-center justify-center rounded-full border-2 transition-colors"
                    style={{
                      borderColor: color,
                      background: done
                        ? "rgba(0,255,136,0.1)"
                        : active
                          ? "rgba(0,212,255,0.1)"
                          : "var(--glass-1)",
                      boxShadow: active ? "0 0 24px -4px var(--cyan)" : done ? "0 0 16px -6px var(--green)" : undefined,
                    }}
                  >
                    {active && (
                      <span
                        className="absolute inset-[-6px] rounded-full border"
                        style={{ borderColor: "var(--cyan)", opacity: 0.35, animation: "ringPulse 1.6s ease-out infinite" }}
                      />
                    )}
                    {done ? (
                      <Check className="size-6" style={{ color }} />
                    ) : active ? (
                      <Loader2 className="size-6 animate-spin" style={{ color }} />
                    ) : (
                      <Icon className="size-6" style={{ color: "var(--muted-c)" }} />
                    )}
                  </div>
                  <span
                    className="max-w-[7.5rem] text-center font-mono text-[11px] leading-tight tracking-wide uppercase"
                    style={{ color: done ? "var(--green)" : active ? "var(--cyan)" : "var(--muted-c)" }}
                  >
                    {label}
                  </span>
                </div>

                {i < stages.length - 1 && (
                  <div className="relative -mt-9 h-0.5 w-full min-w-8 overflow-hidden rounded-full" style={{ background: "var(--glass-border)" }}>
                    <div
                      className="h-full rounded-full transition-[width] duration-500 ease-out"
                      style={{
                        width: done ? "100%" : active ? "50%" : "0%",
                        background: "linear-gradient(90deg, var(--green), var(--cyan))",
                      }}
                    />
                    {active && (
                      <div
                        className="pipeline-flow absolute inset-y-0 left-0 w-full"
                        style={{ background: "linear-gradient(90deg, transparent, rgba(0,212,255,0.6), transparent)" }}
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
