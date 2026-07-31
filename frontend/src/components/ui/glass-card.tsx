"use client";

import * as React from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface GlassCardProps extends React.ComponentProps<"div"> {
  /** Renders a thin gradient line along the top edge, tinted with this
   * color — used to color-code metric cards without a full colored fill. */
  accent?: string;
  hoverElevate?: boolean;
}

export function GlassCard({
  className,
  accent,
  hoverElevate = true,
  children,
  ...props
}: GlassCardProps) {
  return (
    <motion.div
      data-slot="glass-card"
      className={cn(
        "relative overflow-hidden rounded-xl border border-[var(--glass-border)] bg-[var(--glass-1)] p-4 backdrop-blur-xl",
        "shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset,0_8px_24px_-8px_var(--shadow-c)]",
        className,
      )}
      whileHover={
        hoverElevate
          ? { y: -2, borderColor: "rgba(0,212,255,0.25)" }
          : undefined
      }
      transition={{ duration: 0.2, ease: "easeOut" }}
      {...(props as React.ComponentProps<typeof motion.div>)}
    >
      {accent && (
        <div
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          }}
        />
      )}
      {children}
    </motion.div>
  );
}
