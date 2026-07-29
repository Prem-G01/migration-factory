"use client";

import { useEffect, useState } from "react";
import { scoreColor } from "@/constants/theme";

export function ScoreRing({
  score,
  size = 72,
  strokeWidth = 6,
}: {
  score: number | null;
  size?: number;
  strokeWidth?: number;
}) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 50);
    return () => clearTimeout(t);
  }, []);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = score ?? 0;
  const color = scoreColor(pct);
  const offset = circumference * (1 - (animated ? pct : 0) / 100);
  const center = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="rgba(0,212,255,0.1)"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${center} ${center})`}
        style={{ transition: "stroke-dashoffset 1s ease" }}
      />
      <text
        x={center}
        y={center + 6}
        textAnchor="middle"
        fontSize={size * 0.25}
        fontWeight={600}
        fontFamily="var(--font-geist-mono)"
        fill={color}
      >
        {score ?? "—"}
      </text>
    </svg>
  );
}
