/**
 * Single source of truth for design tokens that need to exist as JS
 * values too (canvas/SVG strokes, chart series colors) — not just CSS.
 * Mirrors the CSS custom properties in globals.css; keep both in sync.
 */

export const COLORS = {
  void: "#020818",
  surface: "#0D1117",
  raised: "#161B22",
  border: "#21262D",
  cyan: "#00D4FF",
  green: "#00FF88",
  orange: "#FF6B35",
  purple: "#8B5CF6",
  yellow: "#F59E0B",
  red: "#EF4444",
  text: "#F0F6FC",
  muted: "#8B949E",
  dim: "#3D444D",
} as const;

export const RISK_COLORS: Record<string, string> = {
  low: COLORS.green,
  medium: COLORS.yellow,
  high: COLORS.red,
  critical: "#dc2626",
};

export const STRATEGY_COLORS: Record<string, string> = {
  rehost: COLORS.green,
  replatform: COLORS.yellow,
  manual: COLORS.orange,
  unsupported: COLORS.red,
};

/** Score is "higher is better" (confidence, security) unless inverted
 * (complexity, where higher = harder/riskier). */
export function scoreColor(score: number, invert = false): string {
  if (invert) {
    if (score <= 30) return COLORS.green;
    if (score <= 60) return COLORS.yellow;
    return COLORS.red;
  }
  if (score >= 70) return COLORS.green;
  if (score >= 40) return COLORS.yellow;
  return COLORS.red;
}

export function directionColor(direction: string): string {
  const awsIdx = direction.indexOf("AWS");
  const gcpIdx = direction.indexOf("GCP");
  if (awsIdx !== -1 && gcpIdx !== -1 && awsIdx < gcpIdx) return COLORS.green;
  if (gcpIdx !== -1 && awsIdx !== -1 && gcpIdx < awsIdx) return COLORS.orange;
  return COLORS.purple;
}
