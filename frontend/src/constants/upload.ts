import { COLORS } from "@/constants/theme";
import type { MigrationTarget } from "@/types/migration";

export const ALLOWED_EXTENSIONS = [
  "tfstate",
  "json",
  "csv",
  "xlsx",
  "tf",
  "log",
  "yaml",
  "yml",
] as const;

export const FILE_ICONS: Record<string, string> = {
  tfstate: "🗺️",
  json: "🔧",
  csv: "📊",
  xlsx: "📈",
  tf: "📄",
  log: "📜",
  yaml: "📄",
  yml: "📄",
};

export const PARSE_HINTS: Record<string, string> = {
  tfstate: ".tfstate detected — Terraform state format",
  json: ".json detected — JSON inventory format",
  csv: ".csv detected — CSV inventory format",
  xlsx: ".xlsx detected — Excel inventory format",
  tf: ".tf detected — Terraform HCL format",
  log: ".log detected — Terraform plan log format",
  yaml: ".yaml detected — YAML inventory format",
  yml: ".yml detected — YAML inventory format",
};

export type UseCaseId =
  | "aws_to_gcp"
  | "gcp_to_aws"
  | "aws_analysis"
  | "gcp_analysis"
  | "discover";

export interface UseCaseOption {
  id: UseCaseId;
  label: string;
  color: string;
  /** What actually gets sent as `target` to POST /api/v1/analyze. */
  target: MigrationTarget;
  analyzeOnly: boolean;
  /** True for the one card that replaces the file dropzone with a
   * region input + live-discovery flow. */
  isDiscover: boolean;
}

export const USE_CASES: UseCaseOption[] = [
  { id: "aws_to_gcp", label: "AWS → GCP", color: COLORS.cyan, target: "gcp", analyzeOnly: false, isDiscover: false },
  { id: "gcp_to_aws", label: "GCP → AWS", color: COLORS.orange, target: "aws", analyzeOnly: false, isDiscover: false },
  { id: "aws_analysis", label: "AWS Analysis", color: COLORS.purple, target: "analyze_only", analyzeOnly: true, isDiscover: false },
  { id: "gcp_analysis", label: "GCP Analysis", color: COLORS.purple, target: "analyze_only", analyzeOnly: true, isDiscover: false },
  // Discovering live AWS infrastructure defaults to the GCP-migration
  // framing (the project's flagship direction) — there's no separate
  // target selector once Discover Live is chosen as its own use case.
  { id: "discover", label: "Discover Live", color: COLORS.yellow, target: "gcp", analyzeOnly: false, isDiscover: true },
];

export const ALL_PIPELINE_STAGES = [
  "Parsing infrastructure",
  "Translating resources",
  "Assessing complexity",
  "Generating Terraform",
] as const;

export function getPipelineStages(useCase: UseCaseOption): readonly string[] {
  // analyze_only never generates Terraform server-side.
  return useCase.analyzeOnly
    ? ALL_PIPELINE_STAGES.slice(0, 3)
    : ALL_PIPELINE_STAGES;
}
