"use client";

import { Cloud, Server, Network, ArrowLeftRight, Database, Boxes } from "lucide-react";

const GLYPHS = [
  { Icon: Cloud, top: "8%", left: "6%", size: 220, rotate: -8, delay: "0s" },
  { Icon: Server, top: "62%", left: "3%", size: 150, rotate: 6, delay: "1.2s" },
  { Icon: Network, top: "12%", left: "82%", size: 180, rotate: 10, delay: "0.6s" },
  { Icon: Database, top: "70%", left: "86%", size: 160, rotate: -6, delay: "1.8s" },
  { Icon: ArrowLeftRight, top: "40%", left: "50%", size: 130, rotate: 0, delay: "2.4s" },
  { Icon: Boxes, top: "88%", left: "45%", size: 140, rotate: -4, delay: "0.9s" },
] as const;

/** Large, heavily blurred, low-opacity glyphs suggesting "cloud
 * infrastructure" without using any real vendor logo/trademark. Purely
 * decorative depth behind the glass UI — never intercepts pointer
 * events, never affects layout. */
export function CloudMotif() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" style={{ zIndex: 0 }} aria-hidden="true">
      {GLYPHS.map(({ Icon, top, left, size, rotate, delay }, i) => (
        <div
          key={i}
          className="animate-motif-float absolute"
          style={{
            top,
            left,
            width: size,
            height: size,
            animationDelay: delay,
            filter: "blur(1.5px)",
            opacity: "var(--motif-opacity, 0.05)",
            color: "var(--cyan)",
            ["--motif-rotate" as string]: `${rotate}deg`,
          }}
        >
          <Icon
            width={size}
            height={size}
            strokeWidth={0.6}
            style={{ filter: "drop-shadow(0 30px 60px var(--shadow-c))" }}
          />
        </div>
      ))}
    </div>
  );
}
