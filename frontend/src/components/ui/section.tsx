"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface SectionProps {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Stagger delay index — pass increasing values (0, 1, 2...) for
   * successive sections on the same page so they cascade in. */
  index?: number;
}

export function Section({
  title,
  description,
  action,
  children,
  className,
  index = 0,
}: SectionProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06, ease: "easeOut" }}
      className={cn("flex flex-col gap-3", className)}
    >
      {(title || action) && (
        <div className="flex items-center justify-between">
          <div>
            {title && (
              <h2 className="font-mono text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-0.5 text-xs text-muted-foreground/70">
                {description}
              </p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </motion.section>
  );
}
