# Clinical Agents LLM API Scenario Playbook

This guide shows what can happen when integrating with the LLM-related APIs in `clinical-agents`.

It focuses on:
- Real situations
- Minimal request examples
- Simplified response shapes
- Failure handling and next actions

## 1. Prerequisites

- Base URL example: `http://localhost:8080`
- All endpoints in this guide require `Authorization: Bearer <token>` except `/health`.
- Most workflow endpoints require the LLM service to be reachable.
- If the system is booting or models are unavailable, you may get `503`.

Common non-business failures:
- `401 Invalid credentials` or missing/invalid token
- `403` when role is not allowed for endpoint
- `503 System not initialized`
- `503 Medical LLM not available at ...`

---

## 2. Workflow Status Map

Typical progression:
- `active` -> `needs_clarification` -> `ready_for_review` -> `ready_to_send` -> `sent`

Possible alternate branches:
- Emergency branch: `emergency` (human escalation)
- QA branch: `qa_failed` (manual physician review)
- Staff reject branch: `escalated` (manual handling)

Key IDs to track:
- `session_id` for the whole conversation lifecycle
- `ticket_id` after a triage ticket is created

---

## 3. Conversational Workflow Scenarios

### Scenario A: New message creates a review-ready ticket

When it happens:
- Patient message is clear enough and no emergency trigger.

Endpoint:
- `POST /v1/message`

Request:
```bash
curl -X POST http://localhost:8080/v1/message \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "I have dizziness for two days and want advice",
    "patient_id": "P001"
  }'
```

Success response (simplified):
```json
{
  "session_id": "SES-8f12ab34",
  "patient_id": "P001",
  "status": "ready_for_review",
  "ticket_id": "TKT-51aa33ef",
  "next_action": "await_staff_review"
}
```

If it fails:
- `503` LLM unavailable or not initialized.

Next action:
- Staff submits `POST /v1/review`.

### Scenario B: Clarification is required

When it happens:
- Missing critical details after intake/case card generation.

Endpoint:
- `POST /v1/message`

Success response (simplified):
```json
{
  "session_id": "SES-2d0f9a77",
  "status": "needs_clarification",
  "clarification_round": 1,
  "max_rounds": 2,
  "questions": [
    "When did symptoms start?",
    "Any chest pain or shortness of breath?"
  ],
  "next_action": "await_response"
}
```

Next action:
- Client asks user the questions, then calls `POST /v1/clarification`.

### Scenario C: Submit clarification answers

When it happens:
- You previously received `needs_clarification`.

Endpoint:
- `POST /v1/clarification`

Request:
```bash
curl -X POST http://localhost:8080/v1/clarification \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SES-2d0f9a77",
    "responses": {
      "When did symptoms start?": "2 days ago",
      "Any chest pain or shortness of breath?": "No"
    }
  }'
```

Success response (one possible outcome):
```json
{
  "session_id": "SES-2d0f9a77",
  "status": "ready_for_review",
  "ticket_id": "TKT-2aac4df0",
  "next_action": "await_staff_review"
}
```

If it fails:
- `{"error": "Session not found"}` (returned body from orchestrator)

Next action:
- If session missing, start a new `POST /v1/message`.

### Scenario D: Emergency escalation

When it happens:
- Red flags detected (quick screen or route result), e.g. severe chest pain/stroke-like symptoms.

Endpoint:
- `POST /v1/message`

Success response (simplified):
```json
{
  "session_id": "SES-cc8811aa",
  "status": "emergency",
  "ticket_id": "TKT-e0f0112a",
  "red_flags": ["chest_pain"],
  "next_action": "immediate_human_contact"
}
```

Next action:
- Show emergency instructions immediately and route to human/hotline.

### Scenario E: QA fails before normal review

When it happens:
- Ticket created, but QA gate flags response quality/safety issues.

Endpoint:
- `POST /v1/message`

Success response (simplified):
```json
{
  "session_id": "SES-55deaa09",
  "status": "qa_failed",
  "ticket_id": "TKT-7a120f12",
  "issues": ["Missing follow-up safety guidance"],
  "next_action": "manual_review"
}
```

Next action:
- Physician can still override by approving via `POST /v1/review`.

### Scenario F: Staff review rejects

When it happens:
- Physician/admin decides draft should not proceed.

Endpoint:
- `POST /v1/review`

Request:
```bash
curl -X POST http://localhost:8080/v1/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SES-8f12ab34",
    "approved": false,
    "physician_notes": "Escalate to phone follow-up today"
  }'
```

Success response (simplified):
```json
{
  "session_id": "SES-8f12ab34",
  "status": "escalated",
  "ticket_id": "TKT-51aa33ef",
  "next_action": "manual_handling"
}
```

### Scenario G: Staff review approves and prepares sending

When it happens:
- Physician/admin approves and QA passes for drafted reply.

Endpoint:
- `POST /v1/review`

Request:
```bash
curl -X POST http://localhost:8080/v1/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SES-8f12ab34",
    "approved": true,
    "physician_notes": "Keep language simple",
    "key_points": ["Hydration", "Return if fever worsens"]
  }'
```

Success response (simplified):
```json
{
  "session_id": "SES-8f12ab34",
  "status": "ready_to_send",
  "ticket_id": "TKT-51aa33ef",
  "next_action": "send_to_patient"
}
```

If QA still fails during review:
- `status: "needs_revision"`, `next_action: "revise_reply"`

### Scenario H: Send approved reply

When it happens:
- Ticket has an approved draft reply.

Endpoint:
- `POST /v1/send`

Request:
```bash
curl -X POST http://localhost:8080/v1/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SES-8f12ab34"}'
```

Success response (simplified):
```json
{
  "session_id": "SES-8f12ab34",
  "status": "sent",
  "ticket_id": "TKT-51aa33ef",
  "message": "Reply sent to patient"
}
```

If it fails:
- `{"error": "No approved reply to send"}`

### Scenario I: Inspect one session

Endpoint:
- `GET /v1/session/{session_id}`

Request:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/v1/session/SES-8f12ab34
```

Success response (simplified):
```json
{
  "session_id": "SES-8f12ab34",
  "patient_id": "P001",
  "status": "completed",
  "clarification_count": 1,
  "has_ticket": true,
  "ticket_status": "sent"
}
```

If it fails:
- `404 Session not found`

### Scenario J: List sessions

Endpoint:
- `GET /v1/sessions`

Success response (simplified):
```json
{
  "total": 2,
  "sessions": [
    {"session_id": "SES-1", "status": "active"},
    {"session_id": "SES-2", "status": "completed"}
  ]
}
```

---

## 4. LLM Analysis Scenarios

### Scenario K: Analyze a lab report

Endpoint:
- `POST /v1/lab-report/{report_id}/analyze`

Request:
```bash
curl -X POST http://localhost:8080/v1/lab-report/LAB001/analyze \
  -H "Authorization: Bearer $TOKEN"
```

Success response (simplified):
```json
{
  "report_id": "LAB001",
  "analysis": {
    "summary": "Abnormal potassium requires prompt follow-up",
    "risk_level": "high"
  }
}
```

If it fails:
- `404 Lab report not found`
- `503` LLM unavailable

### Scenario L: Analyze an imaging report

Endpoint:
- `POST /v1/patient/{patient_id}/imaging/{index}/analyze`

Request:
```bash
curl -X POST http://localhost:8080/v1/patient/P001/imaging/0/analyze \
  -H "Authorization: Bearer $TOKEN"
```

Success response (simplified):
```json
{
  "report_id": "IMG-3f0e2a1b",
  "analysis": {
    "summary": "No acute intracranial hemorrhage",
    "recommendation": "Routine follow-up"
  }
}
```

If it fails:
- `404 Imaging report not found`
- `503` LLM unavailable

---

## 5. Knowledge Search Scenarios

### Scenario M: Search clinical knowledge (POST)

Endpoint:
- `POST /v1/knowledge/search`

Request:
```bash
curl -X POST http://localhost:8080/v1/knowledge/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"diabetes medication", "top_k":3}'
```

Success response (simplified):
```json
{
  "query": "diabetes medication",
  "results": [
    {"source": "diabetes_guidelines_2024.pdf", "source_type": "sop"}
  ]
}
```

### Scenario N: Search clinical knowledge (GET)

Endpoint:
- `GET /v1/knowledge/search?query=...&top_k=...`

No-result response:
```json
{
  "query": "very uncommon query",
  "results": []
}
```

### Scenario O: List demo knowledge chunks

Endpoint:
- `GET /v1/demo/knowledge`

Success response (simplified):
```json
{
  "chunks": [
    {"source": "chest_pain_protocol_v3.pdf", "source_type": "sop"}
  ]
}
```

---

## 6. RAG API Scenarios (`/v1/rag/*`)

### Scenario P: Check RAG health

Endpoint:
- `GET /v1/rag/health`

Success response (simplified):
```json
{
  "status": "healthy",
  "embedding_service": {"connected": true},
  "documents": 12
}
```

If degraded:
- `status: "degraded"` and embedding connection false.

### Scenario Q: Ingest plain text into RAG

Endpoint:
- `POST /v1/rag/ingest/text`

Request:
```bash
curl -X POST http://localhost:8080/v1/rag/ingest/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Chest pain protocol text...",
    "source":"chest_pain_protocol.txt",
    "source_type":"protocol",
    "department":"ER"
  }'
```

Success response:
```json
{"status":"success","doc_id":"DOC-abc123"}
```

If embedding unavailable:
- `503 Embedding service not available at ...`

### Scenario R: Ingest one file into RAG

Endpoint:
- `POST /v1/rag/ingest/file` (multipart)

Form fields:
- `file`
- `source_type` (required)
- `title` (optional)
- `department` (optional)
- `tags` (comma-separated optional)
- `process_images` (optional, default true)

Success response (simplified):
```json
{
  "status": "success",
  "doc_id": "DOC-19f0",
  "doc_type": "pdf"
}
```

### Scenario S: Ingest batch files

Endpoint:
- `POST /v1/rag/ingest/batch`

Success response (simplified):
```json
{
  "total": 3,
  "success": 2,
  "failed": 1,
  "results": [
    {"filename":"a.pdf","status":"success","doc_id":"DOC-1"},
    {"filename":"b.pdf","status":"error","error":"..."}
  ]
}
```

### Scenario T: Search RAG documents

Endpoints:
- `POST /v1/rag/search`
- `GET /v1/rag/search`

POST request example:
```bash
curl -X POST http://localhost:8080/v1/rag/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"critical potassium threshold",
    "top_k":5,
    "search_type":"hybrid",
    "filter_source_type":"protocol",
    "rerank":true
  }'
```

Success response (simplified):
```json
{
  "query": "critical potassium threshold",
  "total_results": 3,
  "search_type": "hybrid",
  "reranked": true,
  "results": [
    {"chunk_id":"CHUNK-1","score":0.87,"is_image":false}
  ]
}
```

### Scenario U: List and inspect RAG documents

Endpoints:
- `GET /v1/rag/documents`
- `GET /v1/rag/documents/{doc_id}`

List response (simplified):
```json
{
  "total": 2,
  "documents": [
    {"doc_id":"DOC-1","source":"critical_value_protocol.pdf","source_type":"protocol"}
  ]
}
```

Get-one response (simplified):
```json
{
  "doc_id": "DOC-1",
  "title": "Critical Value SOP",
  "content_length": 8200,
  "metadata": {"department": "Lab"}
}
```

If not found:
- `404 Document not found`

### Scenario V: Delete RAG document

Endpoint:
- `DELETE /v1/rag/documents/{doc_id}`

Success:
```json
{"status":"deleted","doc_id":"DOC-1"}
```

If not found:
- `404 Document not found`

### Scenario W: View RAG stats

Endpoint:
- `GET /v1/rag/stats`

Response shape:
```json
{
  "documents": 10,
  "chunks": 152,
  "collections": ["clinical_docs"]
}
```

### Scenario X: Seed demo RAG data

Endpoint:
- `POST /v1/rag/seed`

Success response (simplified):
```json
{
  "message": "Demo data seeded",
  "total": 5,
  "success": 5
}
```

---

## 7. Health and Availability Scenarios

### Scenario Y: Global health check

Endpoint:
- `GET /health`

Healthy response:
```json
{
  "status": "healthy",
  "llm_servers": {
    "medical": {"connected": true},
    "router": {"connected": true},
    "embedding": {"connected": true}
  }
}
```

Degraded response:
- `status` becomes `degraded`
- One or more `connected` flags are `false`

---

## 8. Client UX Guidance (No raw JSON dump)

For better end-user experience, map backend responses to UI states:

- `needs_clarification`:
  - Show each question as a normal form prompt.
  - Keep `session_id` hidden but stored in app state.

- `ready_for_review` / `ready_to_send`:
  - Show a human-readable summary and action buttons.
  - Do not display entire `ticket` JSON to users.

- `emergency`:
  - Show urgent call-to-action banner and immediate contact steps.
  - Suppress technical details unless user is staff.

- error responses:
  - Replace technical error strings with friendly messages.
  - Keep full error in logs only.

Suggested UX message mapping:
- `Session not found` -> "Your session expired. Please resend your message."
- `No approved reply to send` -> "This reply still needs staff approval."
- `Medical LLM not available...` -> "Service is temporarily busy. Please try again shortly."

---

## 9. Integration Checklist

- Always persist `session_id` from first workflow response.
- Keep a status-driven UI (not payload-dump UI).
- Handle `503` with retry/backoff.
- Handle `404` as user/data issue (not retry storm).
- Audit and monitor transitions: `needs_clarification`, `ready_for_review`, `ready_to_send`, `sent`, `emergency`, `qa_failed`.
