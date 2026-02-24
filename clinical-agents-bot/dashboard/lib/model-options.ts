import type {
  Allergy,
  DocumentEntry,
  ImagingFinding,
  LabResult,
  Medication,
  PatientAccess,
  PatientInfoCreatePayload,
  Problem,
  RagSearchType,
  RagSourceType,
  UserCreatePayload,
  UserRole,
  UserUpdatePayload,
} from "@/lib/types";

export const USER_ROLE_OPTIONS = ["admin", "physician", "nurse", "staff"] as const satisfies readonly UserRole[];

export const SEX_OPTIONS = ["male", "female", "other"] as const satisfies readonly PatientInfoCreatePayload["sex"][];

export const MEDICATION_STATUS_OPTIONS = ["active", "discontinued", "on_hold"] as const satisfies readonly Medication["status"][];

export const ALLERGY_SEVERITY_OPTIONS = ["mild", "moderate", "severe"] as const satisfies readonly Exclude<Allergy["severity"], null | undefined>[];

export const PROBLEM_STATUS_OPTIONS = ["active", "resolved", "inactive"] as const satisfies readonly Problem["status"][];

export const LAB_FLAG_OPTIONS = ["normal", "low", "high", "critical_low", "critical_high"] as const satisfies readonly Exclude<LabResult["flag"], null | undefined>[];

export const IMAGING_FINDING_SEVERITY_OPTIONS = ["normal", "mild", "moderate", "severe"] as const satisfies readonly Exclude<ImagingFinding["severity"], null | undefined>[];

export const DOCUMENT_TYPE_OPTIONS = ["scan", "photo", "report", "other"] as const satisfies readonly DocumentEntry["doc_type"][];

export const RELATIONSHIP_OPTIONS = ["family", "self", "front_desk", "admin", "physician", "nurse", "staff", "pharmacist", "emergency"] as const satisfies readonly PatientAccess["relationship"][];

export const ACCESS_LEVEL_OPTIONS = ["full", "limited", "read_only"] as const satisfies readonly PatientAccess["access_level"][];

export const RAG_SEARCH_TYPE_OPTIONS = ["hybrid", "semantic", "keyword"] as const satisfies readonly RagSearchType[];

export const RAG_SOURCE_TYPE_OPTIONS = ["sop", "education", "protocol", "clinical_note"] as const satisfies readonly RagSourceType[];

export type UserRoleFormValue = UserCreatePayload["role"] | UserUpdatePayload["role"];
