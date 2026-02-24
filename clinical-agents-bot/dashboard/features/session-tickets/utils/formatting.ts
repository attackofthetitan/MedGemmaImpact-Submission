import React from "react";

export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function formatDateTimeWithRaw(value?: string | null): React.ReactNode {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return React.createElement(
    React.Fragment,
    null,
    parsed.toLocaleString(),
    React.createElement("span", { className: "small" }, ` (${value})`),
  );
}

export function renderDetails(details?: Record<string, unknown>): string {
  if (!details) return "-";
  const entries = Object.entries(details);
  if (!entries.length) return "-";
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(" | ");
}

export function renderTextList(values?: string[] | null): string {
  if (!values || !values.length) return "-";
  return values.join(", ");
}

export function normalizeStatus(status?: string | null): string {
  if (!status) return "unknown";
  return status.toLowerCase().replace(/[\s-]+/g, "_");
}

export function statusClass(status?: string | null): string {
  const normalized = normalizeStatus(status);
  if (normalized.includes("open") || normalized.includes("active")) return "badge-open";
  if (normalized.includes("pending") || normalized.includes("triage")) return "badge-pending";
  if (normalized.includes("closed") || normalized.includes("resolved") || normalized.includes("done")) return "badge-closed";
  return "badge-neutral";
}
