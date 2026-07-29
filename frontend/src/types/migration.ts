/**
 * Types mirror the real FastAPI response shapes in
 * src/migration_factory/api/main.py exactly — verified against live
 * responses, not guessed from the Pydantic model definitions alone.
 */

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type MigrationStrategy = "rehost" | "replatform" | "manual";
export type PipelineMode = "analyze" | "migrate";
export type AIMode = "ai" | "rule_based";
export type FindingSeverity = "low" | "medium" | "high" | "critical";

export interface RunSummary {
  resources: number;
  complexity_score: number;
  risk_level: RiskLevel;
  confidence_score: number;
  security_score: number;
  compliance_score: number;
  monthly_savings: number;
  downtime_minutes: number;
  waves: number;
  blockers: number;
  duration_seconds: number;
}

/** POST /api/v1/analyze response — compact summary only. */
export interface AnalyzeResponse {
  run_id: string;
  status: string;
  direction: string;
  duration_seconds: number;
  summary: RunSummary;
}

export interface ScoreBreakdown {
  base_complexity: number;
  dependency_load: number;
  support_penalty: number;
}

export interface ResourceAssessment {
  resource_id: string;
  resource_name: string;
  /** e.g. "network.vpc", "compute.instance" — dotted canonical type. */
  canonical_type: string;
  complexity_score: number;
  score_breakdown: ScoreBreakdown;
  support_status: string;
  strategy: MigrationStrategy;
  downtime: string;
  dependency_count: number;
  blockers: string[];
  /** Merged in by the API from the matching TranslationResult — not a
   * field on the underlying Pydantic model itself. */
  target_service: string | null;
}

export interface Assessment {
  overall_complexity_score: number;
  risk_level: RiskLevel;
  resource_assessments: ResourceAssessment[];
  blockers: string[];
  phases: unknown[];
  recommendation: string;
}

export interface SecurityFinding {
  severity: FindingSeverity;
  message: string;
  resource_name?: string;
  attribute_path?: string;
}

export interface Security {
  security_score: number;
  risk_level: RiskLevel;
  policy_report: unknown;
  iam_findings: SecurityFinding[];
  secret_findings: SecurityFinding[];
  firewall_findings: SecurityFinding[];
  summary: unknown;
}

export interface FrameworkResult {
  framework: string;
  total_checks: number;
  passed: number;
  failed: number;
  warnings: number;
  skipped: number;
  compliance_score: number;
  failed_check_ids: string[];
}

export interface Compliance {
  overall_compliance_score: number;
  framework_results: FrameworkResult[];
  policy_report: unknown;
  compliant_frameworks: string[];
  non_compliant_frameworks: string[];
}

export interface CostSummary {
  source_monthly_total: number;
  target_monthly_total: number;
  monthly_savings: number;
  savings_percentage: number;
  yearly_savings: number;
  total_migration_cost: number;
  break_even_months: number;
  idle_resource_count: number;
  idle_monthly_waste: number;
}

export interface FinOps {
  cost_summary: CostSummary;
  savings_recommendations: string[];
}

export interface MigrationWave {
  wave_number: number;
  name: string;
  resource_ids: string[];
  can_parallelize: boolean;
  estimated_duration_hours: number;
  validation_checkpoints: string[];
  rollback_trigger: string;
}

export interface CutoverPlan {
  total_downtime_minutes: number;
  steps: unknown[];
  pre_cutover_checks: string[];
  post_cutover_checks: string[];
}

export interface ConfidenceScore {
  overall_confidence: number;
  factors: Record<string, number>;
  risks_to_confidence: string[];
  confidence_boosters: string[];
}

export interface MigrationPlan {
  waves: MigrationWave[];
  cutover_plan: CutoverPlan;
  maintenance_window: {
    recommended_window_hours: number;
    minimum_window_hours: number;
    buffer_percentage: number;
    justification: string;
  };
  confidence: ConfidenceScore;
  post_migration_verification: string[];
}

export interface AIAnalysis {
  risks: string;
  optimizations: string;
  summary: string;
  mode: AIMode;
}

export interface TranslationResult {
  resource_id: string;
  resource_name: string;
  status: string;
  target_service: string | null;
  required_changes: unknown[];
}

/** GET /api/v1/report/{run_id} — the full report. Every nested object
 * lives at the top level (assessment/security/compliance/plan/
 * ai_analysis), not under a "report" key. */
export interface MigrationReport {
  run_id: string;
  status: string;
  mode: PipelineMode;
  direction: string;
  created_at: string;
  duration_seconds: number;
  source_provider: string;
  target_provider: string;
  unsupported_resources: unknown[];
  knowledge_graph: unknown;
  translation_summary: Record<string, number>;
  translation_results: TranslationResult[];
  assessment: Assessment;
  security: Security;
  compliance: Compliance;
  finops: FinOps;
  validation: unknown;
  plan: MigrationPlan;
  rollback: unknown;
  terraform_available: boolean;
  summary: RunSummary;
  ai_analysis: AIAnalysis;
}

/** GET /api/v1/runs — history list. Each entry is the summary fields
 * spread flat alongside run_id/direction/mode/created_at. */
export interface RunListItem extends RunSummary {
  run_id: string;
  direction: string;
  mode: PipelineMode;
  created_at: string;
}

export interface RunListResponse {
  runs: RunListItem[];
}

export interface DiscoverResponse {
  resources_discovered: number;
  region: string;
  resource_types: string[];
  raw_data: unknown;
}

export type MigrationTarget = "gcp" | "aws" | "analyze_only";
