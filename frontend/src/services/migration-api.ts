import { API_BASE_URL } from "@/lib/config";
import type {
  AnalyzeResponse,
  DiscoverResponse,
  MigrationReport,
  MigrationTarget,
  RunListResponse,
} from "@/types/migration";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorDetail(response));
  }
  return response.json() as Promise<T>;
}

export async function analyzeFile(
  file: File,
  target?: MigrationTarget,
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);
  if (target) form.append("target", target);
  return request<AnalyzeResponse>("/api/v1/analyze", {
    method: "POST",
    body: form,
  });
}

export async function analyzeRawData(
  rawData: unknown,
  target?: MigrationTarget,
): Promise<AnalyzeResponse> {
  const blob = new Blob([JSON.stringify(rawData)], {
    type: "application/json",
  });
  const file = new File([blob], "discovered.json", {
    type: "application/json",
  });
  return analyzeFile(file, target);
}

export async function getReport(runId: string): Promise<MigrationReport> {
  return request<MigrationReport>(`/api/v1/report/${runId}`);
}

export async function getHtmlReport(runId: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/v1/report/${runId}/html`);
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorDetail(response));
  }
  return response.text();
}

export async function downloadTerraform(runId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/terraform/${runId}`, {
    // Errors need to be read as JSON, so don't assume the body is a
    // zip up front — check response.ok first, same trap as the old
    // frontend's responseType:"blob" axios gotcha.
  });
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorDetail(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `migration-terraform-${runId.slice(0, 8)}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function getRuns(): Promise<RunListResponse> {
  return request<RunListResponse>("/api/v1/runs");
}

export async function deleteRun(runId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/v1/runs/${runId}`, {
    method: "DELETE",
  });
}

export async function discoverAws(region: string): Promise<DiscoverResponse> {
  return request<DiscoverResponse>(
    `/api/v1/discover/aws?region=${encodeURIComponent(region)}`,
  );
}

export async function discoverGcp(
  projectId: string,
  region = "us-central1",
): Promise<DiscoverResponse> {
  const params = new URLSearchParams({ project_id: projectId, region });
  return request<DiscoverResponse>(`/api/v1/discover/gcp?${params}`);
}

export async function getHealth(): Promise<{ status: string; version: string }> {
  return request<{ status: string; version: string }>("/api/v1/health");
}
