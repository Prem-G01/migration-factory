/**
 * Single source of truth for design tokens that need to exist as JS
 * values too (chart series colors, canvas/SVG strokes) — not just CSS.
 * Mirrors the CSS custom properties in globals.css; keep both in sync.
 */

export const COLORS = {
  bgVoid: "#020818",
  bgSurface: "#0a1122",
  bgRaised: "rgba(10,20,50,0.6)",
  border: "rgba(99,179,237,0.1)",
  textPrimary: "#e2e8f0",
  textSecondary: "#94a3b8",
  textMuted: "#4a6fa5",
  textDim: "#2d4a7a",
  accentCyan: "#60a5fa",
  accentBlue: "#3b82f6",
  accentGreen: "#34d399",
  accentYellow: "#fbbf24",
  accentOrange: "#fb923c",
  accentRed: "#f87171",
  accentPurple: "#a78bfa",
} as const;

export const RISK_COLORS: Record<string, string> = {
  low: COLORS.accentGreen,
  medium: COLORS.accentYellow,
  high: COLORS.accentRed,
  critical: "#ef4444",
};

export const STRATEGY_COLORS: Record<string, string> = {
  rehost: COLORS.accentGreen,
  replatform: COLORS.accentYellow,
  manual: COLORS.accentOrange,
  unsupported: COLORS.accentRed,
};

/** Score is "higher is better" (confidence, security) unless inverted
 * (complexity, where higher = harder/riskier). */
export function scoreColor(score: number, invert = false): string {
  if (invert) {
    if (score <= 30) return COLORS.accentGreen;
    if (score <= 60) return COLORS.accentYellow;
    return COLORS.accentRed;
  }
  if (score >= 70) return COLORS.accentGreen;
  if (score >= 40) return COLORS.accentYellow;
  return COLORS.accentRed;
}

export function directionColor(direction: string): string {
  const awsIdx = direction.indexOf("AWS");
  const gcpIdx = direction.indexOf("GCP");
  if (awsIdx !== -1 && gcpIdx !== -1 && awsIdx < gcpIdx) return COLORS.accentGreen;
  if (gcpIdx !== -1 && awsIdx !== -1 && gcpIdx < awsIdx) return COLORS.accentOrange;
  return COLORS.accentPurple;
}
