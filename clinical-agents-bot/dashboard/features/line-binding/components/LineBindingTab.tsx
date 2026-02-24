"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { LineBindingCodeResponse, LineBindingStatusResponse } from "@/lib/types";
import { Button, Card } from "@/components/ui/primitives";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";
import { BindingCodeCard } from "@/components/dashboard/bindings/BindingCodeCard";
import { BindingStatusCard } from "@/components/dashboard/bindings/BindingStatusCard";
import { BindingStepper } from "@/components/dashboard/bindings/BindingStepper";
import { bindingErrorMessage, getBindingStep } from "@/components/dashboard/bindings/bindingStatus";

export function LineBindingTab() {
  const { token, user: currentUser, show, refreshUser: onRefreshUser } = useDashboardContext();
  const [code, setCode] = useState<LineBindingCodeResponse | null>(null);
  const [status, setStatus] = useState<LineBindingStatusResponse | null>(null);

  const currentLineId = (currentUser.platform_id ?? "").trim();
  const isAlreadyBound = currentLineId.length > 0;
  const isVerifiedInCurrentSession = status?.status === "verified";
  const shouldDisableGenerate = isAlreadyBound || isVerifiedInCurrentSession;
  const bindingStep = getBindingStep({
    isAlreadyBound,
    hasCode: Boolean(code),
    status: status?.status ?? null,
  });

  useEffect(() => {
    if (!code?.binding_id) return;
    const timer = setInterval(() => {
      api.getLineBindingStatus(token, code.binding_id)
        .then((res) => {
          setStatus(res);
          if (res.status !== "pending_verification") {
            clearInterval(timer);
            if (res.status === "verified") {
              show("success", "LINE binding verified");
              void api.me(token)
                .then((me) => onRefreshUser(me))
                .catch((err) => show("error", bindingErrorMessage(err)));
            }
            if (res.status === "expired") show("error", "Binding code expired. Generate a new code.");
            if (res.status === "cancelled") show("success", "Binding cancelled.");
            if (res.status === "failed") show("error", `Binding failed${res.failure_reason ? `: ${res.failure_reason}` : ""}`);
          }
        })
        .catch((err) => {
          clearInterval(timer);
          show("error", bindingErrorMessage(err));
        });
    }, (code.poll_interval_sec ?? 2) * 1000);
    return () => clearInterval(timer);
  }, [code?.binding_id, code?.poll_interval_sec, onRefreshUser, show, token]);

  useEffect(() => {
    if (!isAlreadyBound) return;
    if (code) setCode(null);
    if (status) setStatus(null);
  }, [code, isAlreadyBound, status]);

  return (
    <div className="col binding-flow">
      <Card title="LINE Binding">
        <BindingStepper step={bindingStep} />
        {shouldDisableGenerate ? (
          <div className="binding-status-card">
            <div className="binding-details-row">
              <span className="binding-status-pill status-verified">verified</span>
              <span className="small">This account is already linked.</span>
            </div>
            <div className="binding-details-row small">
              {currentLineId ? `LINE ID: ${currentLineId}` : "LINE ID: -"}
            </div>
          </div>
        ) : (
          <>
            <p className="section-intro">Create a one-time code, send it in LINE, then wait for confirmation.</p>
            <div className="row" style={{ marginTop: 12 }}>
              <Button onClick={() => {
                if (isAlreadyBound) {
                  show("success", "This account is already linked.");
                  return;
                }
                api.createLineBindingCode(token).then((res) => { setCode(res); setStatus(null); }).catch((e) => {
                  if (e instanceof ApiError && e.detailCode === "BINDING_ALREADY_ACTIVE") {
                    api.createLineBindingCode(token, true)
                      .then((res) => { setCode(res); setStatus(null); show("success", "Previous code replaced with a new one."); })
                      .catch((err) => show("error", bindingErrorMessage(err)));
                    return;
                  }
                  show("error", bindingErrorMessage(e));
                });
              }}>Generate Binding Code</Button>
              {code ? <Button variant="danger" onClick={() => api.cancelLineBinding(token, code.binding_id).then((res) => setStatus({
                binding_id: code.binding_id,
                username: currentUser.username,
                role: currentUser.role,
                status: res.status,
                expires_at: code.expires_at,
                verified_at: null,
                bound_platform_id_masked: null,
                failure_reason: null,
              })).catch((e) => show("error", bindingErrorMessage(e)))}>Cancel</Button> : null}
            </div>
          </>
        )}
      </Card>

      {!shouldDisableGenerate && code ? (
        <Card title="Step 2: Use This Code in LINE">
          <BindingCodeCard
            code={code.code}
            bindingId={code.binding_id}
            expiresAt={code.expires_at}
            message={code.binding_message}
            onCopyCodeLine={() => {
              void navigator.clipboard.writeText(`驗證碼：${code.code}`).then(
                () => show("success", "Verification code copied"),
                (e) => show("error", bindingErrorMessage(e)),
              );
            }}
          />
        </Card>
      ) : null}

      {status ? (
        <Card title="Step 3: Verification Status">
          <BindingStatusCard
            status={status.status}
            verifiedAt={status.verified_at}
            username={status.username}
            role={status.role}
            lineId={status.bound_platform_id_masked}
          />
        </Card>
      ) : null}
    </div>
  );
}
