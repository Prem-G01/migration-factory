import axios from "axios";

const client = axios.create({
  baseURL: "http://localhost:8000",
});

export async function analyzeFile(file, target) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target", target || "analyze_only");
  const response = await client.post("/api/v1/analyze", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function getReport(runId) {
  const response = await client.get(`/api/v1/report/${runId}`);
  return response.data;
}

export async function getHtmlReport(runId) {
  const response = await client.get(`/api/v1/report/${runId}/html`);
  return response.data;
}

export async function downloadTerraform(runId) {
  const response = await client.get(`/api/v1/terraform/${runId}`, {
    responseType: "blob",
  });
  return response.data;
}

export async function getRuns() {
  const response = await client.get("/api/v1/runs");
  return response.data.runs;
}

export async function deleteRun(runId) {
  const response = await client.delete(`/api/v1/runs/${runId}`);
  return response.data;
}

export async function getHealth() {
  const response = await client.get("/api/v1/health");
  return response.data;
}

export default client;
