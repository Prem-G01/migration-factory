"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { COLORS } from "@/constants/theme";
import type { FrameworkResult } from "@/types/migration";

function frameworkBarColor(score: number): string {
  if (score >= 80) return COLORS.accentGreen;
  if (score >= 60) return COLORS.accentYellow;
  return COLORS.accentRed;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { name: string; value: number; payload: Record<string, unknown> }[];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  return (
    <div className="rounded-lg border border-white/10 bg-[#0a1122] px-3 py-2 font-mono text-xs shadow-xl">
      <div className="text-muted-foreground">{point.payload.label as string}</div>
      <div className="font-semibold" style={{ color: point.payload.color as string }}>
        {point.value}%
      </div>
    </div>
  );
}

export function ComplianceBarChart({
  frameworks,
}: {
  frameworks: FrameworkResult[];
}) {
  const data = frameworks.map((f) => ({
    label: f.framework,
    score: Math.round(f.compliance_score),
    color: frameworkBarColor(f.compliance_score),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,179,237,0.08)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: COLORS.textMuted, fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
          axisLine={{ stroke: "rgba(99,179,237,0.1)" }}
          tickLine={false}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fill: COLORS.textMuted, fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(99,179,237,0.05)" }} />
        <Bar dataKey="score" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.label} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CostComparisonChart({
  sourceMonthly,
  targetMonthly,
}: {
  sourceMonthly: number;
  targetMonthly: number;
}) {
  const data = [
    { label: "Current", value: Math.round(sourceMonthly), color: COLORS.accentOrange },
    { label: "Projected", value: Math.round(targetMonthly), color: COLORS.accentGreen },
  ];

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 0, right: 24, left: 8, bottom: 0 }}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: COLORS.textSecondary, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={70}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0];
            return (
              <div className="rounded-lg border border-white/10 bg-[#0a1122] px-3 py-2 font-mono text-xs shadow-xl">
                <div className="text-muted-foreground">{p.payload.label}</div>
                <div className="font-semibold" style={{ color: p.payload.color }}>
                  ${(p.value as number).toLocaleString()}/mo
                </div>
              </div>
            );
          }}
          cursor={{ fill: "rgba(99,179,237,0.05)" }}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={28}>
          {data.map((entry) => (
            <Cell key={entry.label} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
