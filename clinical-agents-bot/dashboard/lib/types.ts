export type UserRole = "admin" | "physician" | "nurse" | "staff";

export interface User {
  id?: number;
  platform_id?: string | null;
  username: string;
  role: UserRole;
  name: string;
  active?: boolean;
  created_at?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface UserCreatePayload {
  username: string;
  password: string;
  role: UserRole;
  name: string;
}

export interface UserUpdatePayload {
  username: string;
  platform_id?: string | null;
  role?: UserRole;
  name?: string;
  active?: boolean;
}

export interface PatientInfo {
  patient_id: string;
  name: string;
  age: number;
  sex: "male" | "female" | "other";
  mrn: string;
  dob: string;
}

export interface PatientInfoCreatePayload {
  patient_id?: string;
  name: string;
  sex: "male" | "female" | "other";
  mrn?: string;
  dob: string;
}

export interface Medication {
  id?: number;
  name: string;
  dose?: string | null;
  frequency?: string | null;
  route?: string | null;
  indication?: string | null;
  start_date?: string | null;
  status: "active" | "discontinued" | "on_hold";
}

export interface Allergy {
  id?: number;
  allergen: string;
  reaction?: string | null;
  severity?: "mild" | "moderate" | "severe" | null;
  verified: boolean;
}

export interface Problem {
  id?: number;
  icd_code?: string | null;
  description: string;
  onset_date?: string | null;
  status: "active" | "resolved" | "inactive";
}

export interface LabResult {
  id?: number;
  test_name: string;
  value: string;
  unit?: string | null;
  reference_range?: string | null;
  flag?: "normal" | "low" | "high" | "critical_low" | "critical_high" | null;
  collected_date?: string | null;
  notes?: string | null;
}

export interface ImagingFinding {
  location: string;
  finding: string;
  severity?: "normal" | "mild" | "moderate" | "severe" | null;
}

export interface ImagingReport {
  report_id: string;
  patient_id?: string | null;
  study_type: string;
  study_date?: string | null;
  body_part: string;
  indication?: string | null;
  technique?: string | null;
  findings: ImagingFinding[];
  impression: string[];
  critical_findings: string[];
  radiologist?: string | null;
}

export interface Encounter {
  encounter_id: string;
  date: string;
  type: string;
  provider: string;
  chief_complaint?: string | null;
  diagnoses: string[];
  summary?: string | null;
}

export interface DocumentEntry {
  id?: number;
  patient_id: string;
  doc_type: "scan" | "photo" | "report" | "other";
  filename: string;
  mime_type?: string | null;
  description?: string | null;
  uploaded_by?: string | null;
  created_at?: string | null;
}

export interface PatientAccess {
  id?: number;
  patient_id: string;
  platform_id: string;
  relationship: "family" | "self" | "front_desk" | "admin" | "physician" | "nurse" | "staff" | "pharmacist" | "emergency";
  access_level: "full" | "limited" | "read_only";
}

export interface PatientSummaryResponse {
  patient: PatientInfo;
  medications: Medication[];
  allergies: Allergy[];
  problems: Problem[];
  recent_labs: LabResult[];
  recent_imaging: ImagingReport[];
  recent_encounters: Encounter[];
}

export type LineBindingStatus = "pending_verification" | "verified" | "expired" | "cancelled" | "failed";

export interface LineBindingCodeResponse {
  binding_id: string;
  code: string;
  status: LineBindingStatus;
  expires_at: string;
  poll_interval_sec: number;
  binding_message: string;
}

export interface LineBindingStatusResponse {
  binding_id: string;
  username: string;
  role: UserRole;
  status: LineBindingStatus;
  expires_at: string;
  verified_at: string | null;
  bound_platform_id_masked: string | null;
  failure_reason: string | null;
}

export interface LineAccessCaptureCodeResponse {
  binding_id: string;
  code: string;
  status: LineBindingStatus;
  expires_at: string;
  poll_interval_sec: number;
  binding_message: string;
}

export interface LineAccessCaptureStatusResponse {
  binding_id: string;
  username: string;
  role: UserRole;
  status: LineBindingStatus;
  expires_at: string;
  verified_at: string | null;
  bound_platform_id_masked: string | null;
  captured_platform_id: string | null;
  failure_reason: string | null;
}

export type RagSearchType = "semantic" | "keyword" | "hybrid";
export type RagSourceType = "sop" | "education" | "protocol" | "clinical_note";

export interface RagHealthResponse {
  status: "healthy" | "degraded";
  timestamp: string;
  embedding_service: {
    url: string;
    model: string;
    connected: boolean;
  };
  vector_store: Record<string, unknown>;
  documents: number;
}

export interface RagSearchRequest {
  query: string;
  top_k: number;
  search_type: RagSearchType;
  filter_source_type?: RagSourceType | null;
  filter_department?: string | null;
  rerank: boolean;
}

export interface RagSearchResult {
  chunk_id: string;
  doc_id: string;
  content: string;
  score: number;
  search_type: string;
  metadata: Record<string, unknown>;
  is_image: boolean;
}

export interface RagSearchResponse {
  query: string;
  results: RagSearchResult[];
  total_results: number;
  search_type: string;
  reranked: boolean;
}

export interface RagIngestTextRequest {
  text: string;
  source: string;
  source_type: RagSourceType;
  title?: string | null;
  department?: string | null;
  tags?: string[];
}

export interface RagIngestTextResponse {
  status: string;
  doc_id: string;
  message: string;
}

export interface RagIngestFileResponse {
  status: string;
  doc_id: string;
  doc_type: string;
  content_length: number;
  images_processed: number;
  message: string;
}

export interface RagIngestBatchResponse {
  total: number;
  success: number;
  failed: number;
  results: Array<{
    filename: string;
    status: string;
    doc_id?: string;
    error?: string;
  }>;
}

export interface RagDocumentListItem {
  doc_id: string;
  source: string;
  source_type: string;
  title?: string | null;
  doc_type: string;
  created_at: string;
  content_length: number;
  images: number;
}

export interface RagDocumentsResponse {
  documents: RagDocumentListItem[];
  total: number;
}

export interface RagDocumentDetailResponse {
  doc_id: string;
  source: string;
  source_type: string;
  title?: string | null;
  doc_type: string;
  created_at: string;
  content: string;
  content_length: number;
  images: Array<{
    image_id: string;
    description?: string | null;
    has_base64: boolean;
  }>;
  metadata: {
    department?: string | null;
    tags: string[];
    language?: string | null;
  };
}

export interface RagDeleteDocumentResponse {
  status: string;
  doc_id: string;
}

export interface RagSeedResponse {
  status?: string;
  message?: string;
  added?: number;
  total?: number;
}

export interface SessionListItem {
  session_id: string;
  patient_id: string | null;
  status: string;
  created_at: string;
}

export interface SessionListResponse {
  sessions: SessionListItem[];
  total: number;
}

export interface TriageView {
  destination?: string;
  urgency?: string;
  reasoning?: string;
  confidence?: number;
}

export interface CaseCardView {
  case_id?: string;
  context_id?: string;
  patient_id?: string | null;
  timestamp?: string;
  summary?: string;
  chief_complaint?: string;
  relevant_history?: string;
  current_meds_summary?: string | null;
  recent_labs_summary?: string | null;
  recent_imaging_summary?: string | null;
  pertinent_positives?: string[];
  pertinent_negatives?: string[];
  information_gaps?: string[];
  triage?: TriageView;
}

export interface ReplyView {
  draft_id?: string;
  locale?: string;
  greeting?: string;
  acknowledgment?: string;
  understanding?: string;
  response?: string;
  action_items?: string[];
  warning_signs?: string[];
  follow_up?: string | null;
  closing?: string;
  emergency_info?: string | null;
}

export interface SessionTicketView {
  ticket_id: string;
  patient_id?: string | null;
  intent?: string;
  risk_level?: string;
  red_flags?: string[];
  destination?: string;
  urgency?: string;
  case_card?: CaseCardView;
  draft_reply?: ReplyView | null;
  status?: string;
  created_at?: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  physician_notes?: string | null;
}

export interface SessionAuditLogEntry {
  timestamp: string;
  action: string;
  details?: Record<string, unknown>;
}

export interface SessionDetailResponse {
  session_id: string;
  patient_id: string | null;
  status: string;
  clarification_count: number;
  has_ticket: boolean;
  ticket_status: string | null;
  ticket: SessionTicketView | null;
  created_at: string;
  audit_log: SessionAuditLogEntry[];
}

export interface ReviewRequest {
  session_id: string;
  approved: boolean;
  physician_notes?: string | null;
  key_points?: string[] | null;
}

export interface ReviewResponse {
  session_id: string;
  patient_id?: string | null;
  status: "ready_to_send" | "needs_revision" | "escalated" | string;
  ticket_id?: string;
  ticket?: SessionTicketView;
  draft_reply?: ReplyView;
  qa_result?: Record<string, unknown>;
  physician_notes?: string | null;
  next_action?: string;
  hint?: string;
}

export interface SendLineRequest {
  session_id: string;
  patient_id: string;
}

export interface SendLineResponse {
  message?: string;
  status?: string;
  session_id?: string;
  ticket_id?: string;
  next_action?: string;
}
