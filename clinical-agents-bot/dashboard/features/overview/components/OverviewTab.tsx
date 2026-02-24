"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DocumentEntry, PatientInfo, PatientSummaryResponse } from "@/lib/types";
import { Button, Card } from "@/components/ui/primitives";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";

export function OverviewTab() {
  const { token, show } = useDashboardContext();
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [selectedPatientIds, setSelectedPatientIds] = useState<string[]>([]);
  const [detailsByPatientId, setDetailsByPatientId] = useState<Record<string, PatientSummaryResponse>>({});
  const [documentsByPatientId, setDocumentsByPatientId] = useState<Record<string, DocumentEntry[]>>({});
  const [loadingSummaryByPatientId, setLoadingSummaryByPatientId] = useState<Record<string, boolean>>({});
  const [loadingDocumentsByPatientId, setLoadingDocumentsByPatientId] = useState<Record<string, boolean>>({});
  const [summaryErrorByPatientId, setSummaryErrorByPatientId] = useState<Record<string, string>>({});
  const [documentsErrorByPatientId, setDocumentsErrorByPatientId] = useState<Record<string, string>>({});
  const detailsRef = useRef(detailsByPatientId);
  const documentsRef = useRef(documentsByPatientId);

  detailsRef.current = detailsByPatientId;
  documentsRef.current = documentsByPatientId;

  useEffect(() => {
    api.listDemoPatients(token)
      .then((res) => {
        setPatients(res.patients);
      })
      .catch((err) => show("error", `Load patients failed: ${String(err)}`));
  }, [token, show]);

  const selectedSet = useMemo(() => new Set(selectedPatientIds), [selectedPatientIds]);
  const selectedPatients = useMemo(
    () => patients.filter((p) => selectedSet.has(p.patient_id)),
    [patients, selectedSet],
  );
  const allSelected = patients.length > 0 && selectedPatientIds.length === patients.length;

  const fetchPatientDetail = useCallback(async (
    patientId: string,
    options?: { force?: boolean; summary?: boolean; documents?: boolean }
  ) => {
    const force = Boolean(options?.force);
    const wantSummary = options?.summary ?? true;
    const wantDocuments = options?.documents ?? true;
    const shouldFetchSummary = wantSummary && (force || !detailsRef.current[patientId]);
    const shouldFetchDocuments = wantDocuments && (force || documentsRef.current[patientId] === undefined);

    if (!shouldFetchSummary && !shouldFetchDocuments) return;

    const requests: Promise<unknown>[] = [];

    if (shouldFetchSummary) {
      setLoadingSummaryByPatientId((v) => ({ ...v, [patientId]: true }));
      setSummaryErrorByPatientId((v) => {
        const next = { ...v };
        delete next[patientId];
        return next;
      });
      requests.push(
        api.patientSummary(token, patientId)
          .then((summaryRes) => {
            setDetailsByPatientId((v) => ({ ...v, [patientId]: summaryRes }));
          })
          .catch((err) => {
            const message = String(err);
            setSummaryErrorByPatientId((v) => ({ ...v, [patientId]: message }));
            show("error", `Summary load failed for ${patientId}: ${message}`);
          })
          .finally(() => {
            setLoadingSummaryByPatientId((v) => ({ ...v, [patientId]: false }));
          })
      );
    }

    if (shouldFetchDocuments) {
      setLoadingDocumentsByPatientId((v) => ({ ...v, [patientId]: true }));
      setDocumentsErrorByPatientId((v) => {
        const next = { ...v };
        delete next[patientId];
        return next;
      });
      requests.push(
        api.listDocuments(token, patientId)
          .then((docsRes) => {
            setDocumentsByPatientId((v) => ({ ...v, [patientId]: docsRes.documents }));
          })
          .catch((err) => {
            const message = String(err);
            setDocumentsErrorByPatientId((v) => ({ ...v, [patientId]: message }));
            show("error", `Documents load failed for ${patientId}: ${message}`);
          })
          .finally(() => {
            setLoadingDocumentsByPatientId((v) => ({ ...v, [patientId]: false }));
          })
      );
    }

    await Promise.allSettled(requests);
  }, [show, token]);

  const togglePatient = useCallback((patientId: string) => {
    const isSelected = selectedSet.has(patientId);
    if (isSelected) {
      setSelectedPatientIds((ids) => ids.filter((id) => id !== patientId));
      return;
    }
    setSelectedPatientIds((ids) => [...ids, patientId]);
    void fetchPatientDetail(patientId);
  }, [fetchPatientDetail, selectedSet]);

  useEffect(() => {
    selectedPatientIds.forEach((patientId) => {
      const hasSummary = Boolean(detailsRef.current[patientId]);
      const hasDocuments = documentsRef.current[patientId] !== undefined;
      const isLoading = Boolean(loadingSummaryByPatientId[patientId] || loadingDocumentsByPatientId[patientId]);
      if (!hasSummary || !hasDocuments) {
        if (!isLoading) void fetchPatientDetail(patientId);
      }
    });
  }, [fetchPatientDetail, loadingDocumentsByPatientId, loadingSummaryByPatientId, selectedPatientIds]);

  const toggleAll = useCallback(async () => {
    if (allSelected) {
      setSelectedPatientIds([]);
      return;
    }
    const allIds = patients.map((p) => p.patient_id);
    setSelectedPatientIds(allIds);
    await Promise.allSettled(
      allIds
        .filter((id) => !detailsRef.current[id] || documentsRef.current[id] === undefined)
        .map((id) => fetchPatientDetail(id))
    );
  }, [allSelected, fetchPatientDetail, patients]);

  return (
    <div className="col">
      <Card title="Portal Overview">
        <p className="section-intro">This dashboard shows only data your role can access.</p>
      </Card>
      <Card title="Patients">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div className="small">Select patients to show details below.</div>
          <Button variant="secondary" onClick={toggleAll}>{allSelected ? "Hide All" : "Expand All"}</Button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>patient_id</th>
                <th>name</th>
                <th>age</th>
                <th>sex</th>
                <th>mrn</th>
                <th>dob</th>
                <th>details</th>
              </tr>
            </thead>
            <tbody>
              {patients.map((p) => (
                <tr key={p.patient_id}>
                  <td>{p.patient_id}</td>
                  <td>{p.name}</td>
                  <td>{p.age}</td>
                  <td>{p.sex}</td>
                  <td>{p.mrn}</td>
                  <td>{p.dob}</td>
                  <td>
                    <Button
                      variant="secondary"
                      onClick={() => togglePatient(p.patient_id)}
                    >
                      {selectedSet.has(p.patient_id) ? "Hide" : "View"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {selectedPatients.map((p) => {
        const summary = detailsByPatientId[p.patient_id];
        const documents = documentsByPatientId[p.patient_id] ?? [];
        const hasDocuments = documentsByPatientId[p.patient_id] !== undefined;
        const isSummaryLoading = loadingSummaryByPatientId[p.patient_id];
        const isDocumentsLoading = loadingDocumentsByPatientId[p.patient_id];
        const isLoading = isSummaryLoading || isDocumentsLoading;
        const summaryError = summaryErrorByPatientId[p.patient_id];
        const documentsError = documentsErrorByPatientId[p.patient_id];
        const canRetry = Boolean(summaryError || documentsError);
        return (
          <Card key={p.patient_id} title={`${p.patient_id} Clinical Details`}>
            <div style={{ contentVisibility: "auto", containIntrinsicSize: "500px" }}>
              {canRetry ? (
                <div className="row" style={{ justifyContent: "flex-end", marginBottom: 8 }}>
                  <Button
                    variant="secondary"
                    onClick={() => void fetchPatientDetail(p.patient_id, {
                      force: true,
                      summary: Boolean(summaryError),
                      documents: Boolean(documentsError),
                    })}
                  >
                    Retry Failed Requests
                  </Button>
                </div>
              ) : null}
              {!summary && isLoading ? (
                <div className="small">Loading…</div>
              ) : summary ? (
                <>
                  <div className="small">Patient: {summary.patient.name} ({summary.patient.sex}, {summary.patient.age})</div>
                  {summaryError ? <div className="error">Summary load failed: {summaryError}</div> : null}

                  <h3 style={{ marginTop: 10 }}>Medications</h3>
                  <div className="table-wrap"><table><thead><tr><th>name</th><th>dose</th><th>frequency</th><th>route</th><th>indication</th><th>start_date</th><th>status</th></tr></thead><tbody>{summary.medications.map((m) => <tr key={`${m.name}-${m.id}`}><td>{m.name}</td><td>{m.dose ?? "-"}</td><td>{m.frequency ?? "-"}</td><td>{m.route ?? "-"}</td><td>{m.indication ?? "-"}</td><td>{m.start_date ?? "-"}</td><td>{m.status}</td></tr>)}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Allergies</h3>
                  <div className="table-wrap"><table><thead><tr><th>allergen</th><th>reaction</th><th>severity</th><th>verified</th></tr></thead><tbody>{summary.allergies.map((a) => <tr key={`${a.allergen}-${a.id}`}><td>{a.allergen}</td><td>{a.reaction ?? "-"}</td><td>{a.severity ?? "-"}</td><td>{a.verified ? "true" : "false"}</td></tr>)}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Problems</h3>
                  <div className="table-wrap"><table><thead><tr><th>icd_code</th><th>description</th><th>onset_date</th><th>status</th></tr></thead><tbody>{summary.problems.map((pr) => <tr key={`${pr.description}-${pr.id}`}><td>{pr.icd_code ?? "-"}</td><td>{pr.description}</td><td>{pr.onset_date ?? "-"}</td><td>{pr.status}</td></tr>)}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Recent Labs</h3>
                  <div className="table-wrap"><table><thead><tr><th>test_name</th><th>value</th><th>unit</th><th>reference_range</th><th>flag</th><th>collected_date</th><th>notes</th></tr></thead><tbody>{summary.recent_labs.map((l) => <tr key={`${l.test_name}-${l.id}`}><td>{l.test_name}</td><td>{l.value}</td><td>{l.unit ?? "-"}</td><td>{l.reference_range ?? "-"}</td><td>{l.flag ?? "-"}</td><td>{l.collected_date ?? "-"}</td><td>{l.notes ?? "-"}</td></tr>)}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Recent Imaging</h3>
                  <div className="table-wrap"><table><thead><tr><th>report_id</th><th>patient_id</th><th>study_type</th><th>study_date</th><th>body_part</th><th>indication</th><th>technique</th><th>findings</th><th>impression</th><th>critical_findings</th><th>radiologist</th></tr></thead><tbody>{summary.recent_imaging.length ? summary.recent_imaging.map((i) => <tr key={i.report_id}><td>{i.report_id}</td><td>{i.patient_id ?? "-"}</td><td>{i.study_type}</td><td>{i.study_date ?? "-"}</td><td>{i.body_part}</td><td>{i.indication ?? "-"}</td><td>{i.technique ?? "-"}</td><td>{i.findings?.length ? i.findings.map((f) => `${f.location}/${f.finding}/${f.severity ?? "-"}`).join("; ") : "-"}</td><td>{i.impression?.length ? i.impression.join("; ") : "-"}</td><td>{i.critical_findings?.length ? i.critical_findings.join("; ") : "-"}</td><td>{i.radiologist ?? "-"}</td></tr>) : <tr><td colSpan={11}>No recent imaging</td></tr>}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Recent Encounters</h3>
                  <div className="table-wrap"><table><thead><tr><th>encounter_id</th><th>date</th><th>type</th><th>provider</th><th>chief_complaint</th><th>diagnoses</th><th>summary</th></tr></thead><tbody>{summary.recent_encounters.length ? summary.recent_encounters.map((e) => <tr key={e.encounter_id}><td>{e.encounter_id}</td><td>{e.date}</td><td>{e.type}</td><td>{e.provider}</td><td>{e.chief_complaint ?? "-"}</td><td>{e.diagnoses?.length ? e.diagnoses.join("; ") : "-"}</td><td>{e.summary ?? "-"}</td></tr>) : <tr><td colSpan={7}>No recent encounters</td></tr>}</tbody></table></div>

                  <h3 style={{ marginTop: 10 }}>Documents</h3>
                  {documentsError ? <div className="error">Documents load failed: {documentsError}</div> : null}
                  {isDocumentsLoading && !hasDocuments ? (
                    <div className="small">Loading documents…</div>
                  ) : (
                    <div className="table-wrap"><table><thead><tr><th>id</th><th>patient_id</th><th>doc_type</th><th>filename</th><th>mime_type</th><th>description</th><th>uploaded_by</th><th>created_at</th></tr></thead><tbody>{documents.length ? documents.map((d) => <tr key={`${d.id}-${d.filename}`}><td>{d.id ?? "-"}</td><td>{d.patient_id ?? summary.patient.patient_id}</td><td>{d.doc_type}</td><td>{d.filename}</td><td>{d.mime_type ?? "-"}</td><td>{d.description ?? "-"}</td><td>{d.uploaded_by ?? "-"}</td><td>{d.created_at ?? "-"}</td></tr>) : <tr><td colSpan={8}>No documents</td></tr>}</tbody></table></div>
                  )}
                </>
              ) : (
                <>
                  {summaryError ? <div className="error">Summary load failed: {summaryError}</div> : null}
                  {isSummaryLoading ? <div className="small">Loading summary…</div> : null}
                  {documentsError ? <div className="error">Documents load failed: {documentsError}</div> : null}
                  {hasDocuments ? (
                    <>
                      <h3 style={{ marginTop: 10 }}>Documents</h3>
                      <div className="table-wrap"><table><thead><tr><th>id</th><th>patient_id</th><th>doc_type</th><th>filename</th><th>mime_type</th><th>description</th><th>uploaded_by</th><th>created_at</th></tr></thead><tbody>{documents.length ? documents.map((d) => <tr key={`${d.id}-${d.filename}`}><td>{d.id ?? "-"}</td><td>{d.patient_id ?? p.patient_id}</td><td>{d.doc_type}</td><td>{d.filename}</td><td>{d.mime_type ?? "-"}</td><td>{d.description ?? "-"}</td><td>{d.uploaded_by ?? "-"}</td><td>{d.created_at ?? "-"}</td></tr>) : <tr><td colSpan={8}>No documents</td></tr>}</tbody></table></div>
                    </>
                  ) : isDocumentsLoading ? (
                    <div className="small">Loading documents…</div>
                  ) : (!summaryError && !documentsError) ? (
                    <div className="small">No data</div>
                  ) : null}
                </>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

