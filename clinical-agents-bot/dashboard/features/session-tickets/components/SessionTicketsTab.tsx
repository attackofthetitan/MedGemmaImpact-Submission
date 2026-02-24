"use client";

import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ReviewResponse, SendLineResponse, SessionAuditLogEntry, SessionDetailResponse, SessionListItem } from "@/lib/types";
import { Button, Card, Input, TextArea } from "@/components/ui/primitives";
import { OptLabel } from "@/components/dashboard/common/FormLabels";
import { splitLines } from "@/components/dashboard/common/textParsers";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";
import { formatDateTime, formatDateTimeWithRaw, renderDetails, renderTextList, statusClass } from "@/features/session-tickets/utils/formatting";

export function SessionTicketsTab() {
  const { token, show } = useDashboardContext();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<SessionDetailResponse | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const selectedIdRef = useRef(selectedId);

  selectedIdRef.current = selectedId;

  const loadSessions = useCallback(async () => {
    setLoadingList(true);
    setError("");
    try {
      const res = await api.listSessions(token);
      setSessions(res.sessions);
      if (!selectedIdRef.current && res.sessions.length) setSelectedId(res.sessions[0].session_id);
    } catch (e) {
      const msg = String(e);
      setError(msg);
      show("error", msg);
    } finally {
      setLoadingList(false);
    }
  }, [show, token]);

  const loadDetail = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    setLoadingDetail(true);
    setError("");
    try {
      const res = await api.getSession(token, sessionId);
      setSelected(res);
    } catch (e) {
      const msg = String(e);
      setError(msg);
      show("error", msg);
    } finally {
      setLoadingDetail(false);
    }
  }, [show, token]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    void loadDetail(selectedId);
  }, [loadDetail, selectedId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.session_id.toLowerCase().includes(q) || (s.patient_id ?? "").toLowerCase().includes(q) || s.status.toLowerCase().includes(q));
  }, [query, sessions]);

  const ticket = selected?.ticket ?? null;

  return (
    <div className="col session-section">
      <Card title="Session & Ticket Browser">
        <p className="section-intro">Review sessions, then expand details for ticket and audit context.</p>
        <div className="session-toolbar">
          <div style={{ flex: 1, minWidth: 220 }}>
            <OptLabel text="Search sessions" htmlFor="session-search" />
            <Input id="session-search" name="session_search" placeholder="Search by Session ID, Patient ID, or status..." value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="session-toolbar-actions">
            <Button variant="secondary" onClick={() => void loadSessions()}>Refresh</Button>
          </div>
        </div>
        {error ? <div className="state-error" style={{ marginTop: 10 }}>{error}</div> : null}
      </Card>

      <Card title="Sessions">
        <div className="session-table-card">
          {loadingList ? <div className="state-loading">Loading sessions…</div> : null}
          {!loadingList && !filtered.length ? <div className="state-empty">No sessions found.</div> : null}
          {filtered.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Session ID</th><th>Patient ID</th><th>Status</th><th>Created</th><th>Open</th></tr>
                </thead>
                <tbody>
                  {filtered.map((s) => (
                    <tr key={s.session_id} className={selectedId === s.session_id ? "session-row-selected" : "session-row-hover"}>
                      <td>{s.session_id}</td>
                      <td>{s.patient_id ?? "-"}</td>
                      <td><span className={`badge-status ${statusClass(s.status)}`}>{s.status}</span></td>
                      <td>{formatDateTime(s.created_at)}</td>
                      <td><Button variant="secondary" onClick={() => setSelectedId(s.session_id)}>{selectedId === s.session_id ? "Opened" : "Open"}</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </Card>

      {!selectedId ? <SessionDetailEmpty /> : null}
      {selectedId && loadingDetail ? <SessionDetailLoading /> : null}
      {selectedId && selected ? <SessionDetailReady selected={selected} ticket={ticket} onReload={() => void loadDetail(selectedId)} /> : null}
    </div>
  );
}

function SessionDetailEmpty() {
  return <Card title="Session Detail"><div className="state-empty">Select a session to view details.</div></Card>;
}

function SessionDetailLoading() {
  return <Card title="Session Detail"><div className="state-loading">Loading detail…</div></Card>;
}

function SessionAccordionItem({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="accordion-item" open={defaultOpen}>
      <summary className="accordion-summary">{title}</summary>
      <div className="accordion-content">{children}</div>
    </details>
  );
}

function SessionDetailReady({
  selected,
  ticket,
  onReload,
}: {
  selected: SessionDetailResponse;
  ticket: SessionDetailResponse["ticket"];
  onReload: () => void;
}) {
  const { token, user, show } = useDashboardContext();
  const canManualReview = user.role === "admin" || user.role === "physician";
  const ticketRedFlags = renderTextList(ticket?.red_flags ?? []);
  const caseCardPositives = renderTextList(ticket?.case_card?.pertinent_positives ?? []);
  const caseCardNegatives = renderTextList(ticket?.case_card?.pertinent_negatives ?? []);
  const caseCardGaps = renderTextList(ticket?.case_card?.information_gaps ?? []);
  const draftActionItems = renderTextList(ticket?.draft_reply?.action_items ?? []);
  const draftWarningSigns = renderTextList(ticket?.draft_reply?.warning_signs ?? []);
  const [reviewDecision, setReviewDecision] = useState<"approve" | "reject">("approve");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewKeyPoints, setReviewKeyPoints] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewResult, setReviewResult] = useState<ReviewResponse | null>(null);
  const [sendSubmitting, setSendSubmitting] = useState(false);
  const [sendResult, setSendResult] = useState<SendLineResponse | null>(null);
  const [sendError, setSendError] = useState("");
  const [sentInView, setSentInView] = useState(false);
  useEffect(() => {
    setSendResult(null);
    setSendError("");
    setSentInView(false);
  }, [selected.session_id]);
  const lastQaValidation = useMemo(() => {
    for (let i = selected.audit_log.length - 1; i >= 0; i -= 1) {
      const entry = selected.audit_log[i];
      if (entry.action === "qa_validation") return entry;
    }
    return null;
  }, [selected.audit_log]);
  const lastReplyQa = useMemo(() => {
    for (let i = selected.audit_log.length - 1; i >= 0; i -= 1) {
      const entry = selected.audit_log[i];
      if (entry.action === "reply_qa") return entry;
    }
    return null;
  }, [selected.audit_log]);
  const reviewContext = useMemo((): "qa_failed" | "needs_revision" | "escalated" | "normal" => {
    if (selected.status === "escalated" || ticket?.status === "escalated") return "escalated";
    if (ticket?.status === "in_review") {
      if (lastQaValidation?.details?.passed === false) return "qa_failed";
      if (lastReplyQa?.details?.passed === false) return "needs_revision";
    }
    return "normal";
  }, [lastQaValidation?.details?.passed, lastReplyQa?.details?.passed, selected.status, ticket?.status]);
  const notesRequired = reviewDecision === "approve" && (reviewContext === "qa_failed" || reviewContext === "needs_revision" || reviewContext === "escalated");
  const canSubmitReview = Boolean(selected.session_id) && !reviewSubmitting && (!notesRequired || reviewNotes.trim().length > 0);
  const approveLabel = reviewContext === "qa_failed"
    ? "Override QA & Regenerate Draft"
    : reviewContext === "needs_revision"
      ? "Resubmit Revision"
      : reviewContext === "escalated"
        ? "Re-enter Pipeline"
        : "Submit Review";
  const contextHint = reviewContext === "qa_failed"
    ? "Backend QA failed. Approve to override and regenerate draft."
    : reviewContext === "needs_revision"
      ? "Draft needs revision. Approve with notes/key points to regenerate."
      : reviewContext === "escalated"
        ? "Case escalated. Approve to re-enter review pipeline."
        : "Submit manual review based on clinical judgement.";
  const sendRoleAllowed = canManualReview;
  const sessionStatus = selected.status.toLowerCase();
  const ticketStatus = (ticket?.status ?? selected.ticket_status ?? "").toLowerCase();
  const reviewStatus = (reviewResult?.status ?? "").toLowerCase();
  const sendEligible = reviewStatus === "ready_to_send"
    || ticketStatus === "ready_to_send"
    || ticketStatus === "approved"
    || sessionStatus === "ready_to_send";
  const missingPatientId = !selected.patient_id;
  const canSendToLine = sendRoleAllowed && sendEligible && !missingPatientId && !sendSubmitting && !sentInView;

  const submitReview = useCallback(async () => {
    if (!canManualReview) return;
    if (!selected.session_id) return;
    setReviewSubmitting(true);
    try {
      const res = await api.reviewSession(token, {
        session_id: selected.session_id,
        approved: reviewDecision === "approve",
        physician_notes: reviewNotes.trim() || null,
        key_points: reviewDecision === "approve" ? splitLines(reviewKeyPoints) : null,
      });
      setReviewResult(res);
      onReload();
      show("success", `Review submitted: ${res.status}`);
    } catch (e) {
      show("error", String(e));
    } finally {
      setReviewSubmitting(false);
    }
  }, [canManualReview, onReload, reviewDecision, reviewKeyPoints, reviewNotes, selected.session_id, show, token]);

  const submitSendToLine = useCallback(async () => {
    if (!canSendToLine || !selected.patient_id) return;
    setSendSubmitting(true);
    setSendError("");
    try {
      const res = await api.sendToLine(token, {
        session_id: selected.session_id,
        patient_id: selected.patient_id,
      });
      setSendResult(res);
      setSentInView(true);
      onReload();
      show("success", "Message sent to LINE.");
    } catch (e) {
      if (e instanceof ApiError && e.statusCode === 404) {
        setSendError("LINE send API is not available in this environment.");
      } else if (e instanceof ApiError) {
        setSendError(e.message || "Failed to send message to LINE.");
      } else {
        setSendError(String(e));
      }
      show("error", "Failed to send message to LINE.");
    } finally {
      setSendSubmitting(false);
    }
  }, [canSendToLine, onReload, selected.patient_id, selected.session_id, show, token]);

  return (
    <>
      <Card title="Session Summary">
        <div className="summary-grid">
          <div className="summary-item"><span className="summary-label">Session ID</span><span className="summary-value">{selected.session_id}</span></div>
          <div className="summary-item"><span className="summary-label">Patient ID</span><span className="summary-value">{selected.patient_id ?? "-"}</span></div>
          <div className="summary-item"><span className="summary-label">Status</span><span className="summary-value"><span className={`badge-status ${statusClass(selected.status)}`}>{selected.status}</span></span></div>
          <div className="summary-item"><span className="summary-label">Created</span><span className="summary-value">{formatDateTimeWithRaw(selected.created_at)}</span></div>
          <div className="summary-item"><span className="summary-label">Clarification Count</span><span className="summary-value">{selected.clarification_count}</span></div>
          <div className="summary-item"><span className="summary-label">Ticket Status</span><span className="summary-value">{selected.ticket_status ?? "-"}</span></div>
          <div className="summary-item"><span className="summary-label">Has Ticket</span><span className="summary-value">{selected.has_ticket ? "yes" : "no"}</span></div>
        </div>
      </Card>

      <Card title="Session Detail">
        <div className="accordion">
          <SessionAccordionItem title="Ticket" defaultOpen>
            {!ticket ? <div className="state-empty">This session has no ticket yet.</div> : (
              <div className="detail-grid">
                <div className="detail-row"><strong>Ticket ID:</strong> {ticket.ticket_id}</div>
                <div className="detail-row"><strong>Status:</strong> {ticket.status ?? "-"}</div>
                <div className="detail-row"><strong>Intent:</strong> {ticket.intent ?? "-"}</div>
                <div className="detail-row"><strong>Risk Level:</strong> {ticket.risk_level ?? "-"}</div>
                <div className="detail-row"><strong>Red Flags:</strong> {ticketRedFlags}</div>
                <div className="detail-row"><strong>Destination:</strong> {ticket.destination ?? "-"}</div>
                <div className="detail-row"><strong>Urgency:</strong> {ticket.urgency ?? "-"}</div>
                <div className="detail-row"><strong>Created At:</strong> {formatDateTimeWithRaw(ticket.created_at)}</div>
                <div className="detail-row"><strong>Reviewed By:</strong> {ticket.reviewed_by ?? "-"}</div>
                <div className="detail-row"><strong>Reviewed At:</strong> {formatDateTimeWithRaw(ticket.reviewed_at)}</div>
                <div className="detail-row"><strong>Physician Notes:</strong> {ticket.physician_notes ?? "-"}</div>
              </div>
            )}
          </SessionAccordionItem>

          <SessionAccordionItem title="Case Card">
            {ticket?.case_card ? (
              <div className="detail-grid">
                <div className="detail-row"><strong>Case ID:</strong> {ticket.case_card.case_id ?? "-"}</div>
                <div className="detail-row"><strong>Context ID:</strong> {ticket.case_card.context_id ?? "-"}</div>
                <div className="detail-row"><strong>Patient ID:</strong> {ticket.case_card.patient_id ?? "-"}</div>
                <div className="detail-row"><strong>Timestamp:</strong> {formatDateTimeWithRaw(ticket.case_card.timestamp)}</div>
                <div className="detail-row"><strong>Chief Complaint:</strong> {ticket.case_card.chief_complaint ?? "-"}</div>
                <div className="detail-row"><strong>Summary:</strong> {ticket.case_card.summary ?? "-"}</div>
                <div className="detail-row"><strong>Relevant History:</strong> {ticket.case_card.relevant_history ?? "-"}</div>
                <div className="detail-row"><strong>Current Medications Summary:</strong> {ticket.case_card.current_meds_summary ?? "-"}</div>
                <div className="detail-row"><strong>Recent Labs Summary:</strong> {ticket.case_card.recent_labs_summary ?? "-"}</div>
                <div className="detail-row"><strong>Recent Imaging Summary:</strong> {ticket.case_card.recent_imaging_summary ?? "-"}</div>
                <div className="detail-row"><strong>Pertinent Positives:</strong> {caseCardPositives}</div>
                <div className="detail-row"><strong>Pertinent Negatives:</strong> {caseCardNegatives}</div>
                <div className="detail-row"><strong>Information Gaps:</strong> {caseCardGaps}</div>
                <div className="detail-row"><strong>Triage Destination:</strong> {ticket.case_card.triage?.destination ?? "-"}</div>
                <div className="detail-row"><strong>Triage Urgency:</strong> {ticket.case_card.triage?.urgency ?? "-"}</div>
                <div className="detail-row"><strong>Triage Reasoning:</strong> {ticket.case_card.triage?.reasoning ?? "-"}</div>
                <div className="detail-row"><strong>Triage Confidence:</strong> {ticket.case_card.triage?.confidence ?? "-"}</div>
              </div>
            ) : <div className="state-empty">No case card available.</div>}
          </SessionAccordionItem>

          <SessionAccordionItem title="Draft Reply">
            {ticket?.draft_reply ? (
              <div className="detail-grid">
                <div className="detail-row"><strong>Draft ID:</strong> {ticket.draft_reply.draft_id ?? "-"}</div>
                <div className="detail-row"><strong>Locale:</strong> {ticket.draft_reply.locale ?? "-"}</div>
                <div className="detail-row"><strong>Greeting:</strong> {ticket.draft_reply.greeting ?? "-"}</div>
                <div className="detail-row"><strong>Acknowledgment:</strong> {ticket.draft_reply.acknowledgment ?? "-"}</div>
                <div className="detail-row"><strong>Understanding:</strong> {ticket.draft_reply.understanding ?? "-"}</div>
                <div className="detail-row"><strong>Response:</strong> {ticket.draft_reply.response ?? "-"}</div>
                <div className="detail-row"><strong>Action Items:</strong> {draftActionItems}</div>
                <div className="detail-row"><strong>Warning Signs:</strong> {draftWarningSigns}</div>
                <div className="detail-row"><strong>Follow Up:</strong> {ticket.draft_reply.follow_up ?? "-"}</div>
                <div className="detail-row"><strong>Closing:</strong> {ticket.draft_reply.closing ?? "-"}</div>
                <div className="detail-row"><strong>Emergency Info:</strong> {ticket.draft_reply.emergency_info ?? "-"}</div>
              </div>
            ) : <div className="state-empty">No draft reply available.</div>}
          </SessionAccordionItem>

          <SessionAccordionItem title="Audit Timeline">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Timestamp</th><th>Action</th><th>Details</th></tr></thead>
                <tbody>
                  {selected.audit_log.length ? selected.audit_log.map((entry: SessionAuditLogEntry, idx: number) => (
                    <tr key={`${entry.timestamp}-${entry.action}-${idx}`}>
                      <td>{formatDateTimeWithRaw(entry.timestamp)}</td>
                      <td>{entry.action}</td>
                      <td>{renderDetails(entry.details)}</td>
                    </tr>
                  )) : <tr><td colSpan={3}>No audit entries</td></tr>}
                </tbody>
              </table>
            </div>
          </SessionAccordionItem>
        </div>
      </Card>

      <Card title="Manual Review">
        {!canManualReview ? (
          <div className="state-empty">Only admin/physician can submit manual review.</div>
        ) : (
          <div className="col">
            <div className="info-box">{contextHint}</div>
            <div className="row">
              <label className="small">
                <input
                  type="radio"
                  name="review-decision"
                  checked={reviewDecision === "approve"}
                  onChange={() => setReviewDecision("approve")}
                />{" "}
                Approve
              </label>
              <label className="small">
                <input
                  type="radio"
                  name="review-decision"
                  checked={reviewDecision === "reject"}
                  onChange={() => setReviewDecision("reject")}
                />{" "}
                Reject (Escalate)
              </label>
            </div>
            <OptLabel text="Physician Notes" htmlFor="manual-review-notes" />
            <TextArea id="manual-review-notes" value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} />
            {notesRequired ? <div className="small">Physician notes are required in current override/resubmit context.</div> : null}
            <OptLabel text="Key Points (one per line, approve only)" htmlFor="manual-review-keypoints" />
            <TextArea id="manual-review-keypoints" value={reviewKeyPoints} onChange={(e) => setReviewKeyPoints(e.target.value)} disabled={reviewDecision !== "approve"} />
            <div className="row">
              <Button onClick={() => void submitReview()} disabled={!canSubmitReview}>
                {reviewSubmitting ? "Submitting..." : reviewDecision === "approve" ? approveLabel : "Reject (Escalate)"}
              </Button>
            </div>
            {reviewResult ? (
              <div className="info-box">
                Status: {reviewResult.status}
                {"\n"}Next Action: {reviewResult.next_action ?? "-"}
                {"\n"}Hint: {reviewResult.hint ?? "-"}
                {"\n"}Notes: {reviewResult.physician_notes ?? "-"}
                {"\n"}QA Passed: {typeof reviewResult.qa_result === "object" && reviewResult.qa_result && "passed" in reviewResult.qa_result ? String((reviewResult.qa_result as Record<string, unknown>).passed) : "-"}
              </div>
            ) : null}
            <div className="row">
              <Button onClick={() => void submitSendToLine()} disabled={!canSendToLine}>
                {sendSubmitting ? "Sending..." : "Send to LINE"}
              </Button>
            </div>
            {missingPatientId ? <div className="small">Patient ID is required by backend send API.</div> : null}
            {!sendEligible ? <div className="small">Send becomes available when review state is ready to send.</div> : null}
            {sendError ? <div className="state-error">{sendError}</div> : null}
            {sendResult ? (
              <div className="success">
                Sent successfully.
                {"\n"}Status: {sendResult.status ?? "sent"}
                {"\n"}Message: {sendResult.message ?? "success"}
                {"\n"}Session: {sendResult.session_id ?? selected.session_id}
              </div>
            ) : null}
          </div>
        )}
      </Card>
    </>
  );
}
