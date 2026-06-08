import type {
  HealthResponse,
  StatusResponse,
  UploadResponse,
  ProcessResponse,
  DocumentInfo,
  QueryResponse,
  FullAnalysisResponse,
  WorkflowStatusResponse,
  ComplianceReportResponse,
  AuditReportResponse,
  DashboardResponse,
  CostReport,
} from "./types";

// Always use relative path — Next.js rewrites proxy this to the backend (no CORS)
const BASE = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...options,
    headers:
      options?.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  status: () => request<StatusResponse>("/status"),

  uploadDocument: (tenderId: string, file: File) => {
    const form = new FormData();
    form.append("tender_id", tenderId);
    form.append("file", file);
    return request<UploadResponse>("/documents/upload", {
      method: "POST",
      body: form,
    });
  },

  processDocument: (documentId: string) =>
    request<ProcessResponse>(
      `/documents/process?document_id=${encodeURIComponent(documentId)}`,
      { method: "POST" }
    ),

  getDocument: (documentId: string) =>
    request<DocumentInfo>(`/documents/${encodeURIComponent(documentId)}`),

  ragQuery: (
    question: string,
    tenderId?: string,
    documentId?: string,
    topK = 5
  ) =>
    request<QueryResponse>("/rag/query", {
      method: "POST",
      body: JSON.stringify({
        question,
        tender_id: tenderId || null,
        document_id: documentId || null,
        top_k: topK,
      }),
    }),

  runFullAnalysis: (tenderId: string) =>
    request<FullAnalysisResponse>("/workflow/full-analysis", {
      method: "POST",
      body: JSON.stringify({ tender_id: tenderId }),
    }),

  getWorkflow: (workflowId: string) =>
    request<WorkflowStatusResponse>(
      `/workflow/${encodeURIComponent(workflowId)}`
    ),

  getReport: (workflowId: string) =>
    request<AuditReportResponse>(
      `/reports/${encodeURIComponent(workflowId)}`
    ),

  getCompliance: (tenderId: string) =>
    request<ComplianceReportResponse>(
      `/compliance/${encodeURIComponent(tenderId)}`
    ),

  getDashboard: (tenderId: string) =>
    request<DashboardResponse>(
      `/dashboard/${encodeURIComponent(tenderId)}`
    ),

  getCostAnalysis: () => request<CostReport>("/cost/analysis"),
};
