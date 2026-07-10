import type {
  ApprovalRequest,
  ConversationDetail,
  ConversationSummary,
  DatasetDetail,
  DatasetSummary,
  EvalRun,
  PaginatedLogs,
  PublicSettings,
  QueryLog,
  QueryResponse,
  StatsOverview,
  TraceEvent,
} from "../types";
import { deepseekRequestHeaders } from "../temporaryCredentials";

export class ApiError extends Error {
  constructor(
    public readonly type: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export async function parseApiResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const error =
      typeof payload === "object" && payload !== null && "error" in payload
        ? (payload as { error?: { type?: string; message?: string } }).error
        : undefined;
    throw new ApiError(
      error?.type ?? "http_error",
      error?.message ?? `Request failed with status ${response.status}`,
      response.status,
    );
  }
  return payload as T;
}

export function isQueryResponse(value: unknown): value is QueryResponse {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<QueryResponse>;
  return (
    typeof item.request_id === "string" &&
    typeof item.query_log_id === "string" &&
    typeof item.status === "string" &&
    typeof item.question === "string" &&
    Array.isArray(item.rows) &&
    Array.isArray(item.trace)
  );
}

export function parseQueryResponse(value: unknown): QueryResponse {
  if (!isQueryResponse(value)) {
    throw new ApiError("invalid_response", "The server returned an invalid query response.", 502);
  }
  return value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  return parseApiResponse<T>(await fetch(path, { ...init, headers }));
}

export const api = {
  datasets: () => request<DatasetSummary[]>("/api/datasets"),
  dataset: (id: string) => request<DatasetDetail>(`/api/datasets/${id}`),
  deleteDataset: (id: string) => request<{ status: string }>(`/api/datasets/${id}`, { method: "DELETE" }),
  conversations: () => request<ConversationSummary[]>("/api/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  createConversation: (datasetId: string, title?: string) =>
    request<ConversationSummary>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId, title }),
    }),
  deleteConversation: (id: string) =>
    request<{ status: string }>(`/api/conversations/${id}`, { method: "DELETE" }),
  approvals: (status?: string) =>
    request<ApprovalRequest[]>(`/api/approvals${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  decideApproval: (id: string, approved: boolean, note?: string, deepseekApiKey = "") =>
    request<QueryResponse>(`/api/approvals/${id}/${approved ? "approve" : "reject"}`, {
      method: "POST",
      headers: deepseekRequestHeaders(deepseekApiKey),
      body: JSON.stringify({ note: note || null }),
    }),
  logs: (params: URLSearchParams) => request<PaginatedLogs>(`/api/logs?${params.toString()}`),
  log: (id: string) => request<QueryLog>(`/api/logs/${id}`),
  events: (id: string) => request<TraceEvent[]>(`/api/logs/${id}/events`),
  stats: () => request<StatsOverview>("/api/stats/overview"),
  runEval: () => request<EvalRun>("/api/evals/run", { method: "POST" }),
  evals: () => request<EvalRun[]>("/api/evals"),
  latestEval: () => request<EvalRun>("/api/evals/latest"),
  settings: () => request<PublicSettings>("/api/settings/public"),
};

export function uploadDataset(
  file: File,
  onProgress: (percent: number) => void,
): Promise<DatasetDetail> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/datasets/upload");
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError("network_error", "Upload connection failed.", 0));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as DatasetDetail);
        return;
      }
      const payload = xhr.response as { error?: { type?: string; message?: string } } | null;
      reject(
        new ApiError(
          payload?.error?.type ?? "invalid_upload",
          payload?.error?.message ?? "Upload failed.",
          xhr.status,
        ),
      );
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
