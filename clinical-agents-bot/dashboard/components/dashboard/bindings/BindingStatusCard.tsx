"use client";

import { bindingStatusClass, describeBindingStatus } from "@/components/dashboard/bindings/bindingStatus";

export function BindingStatusCard({
  status,
  verifiedAt,
  username,
  role,
  lineId,
}: {
  status: string;
  verifiedAt?: string | null;
  username?: string;
  role?: string;
  lineId?: string | null;
}) {
  return (
    <div className="binding-status-card">
      <div className="binding-details-row">
        <span className={`binding-status-pill ${bindingStatusClass(status)}`}>{status.replace(/_/g, " ")}</span>
        <span className="small">{describeBindingStatus(status)}</span>
      </div>
      <div className="binding-details-row small">
        {verifiedAt ? `Verified At: ${verifiedAt}` : "Verified At: -"}
        {username ? ` · User: ${username}${role ? ` (${role})` : ""}` : ""}
        {lineId ? ` · LINE ID: ${lineId}` : ""}
      </div>
    </div>
  );
}
