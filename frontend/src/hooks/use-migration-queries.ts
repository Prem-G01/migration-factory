import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  analyzeFile,
  analyzeRawData,
  deleteRun,
  discoverAws,
  discoverGcp,
  downloadTerraform,
  getHealth,
  getReport,
  getRuns,
} from "@/services/migration-api";
import type { MigrationTarget } from "@/types/migration";

export const queryKeys = {
  health: ["health"] as const,
  runs: ["runs"] as const,
  report: (runId: string) => ["report", runId] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: getRuns,
  });
}

export function useReport(runId: string | null) {
  return useQuery({
    queryKey: queryKeys.report(runId ?? ""),
    queryFn: () => getReport(runId as string),
    enabled: runId !== null,
  });
}

export function useAnalyzeFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, target }: { file: File; target?: MigrationTarget }) =>
      analyzeFile(file, target),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useAnalyzeRawData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      rawData,
      target,
    }: {
      rawData: unknown;
      target?: MigrationTarget;
    }) => analyzeRawData(rawData, target),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useDeleteRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => deleteRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useDownloadTerraform() {
  return useMutation({
    mutationFn: (runId: string) => downloadTerraform(runId),
  });
}

export function useDiscoverAws() {
  return useMutation({
    mutationFn: (region: string) => discoverAws(region),
  });
}

export function useDiscoverGcp() {
  return useMutation({
    mutationFn: ({ projectId, region }: { projectId: string; region?: string }) =>
      discoverGcp(projectId, region),
  });
}
