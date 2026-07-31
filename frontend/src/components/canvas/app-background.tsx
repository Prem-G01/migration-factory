"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { GalaxyBackground } from "@/components/canvas/galaxy-background";
import { LightBackground } from "@/components/canvas/light-background";
import { CloudMotif } from "@/components/canvas/cloud-motif";

export function AppBackground() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Default to dark's starfield before hydration settles — matches
  // providers.tsx's defaultTheme="dark" so there's no flash/mismatch.
  const isLight = mounted && resolvedTheme === "light";

  return (
    <>
      {isLight ? <LightBackground /> : <GalaxyBackground />}
      <CloudMotif />
    </>
  );
}
