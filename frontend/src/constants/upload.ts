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

export interface TargetOption {
  value: MigrationTarget;
  label: string;
  name: string;
  description: string;
  color: string;
}

export const TARGET_OPTIONS: TargetOption[] = [
  {
    value: "gcp",
    label: "AWS → GCP",
    name: "Migrate to GCP",
    description: "Generate GCP Terraform from AWS infrastructure",
    color: "#34d399",
  },
  {
    value: "aws",
    label: "GCP → AWS",
    name: "Migrate to AWS",
    description: "Generate AWS Terraform from GCP infrastructure",
    color: "#fb923c",
  },
  {
    value: "analyze_only",
    label: "Any cloud",
    name: "Analyze Only",
    description: "Security, compliance and cost analysis without migration",
    color: "#a78bfa",
  },
];

export const ALL_PIPELINE_STAGES = [
  "Parsing infrastructure",
  "Translating resources",
  "Assessing complexity",
  "Generating Terraform",
] as const;

export function getPipelineStages(target: MigrationTarget): readonly string[] {
  // analyze_only never generates Terraform server-side.
  return target === "analyze_only"
    ? ALL_PIPELINE_STAGES.slice(0, 3)
    : ALL_PIPELINE_STAGES;
}

export interface SampleFile {
  label: string;
  url: string;
  filename: string;
  target: MigrationTarget;
}

// Next's basePath auto-prefixes <Link>/router.push navigation, but not
// raw fetch() calls — these need the prefix added manually so they still
// resolve once served under GitHub Pages' /migration-factory/ subpath.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const SAMPLE_FILES: SampleFile[] = [
  { label: "Try AWS sample", url: `${BASE_PATH}/samples/aws-sample.tfstate`, filename: "aws-sample.tfstate", target: "gcp" },
  { label: "Try GCP sample", url: `${BASE_PATH}/samples/gcp-sample.tfstate`, filename: "gcp-sample.tfstate", target: "aws" },
  { label: "Try complex estate", url: `${BASE_PATH}/samples/complex-estate.tfstate`, filename: "complex-estate.tfstate", target: "gcp" },
];
