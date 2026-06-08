export interface HealthResponse {
  status: string;
  version: string;
  app: string;
}

export interface ServiceStatus {
  status: string;
  latency_ms: number;
  detail?: string;
}

export interface StatusResponse {
  status: string;
  version: string;
  services: Record<string, ServiceStatus>;
  llm_model: string;
  embed_model: string;
  context_top_k: number;
  max_context_tokens: number;
  guardrail_threshold: number;
}

export interface UploadResponse {
  document_id: string;
  tender_id: string;
  filename: string;
  minio_path: string;
  file_size: number;
}

export interface ProcessResponse {
  document_id: string;
  page_count: number;
  chunk_count: number;
  status: string;
}

export interface DocumentInfo {
  id: string;
  tender_id: string;
  filename: string;
  original_filename: string;
  minio_path: string;
  file_size: number;
  status: string;
  page_count: number;
}

export interface SourceItem {
  chunk_id: string | null;
  document_id: string | null;
  page_number: number | null;
  score: number;
}

export interface QueryResponse {
  answer: string;
  question: string;
  sources: SourceItem[];
  route?: "small" | "large";
  route_reason?: string;
}

export interface FullAnalysisResponse {
  workflow_id: string;
  tender_id: string;
  correlation_id: string;
  status: string;
  steps_completed: string[];
  errors: string[];
  final_report: Record<string, unknown> | null;
}

export interface WorkflowStatusResponse {
  workflow_id: string;
  tender_id: string;
  correlation_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface ComplianceReportResponse {
  id: string;
  workflow_id: string;
  tender_id: string;
  compliance_score: number;
  risk_level: string;
  issues: Array<Record<string, unknown>>;
  recommendations: string[];
  created_at: string;
}

export interface AuditReportResponse {
  id: string;
  workflow_id: string;
  tender_id: string;
  legal_output: Record<string, unknown> | null;
  proposal_output: Record<string, unknown> | null;
  audit_output: Record<string, unknown> | null;
  final_report: Record<string, unknown> | null;
  created_at: string;
}

export interface DashboardResponse {
  tender_id: string;
  workflow_id: string | null;
  compliance_score: number | null;
  risk_level: string | null;
  requirements_count: number;
  checklist_items: number;
  issues_count: number;
  recommendations: string[];
  key_dates: Array<Record<string, unknown>>;
}

export interface CostReport {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  avg_tokens_per_request: number;
  tokens_per_second_current: number;
  cost_local_usd: number;
  cost_aks_cpu_per_1k_requests_usd: number;
  cost_aks_gpu_per_1k_requests_usd: number;
  cost_vllm_per_1k_requests_usd: number;
  recommendations: string[];
  breakdown: Record<string, unknown>;
  prometheus_available: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: SourceItem[];
  route?: "small" | "large";
  route_reason?: string;
  blocked?: boolean;
  timestamp: number;
}
