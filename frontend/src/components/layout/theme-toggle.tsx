"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isLight = mounted && resolvedTheme === "light";

  return (
    <button
      type="button"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      title={isLight ? "Switch to dark theme" : "Switch to light theme"}
      aria-label="Toggle color theme"
      className="relative flex size-8 shrink-0 items-center justify-center rounded-lg border border-[var(--glass-border)] bg-[var(--glass-1)] text-muted-foreground transition-colors hover:text-foreground"
    >
      {mounted && (
        <>
          <Sun
            className={cn("absolute size-4 transition-all", isLight ? "scale-100 opacity-100" : "scale-50 opacity-0")}
          />
          <Moon
            className={cn("absolute size-4 transition-all", isLight ? "scale-50 opacity-0" : "scale-100 opacity-100")}
          />
        </>
      )}
    </button>
  );
}
