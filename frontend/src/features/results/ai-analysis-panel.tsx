"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { ChevronRight } from "lucide-react";
import type { AIAnalysis } from "@/types/migration";
import { cn } from "@/lib/utils";

export function AIAnalysisPanel({ ai }: { ai: AIAnalysis | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!ai?.risks) return null;

  return (
    <div className="rounded-xl border border-[rgba(139,92,246,0.18)] bg-[rgba(88,28,135,0.08)] p-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
      >
        <ChevronRight
          className={cn(
            "size-3 text-[#a78bfa] transition-transform",
            expanded && "rotate-90",
          )}
        />
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#a78bfa] opacity-75" />
          <span className="relative inline-flex size-1.5 rounded-full bg-[#a78bfa]" />
        </span>
        <span className="text-xs font-medium text-[#a78bfa]">AI Analysis</span>
        <span className="ml-auto font-mono text-[10px] text-[#4a1d96]">
          {ai.mode === "rule_based" ? "Rule-based" : "Claude"}
        </span>
      </button>
      <motion.div
        initial={false}
        animate={{ height: expanded ? "auto" : 0 }}
        className="overflow-hidden"
      >
        <p className="pt-2 text-xs leading-relaxed text-muted-foreground">
          {ai.risks.slice(0, 250)}
        </p>
      </motion.div>
    </div>
  );
}
