import type {
  Allergy,
  DocumentEntry,
  Encounter,
  ImagingReport,
  LineAccessCaptureCodeResponse,
  LineAccessCaptureStatusResponse,
  LabResult,
  LineBindingCodeResponse,
  LineBindingStatusResponse,
  Medication,
  PatientAccess,
  PatientInfo,
  PatientInfoCreatePayload,
  PatientSummaryResponse,
  Problem,
  RagDeleteDocumentResponse,
  RagDocumentDetailResponse,
  RagDocumentsResponse,
  RagHealthResponse,
  RagIngestBatchResponse,
  RagIngestFileResponse,
  RagIngestTextRequest,
  RagIngestTextResponse,
  RagSearchRequest,
  RagSearchResponse,
  RagSeedResponse,
  ReviewRequest,
  ReviewResponse,
  SendLineRequest,
  SendLineResponse,
  SessionDetailResponse,
  SessionListResponse,
  TokenResponse,
  User,
  UserCreatePayload,
  UserUpdatePayload,
} from "@/lib/types";

const RAW_BASE_URL = process.env.NEXT_PUBLIC_AGENT_BASE_URL ?? "";
function resolveBaseUrl(): string {
  if (typeof window === "undefined") return RAW_BASE_URL || "http://localhost:8090";
  if (!RAW_BASE_URL) return `${window.location.origin}/dashboard`;
  if (RAW_BASE_URL.startsWith("/")) return RAW_BASE_URL.replace(/\/$/, "");
  try {
    const u = new URL(RAW_BASE_URL, window.location.origin);
    const isLocalhostBase = u.hostname === "localhost" || u.hostname === "127.0.0.1";
    const isLocalhostPage = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

    // If a localhost URL was baked into a deployed build, use same-origin dashboard path.
    if (isLocalhostBase && !isLocalhostPage) {
      return `${window.location.origin}/dashboard`;
    }

    // Avoid mixed-content requests when page is loaded via HTTPS.
    if (window.location.protocol === "https:" && u.protocol === "http:") {
      if (u.hostname === window.location.hostname && !window.location.port) {
        return `${window.location.origin}/dashboard`;
      }
      u.protocol = "https:";
    }

    if (
      isLocalhostBase &&
      window.location.hostname !== "localhost" &&
      window.location.hostname !== "127.0.0.1"
    ) {
      return `${window.location.origin}/dashboard`;
    }
    return u.toString().replace(/\/$/, "");
  } catch {
    return RAW_BASE_URL;
  }
}
const BASE_URL = resolveBaseUrl();

type RequestInitWithAuth = RequestInit & { token?: string };

type ApiErrorDetail = {
  code?: string;
  message?: string;
  retryable?: boolean;
};

export class ApiError extends Error {
  statusCode: number;
  detailCode?: string;
  retryable?: boolean;

  constructor(message: string, statusCode: number, detail?: ApiErrorDetail) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.detailCode = detail?.code;
    this.retryable = detail?.retryable;
  }
}

function parseApiErrorPayload(text: string): { message: string; detail?: ApiErrorDetail } {
  if (!text) return { message: "Request failed" };
  try {
    const body = JSON.parse(text) as { detail?: string | ApiErrorDetail };
    if (typeof body.detail === "string") return { message: body.detail };
    if (body.detail && typeof body.detail === "object") {
      return {
        message: body.detail.message || "Request failed",
        detail: body.detail,
      };
    }
  } catch {
    return { message: text };
  }
  return { message: text };
}

async function http<T>(path: string, init: RequestInitWithAuth = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (init.token) headers.set("Authorization", `Bearer ${init.token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.get("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const normalizedPath = path === "/" ? path : path.replace(/\/+$/, "");

  const response = await fetch(`${BASE_URL}${normalizedPath}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    const parsed = parseApiErrorPayload(text);
    throw new ApiError(parsed.message || `Request failed: ${response.status}`, response.status, parsed.detail);
  }

  if (response.status === 204) return {} as T;
  return (await response.json()) as T;
}

const realApi = {
  login: (username: string, password: string) =>
    http<TokenResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: (token: string) => http<User>("/api/v1/auth/me", { token }),
  listUsers: (token: string) => http<{ users: User[] }>("/api/v1/auth/users", { token }),
  registerUser: (token: string, payload: UserCreatePayload) =>
    http<User>("/api/v1/auth/register", { token, method: "POST", body: JSON.stringify(payload) }),
  updateUser: (token: string, payload: UserUpdatePayload) =>
    http<User>("/api/v1/auth/user", { token, method: "PATCH", body: JSON.stringify(payload) }),
  listDemoPatients: (token: string) => http<{ patients: PatientInfo[] }>("/api/v1/demo/patients", { token }),
  patientSummary: (token: string, patientId: string) => http<PatientSummaryResponse>(`/api/v1/patient/${patientId}`, { token }),
  listDocuments: (token: string, patientId: string) => http<{ patient_id: string; documents: DocumentEntry[] }>(`/api/v1/patient/${patientId}/documents`, { token }),
  createPatient: (token: string, payload: PatientInfoCreatePayload) => http<{ patient_id: string }>("/api/v1/patient", { token, method: "POST", body: JSON.stringify(payload) }),
  addMedication: (token: string, patientId: string, payload: Medication) => http<{ id: number; patient_id: string }>(`/api/v1/patient/${patientId}/medications`, { token, method: "POST", body: JSON.stringify(payload) }),
  addAllergy: (token: string, patientId: string, payload: Allergy) => http<{ id: number; patient_id: string }>(`/api/v1/patient/${patientId}/allergies`, { token, method: "POST", body: JSON.stringify(payload) }),
  addProblem: (token: string, patientId: string, payload: Problem) => http<{ id: number; patient_id: string }>(`/api/v1/patient/${patientId}/problems`, { token, method: "POST", body: JSON.stringify(payload) }),
  addLab: (token: string, patientId: string, payload: LabResult) => http<{ id: number; patient_id: string }>(`/api/v1/patient/${patientId}/labs`, { token, method: "POST", body: JSON.stringify(payload) }),
  addImaging: (token: string, patientId: string, payload: ImagingReport) => http<{ report_id: string; patient_id: string }>(`/api/v1/patient/${patientId}/imaging`, { token, method: "POST", body: JSON.stringify(payload) }),
  addEncounter: (token: string, patientId: string, payload: Encounter) => http<{ encounter_id: string; patient_id: string }>(`/api/v1/patient/${patientId}/encounters`, { token, method: "POST", body: JSON.stringify(payload) }),
  uploadDocument: async (token: string, patientId: string, file: File, docType: string, description: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    if (description) fd.append("description", description);
    return http<{ id: number; patient_id: string }>(`/api/v1/patient/${patientId}/documents`, { token, method: "POST", body: fd });
  },
  listRelations: (token: string) => http<{ patient_access: PatientAccess[] }>("/api/v1/patient_access", { token }),
  createRelation: (token: string, payload: PatientAccess) => http<{ id: number }>("/api/v1/patient_access", { token, method: "POST", body: JSON.stringify(payload) }),
  getRole: (token: string, platformId: string) => http<{ role: string }>(`/api/v1/user/role/${platformId}`, { token }),
  getPlatformPatient: (token: string, platformId: string) => http<{ patient_id: string }>(`/api/v1/platform/patient?platform_id=${encodeURIComponent(platformId)}`, { token }),
  getStaffByRelationship: (token: string, relationship: string, patientId: string) =>
    http<{ staff_id: string }>(`/api/v1/patient/staff/${relationship}?patient_id=${encodeURIComponent(patientId)}`, { token }),
  createLineBindingCode: (token: string, forceRegenerate = false) => http<LineBindingCodeResponse>(`/api/v1/line-binding/code?force_regenerate=${forceRegenerate ? "true" : "false"}`, { token, method: "POST" }),
  getLineBindingStatus: (token: string, bindingId: string) => http<LineBindingStatusResponse>(`/api/v1/line-binding/code/${bindingId}`, { token }),
  cancelLineBinding: (token: string, bindingId: string) => http<{ binding_id: string; status: LineBindingStatusResponse["status"] }>(`/api/v1/line-binding/code/${bindingId}/cancel`, { token, method: "POST" }),
  createLineAccessCaptureCode: (token: string, forceRegenerate = false) => http<LineAccessCaptureCodeResponse>(`/api/v1/line-binding/access/code?force_regenerate=${forceRegenerate ? "true" : "false"}`, { token, method: "POST" }),
  getLineAccessCaptureStatus: (token: string, bindingId: string) => http<LineAccessCaptureStatusResponse>(`/api/v1/line-binding/access/code/${bindingId}`, { token }),
  cancelLineAccessCapture: (token: string, bindingId: string) => http<{ binding_id: string; status: LineAccessCaptureStatusResponse["status"] }>(`/api/v1/line-binding/access/code/${bindingId}/cancel`, { token, method: "POST" }),
  listSessions: (token: string) => http<SessionListResponse>("/api/v1/sessions", { token }),
  getSession: (token: string, sessionId: string) => http<SessionDetailResponse>(`/api/v1/session/${encodeURIComponent(sessionId)}`, { token }),
  reviewSession: (token: string, payload: ReviewRequest) => http<ReviewResponse>("/api/v1/review", { token, method: "POST", body: JSON.stringify(payload) }),
  sendToLine: (token: string, payload: SendLineRequest) =>
    http<SendLineResponse>(`/api/v1/api/line/send?session_id=${encodeURIComponent(payload.session_id)}&patient_id=${encodeURIComponent(payload.patient_id)}`, {
      token,
      method: "POST",
    }),
  ragHealth: (token: string) => http<RagHealthResponse>("/api/v1/rag/health", { token }),
  ragSearch: (token: string, payload: RagSearchRequest) => http<RagSearchResponse>("/api/v1/rag/search", { token, method: "POST", body: JSON.stringify(payload) }),
  ragIngestText: (token: string, payload: RagIngestTextRequest) => http<RagIngestTextResponse>("/api/v1/rag/ingest/text", { token, method: "POST", body: JSON.stringify(payload) }),
  ragIngestFile: async (token: string, file: File, meta: { source_type: string; title?: string; department?: string; tags?: string; process_images?: boolean }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("source_type", meta.source_type);
    if (meta.title) fd.append("title", meta.title);
    if (meta.department) fd.append("department", meta.department);
    if (meta.tags) fd.append("tags", meta.tags);
    fd.append("process_images", `${meta.process_images ?? true}`);
    return http<RagIngestFileResponse>("/api/v1/rag/ingest/file", { token, method: "POST", body: fd });
  },
  ragIngestBatch: async (token: string, files: File[], meta: { source_type: string; department?: string }) => {
    const fd = new FormData();
    for (const file of files) fd.append("files", file);
    fd.append("source_type", meta.source_type);
    if (meta.department) fd.append("department", meta.department);
    return http<RagIngestBatchResponse>("/api/v1/rag/ingest/batch", { token, method: "POST", body: fd });
  },
  ragListDocuments: (token: string) => http<RagDocumentsResponse>("/api/v1/rag/documents", { token }),
  ragGetDocument: (token: string, docId: string) => http<RagDocumentDetailResponse>(`/api/v1/rag/documents/${encodeURIComponent(docId)}`, { token }),
  ragDeleteDocument: (token: string, docId: string) => http<RagDeleteDocumentResponse>(`/api/v1/rag/documents/${encodeURIComponent(docId)}`, { token, method: "DELETE" }),
  ragStats: (token: string) => http<Record<string, unknown>>("/api/v1/rag/stats", { token }),
  ragSeed: (token: string) => http<RagSeedResponse>("/api/v1/rag/seed", { token, method: "POST" }),
};

export const api = {
  mode: "real" as const,
  ...realApi,
};
