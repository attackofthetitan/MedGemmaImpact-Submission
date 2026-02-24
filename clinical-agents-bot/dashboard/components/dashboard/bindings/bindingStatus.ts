import { ApiError } from "@/lib/api";

export function normalizeBindingStatus(status?: string | null): string {
  if (!status) return "pending_verification";
  return status.toLowerCase().replace(/[\s-]+/g, "_");
}

export function bindingStatusClass(status?: string | null): string {
  const normalized = normalizeBindingStatus(status);
  if (normalized === "verified") return "status-verified";
  if (normalized === "pending_verification") return "status-pending";
  if (normalized === "cancelled" || normalized === "canceled") return "status-cancelled";
  if (normalized === "expired") return "status-expired";
  return "status-failed";
}

export function describeBindingStatus(status: string): string {
  const normalized = normalizeBindingStatus(status);
  if (normalized === "verified") return "Account successfully linked.";
  if (normalized === "expired") return "Verification code expired. Generate a new code.";
  if (normalized === "cancelled") return "Binding request cancelled.";
  if (normalized === "failed") return "Binding failed. Please try again.";
  return "Waiting for verification.";
}

export function bindingErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.detailCode === "BINDING_ALREADY_ACTIVE") {
      return "An active binding code already exists.";
    }
    return error.message || "Binding request failed";
  }
  return String(error);
}

export function getBindingStep({
  isAlreadyBound,
  hasCode,
  status,
}: {
  isAlreadyBound: boolean;
  hasCode: boolean;
  status?: string | null;
}): 1 | 2 | 3 {
  if (isAlreadyBound || normalizeBindingStatus(status) === "verified") return 3;
  if (hasCode) return 2;
  return 1;
}
