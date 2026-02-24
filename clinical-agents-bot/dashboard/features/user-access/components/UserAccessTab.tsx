"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ACCESS_LEVEL_OPTIONS, RELATIONSHIP_OPTIONS } from "@/lib/model-options";
import type { LineAccessCaptureCodeResponse, LineAccessCaptureStatusResponse, PatientAccess, PatientInfo, User } from "@/lib/types";
import { Button, Card, Input, Select } from "@/components/ui/primitives";
import { OptLabel, ReqLabel } from "@/components/dashboard/common/FormLabels";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";
import { BindingCodeCard } from "@/components/dashboard/bindings/BindingCodeCard";
import { BindingStatusCard } from "@/components/dashboard/bindings/BindingStatusCard";
import { BindingStepper } from "@/components/dashboard/bindings/BindingStepper";
import { bindingErrorMessage, getBindingStep } from "@/components/dashboard/bindings/bindingStatus";

export function UserAccessTab() {
  const { token, user, show } = useDashboardContext();
  const isAdmin = user.role === "admin";
  const canCaptureLineId = user.role === "admin" || user.role === "physician";
  const NEW_LINE_ID_OPTION = "__new_line_id__";
  const [rows, setRows] = useState<PatientAccess[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [form, setForm] = useState<PatientAccess>({ patient_id: "", platform_id: "", relationship: "staff", access_level: "read_only" });
  const [lineIdSelection, setLineIdSelection] = useState("");
  const [isCaptureFlowActive, setIsCaptureFlowActive] = useState(false);
  const [bindingCode, setBindingCode] = useState<LineAccessCaptureCodeResponse | null>(null);
  const [bindingStatus, setBindingStatus] = useState<LineAccessCaptureStatusResponse | null>(null);
  const bindingStep = getBindingStep({
    isAlreadyBound: false,
    hasCode: Boolean(bindingCode),
    status: bindingStatus?.status ?? null,
  });

  const load = useCallback(async (): Promise<User[]> => {
    if (isAdmin) {
      const [relationsRes, usersRes, patientsRes] = await Promise.allSettled([
        api.listRelations(token),
        api.listUsers(token),
        api.listDemoPatients(token),
      ]);

      if (relationsRes.status === "fulfilled") setRows(relationsRes.value.patient_access);
      else show("error", String(relationsRes.reason));

      if (usersRes.status === "fulfilled") setUsers(usersRes.value.users);
      else show("error", String(usersRes.reason));

      if (patientsRes.status === "fulfilled") setPatients(patientsRes.value.patients);
      else show("error", String(patientsRes.reason));

      return usersRes.status === "fulfilled" ? usersRes.value.users : [];
    }

    const patientsRes = await api.listDemoPatients(token);
    setPatients(patientsRes.patients);
    return [];
  }, [isAdmin, show, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectablePlatformIds = useMemo(() => {
    if (isAdmin) {
      return users
        .map((u) => (u.platform_id ?? "").trim())
        .filter(Boolean);
    }
    const selfPlatformId = (user.platform_id ?? "").trim();
    return selfPlatformId ? [selfPlatformId] : [];
  }, [isAdmin, user.platform_id, users]);

  const uniqueSelectablePlatformIds = useMemo(
    () => Array.from(new Set(selectablePlatformIds)),
    [selectablePlatformIds],
  );
  const lineIdOptionsForSelect = useMemo(() => {
    const next = [...uniqueSelectablePlatformIds];
    const currentFormPlatformId = (form.platform_id ?? "").trim();
    const capturedPlatformId = (bindingStatus?.captured_platform_id ?? "").trim();
    if (currentFormPlatformId && !next.includes(currentFormPlatformId)) next.push(currentFormPlatformId);
    if (capturedPlatformId && !next.includes(capturedPlatformId)) next.push(capturedPlatformId);
    return next;
  }, [bindingStatus?.captured_platform_id, form.platform_id, uniqueSelectablePlatformIds]);
  const platformIdToUsersMap = useMemo(() => {
    const map = new Map<string, User[]>();
    const sourceUsers = isAdmin ? users : [user];
    for (const candidate of sourceUsers) {
      const platformId = (candidate.platform_id ?? "").trim();
      if (!platformId) continue;
      const existing = map.get(platformId);
      if (existing) existing.push(candidate);
      else map.set(platformId, [candidate]);
    }
    return map;
  }, [isAdmin, user, users]);
  const lineIdOptionItems = useMemo(() => {
    const capturedPlatformId = (bindingStatus?.captured_platform_id ?? "").trim();
    return lineIdOptionsForSelect.map((platformId) => {
      const owners = platformIdToUsersMap.get(platformId) ?? [];
      if (owners.length === 1) {
        const owner = owners[0];
        return {
          value: platformId,
          label: `${platformId} · ${owner.name} (@${owner.username}, ${owner.role})`,
        };
      }
      if (owners.length > 1) {
        const usernames = owners.map((o) => `@${o.username}`);
        const ownerLabel = owners.length <= 2 ? usernames.join(", ") : `${usernames.slice(0, 2).join(", ")} +${owners.length - 2}`;
        return {
          value: platformId,
          label: `${platformId} · ${ownerLabel} (${owners.length} users)`,
        };
      }
      const suffix = platformId === capturedPlatformId
        ? " (captured)"
        : platformId === (form.platform_id ?? "").trim()
          ? " (custom)"
          : "";
      return {
        value: platformId,
        label: `${platformId}${suffix}`,
      };
    });
  }, [bindingStatus?.captured_platform_id, form.platform_id, lineIdOptionsForSelect, platformIdToUsersMap]);

  const showCapturePanel = canCaptureLineId && (isCaptureFlowActive || Boolean(bindingCode) || Boolean(bindingStatus));

  useEffect(() => {
    if (isAdmin) return;
    if (isCaptureFlowActive) return;
    if (bindingCode || bindingStatus) return;
    if (lineIdSelection.trim()) return;
    if ((form.platform_id ?? "").trim()) return;
    const selfPlatformId = (user.platform_id ?? "").trim();
    if (!selfPlatformId) return;
    setLineIdSelection(selfPlatformId);
    setForm((v) => ({ ...v, platform_id: selfPlatformId }));
  }, [
    bindingCode,
    bindingStatus,
    form.platform_id,
    isAdmin,
    isCaptureFlowActive,
    lineIdSelection,
    user.platform_id,
  ]);

  const handleBindingVerified = useCallback((status: LineAccessCaptureStatusResponse) => {
    const captured = (status.captured_platform_id ?? "").trim();
    if (!captured) {
      show("error", "Capture succeeded but no LINE ID was returned.");
      return;
    }
    setLineIdSelection(captured);
    setForm((v) => ({ ...v, platform_id: captured }));
    show("success", "LINE ID captured and filled into the relation form.");
  }, [show]);

  useEffect(() => {
    if (!canCaptureLineId) return;
    if (!bindingCode?.binding_id) return;
    const timer = setInterval(() => {
      api.getLineAccessCaptureStatus(token, bindingCode.binding_id)
        .then((res) => {
          setBindingStatus(res);
          if (res.status !== "pending_verification") {
            clearInterval(timer);
            if (res.status === "verified") handleBindingVerified(res);
            if (res.status === "expired") show("error", "Binding code expired. Generate a new code.");
            if (res.status === "cancelled") show("success", "Binding cancelled.");
            if (res.status === "failed") show("error", `Binding failed${res.failure_reason ? `: ${res.failure_reason}` : ""}`);
          }
        })
        .catch((err) => {
          clearInterval(timer);
          show("error", bindingErrorMessage(err));
        });
    }, (bindingCode.poll_interval_sec ?? 2) * 1000);
    return () => clearInterval(timer);
  }, [bindingCode?.binding_id, bindingCode?.poll_interval_sec, canCaptureLineId, handleBindingVerified, show, token]);

  return (
    <div className="col">
      {isAdmin ? <Card title="User Directory">
        <p className="section-intro">View all users and linked LINE account IDs.</p>
        <div className="table-wrap"><table><thead><tr><th>User ID</th><th>Username</th><th>Name</th><th>Role</th><th>LINE Account ID</th><th>Active</th></tr></thead><tbody>{users.map((u) => <tr key={u.id}><td>{u.id}</td><td>{u.username}</td><td>{u.name}</td><td>{u.role}</td><td>{u.platform_id || "-"}</td><td>{u.active ? "Yes" : "No"}</td></tr>)}</tbody></table></div>
      </Card> : null}

      <Card title="Patients">
        <p className="section-intro">Browse available patients before assigning access.</p>
        <div className="table-wrap"><table><thead><tr><th>Patient ID</th><th>Name</th><th>Sex</th><th>Age</th><th>MRN</th></tr></thead><tbody>{patients.map((p) => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.name}</td><td>{p.sex}</td><td>{p.age}</td><td>{p.mrn}</td></tr>)}</tbody></table></div>
      </Card>

      {isAdmin ? <Card title="Access Assignments">
        <div className="table-wrap"><table><thead><tr><th>Patient ID</th><th>LINE Account ID</th><th>Relationship</th><th>Access Level</th></tr></thead><tbody>{rows.map((r) => <tr key={`${r.id}-${r.patient_id}`}><td>{r.patient_id}</td><td>{r.platform_id}</td><td>{r.relationship}</td><td>{r.access_level}</td></tr>)}</tbody></table></div>
      </Card> : null}

      <Card title="Create Relation">
        <div className="col">
          <ReqLabel text="Patient ID" />
          <Select required value={form.patient_id} onChange={(e) => setForm((v) => ({ ...v, patient_id: e.target.value }))} disabled={!patients.length}>
            <option value="">-- select patient --</option>
            {patients.map((p) => (
              <option key={p.patient_id} value={p.patient_id}>
                {p.patient_id} · {p.name}
              </option>
            ))}
          </Select>
          <ReqLabel text="LINE Account ID" />
          {canCaptureLineId ? (
            <>
              <Select
                required
                value={lineIdSelection}
                onChange={(e) => {
                  const selectedValue = e.target.value;
                  setLineIdSelection(selectedValue);
                  if (selectedValue === NEW_LINE_ID_OPTION) {
                    setIsCaptureFlowActive(true);
                    setForm((v) => ({ ...v, platform_id: "" }));
                    return;
                  }
                  setIsCaptureFlowActive(false);
                  setBindingCode(null);
                  setBindingStatus(null);
                  setForm((v) => ({ ...v, platform_id: selectedValue }));
                }}
              >
                <option value="">-- select LINE account --</option>
                {lineIdOptionItems.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
                <option value={NEW_LINE_ID_OPTION}>+ New LINE ID (capture)</option>
              </Select>
              <div className="small">Admin can select any user LINE ID. Physician can only select self LINE ID.</div>
              {showCapturePanel ? (
                <>
                  <div className="small">Capture mode records LINE ID for access relation only and does not bind user account.</div>
                  <div className="row">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        api.createLineAccessCaptureCode(token)
                          .then((res) => {
                            setBindingCode(res);
                            setBindingStatus(null);
                          })
                          .catch((e) => {
                            if (e instanceof ApiError && e.detailCode === "BINDING_ALREADY_ACTIVE") {
                              api.createLineAccessCaptureCode(token, true)
                                .then((res) => {
                                  setBindingCode(res);
                                  setBindingStatus(null);
                                  show("success", "Previous code replaced with a new one.");
                                })
                                .catch((err) => show("error", bindingErrorMessage(err)));
                              return;
                            }
                            show("error", bindingErrorMessage(e));
                          });
                      }}
                    >
                      Capture LINE ID For Access
                    </Button>
                    {bindingCode ? (
                      <Button
                        variant="danger"
                        onClick={() =>
                          api.cancelLineAccessCapture(token, bindingCode.binding_id)
                            .then((res) => setBindingStatus({
                              binding_id: bindingCode.binding_id,
                              username: user.username,
                              role: user.role,
                              status: res.status,
                              expires_at: bindingCode.expires_at,
                              verified_at: null,
                              bound_platform_id_masked: null,
                              captured_platform_id: null,
                              failure_reason: null,
                            }))
                            .catch((e) => show("error", bindingErrorMessage(e)))
                        }
                      >
                        Cancel Bind
                      </Button>
                    ) : null}
                  </div>
                  {bindingCode ? (
                    <div className="binding-flow" style={{ marginTop: 8 }}>
                      <BindingStepper step={bindingStep} />
                      <BindingCodeCard
                        code={bindingCode.code}
                        bindingId={bindingCode.binding_id}
                        expiresAt={bindingCode.expires_at}
                        message={bindingCode.binding_message}
                        onCopyCodeLine={() => {
                          void navigator.clipboard.writeText(`驗證碼：${bindingCode.code}`).then(
                            () => show("success", "Verification code copied"),
                            (e) => show("error", bindingErrorMessage(e)),
                          );
                        }}
                      />
                      {bindingStatus ? (
                        <BindingStatusCard
                          status={bindingStatus.status}
                          verifiedAt={bindingStatus.verified_at}
                          username={bindingStatus.username}
                          role={bindingStatus.role}
                          lineId={bindingStatus.captured_platform_id ?? bindingStatus.bound_platform_id_masked}
                        />
                      ) : null}
                    </div>
                  ) : null}
                </>
              ) : null}
            </>
          ) : (
            <>
              <Input required placeholder="platform_id" value={form.platform_id} onChange={(e) => setForm((v) => ({ ...v, platform_id: e.target.value }))} />
              <div className="small">Physician mode: enter LINE Account ID manually.</div>
            </>
          )}
          <ReqLabel text="Relationship" />
          <Select required value={form.relationship} onChange={(e) => setForm((v) => ({ ...v, relationship: e.target.value as PatientAccess["relationship"] }))}>{RELATIONSHIP_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          <OptLabel text="Access Level" />
          <Select value={form.access_level} onChange={(e) => setForm((v) => ({ ...v, access_level: e.target.value as PatientAccess["access_level"] }))}>{ACCESS_LEVEL_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          <Button disabled={!form.platform_id} onClick={() => api.createRelation(token, form).then(() => { show("success", "Relation created"); void load(); }).catch((e) => show("error", String(e)))}>Create</Button>
        </div>
      </Card>
    </div>
  );
}
