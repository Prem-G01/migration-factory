"use client";

import { Loader2 } from "lucide-react";

const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ProgressStep({ stages, stageIndex }: { stages: readonly string[]; stageIndex: number }) {
  const pct = Math.min(100, Math.round(((stageIndex + 0.5) / stages.length) * 100));

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-10 p-6">
      <div className="animate-fade-up flex flex-col items-center gap-6 text-center">
        <div className="relative flex size-40 items-center justify-center">
          <svg className="absolute inset-0 -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r={RADIUS} fill="none" stroke="var(--glass-border)" strokeWidth="6" />
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke="var(--cyan)"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={CIRCUMFERENCE * (1 - pct / 100)}
              style={{ transition: "stroke-dashoffset 0.5s ease", filter: "drop-shadow(0 0 10px var(--cyan))" }}
            />
          </svg>
          <div className="flex flex-col items-center">
            <Loader2 className="mb-1 size-6 animate-spin text-[var(--cyan)]" />
            <span className="font-mono text-2xl font-bold">{pct}%</span>
          </div>
        </div>
        <div>
          <h1 className="text-3xl font-bold">Analyzing your infrastructure</h1>
          <p className="mt-2 text-muted-foreground">Real assessment running server-side — usually a few seconds.</p>
        </div>
      </div>

      <div className="animate-fade-up w-full rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-1)] p-6 backdrop-blur-xl">
        {stages.map((label, i) => (
          <div
            key={label}
            className="flex items-center gap-3 py-2.5 font-mono text-sm"
            style={{
              color: i < stageIndex ? "var(--green)" : i === stageIndex ? "var(--cyan)" : "var(--muted-c)",
            }}
          >
            <span
              className="flex size-6 items-center justify-center rounded-full border text-xs"
              style={{
                borderColor: i < stageIndex ? "var(--green)" : i === stageIndex ? "var(--cyan)" : "var(--glass-border)",
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
