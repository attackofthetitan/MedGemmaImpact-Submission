# Clinical Agent System

An LLM-powered clinical communication workflow that processes patient messages through a multi-stage pipeline including intent routing, EHR retrieval via tool calling, clinical case card generation, staff review, and patient-facing reply drafting. All inference is served locally via vLLM with no external API dependencies.

---

## Architecture

```
                          ┌─────────────┐
                          │   Client    │
                          │  (+ JWT)    │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │  FastAPI    │
                          │  server.py  │
                          └──────┬──────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
       │   auth.py   │   │ orchestrator│   │  ehr_db.py  │
       │  JWT/RBAC   │   │   .py       │   │  SQLite     │
       └─────────────┘   └──────┬──────┘   └──────┬──────┘
                                │                 │
              ┌─────────────────┼──────────┐      │
              │                 │          │      │
       ┌──────▼──────┐  ┌──────▼───┐ ┌────▼───┐   │
       │   Agents    │  │ RAG      │ │ demo   │   │
       │  (tool use) │  │ pipeline │ │ _data  │   │
       └──────┬──────┘  └──────┬───┘ └────────┘   │
              │                │                  │
              │     ┌──────────┤                  │
              │     │          │                  │
       ┌──────▼──┐ ┌▼────────┐ │                  │
       │ Router  │ │ChromaDB │ │                  │
       │ Gemma 3 │ └─────────┘ │                  │
       │ :8001   │             │                  │
       └─────────┘      ┌──────▼────┐       ┌─────▼─────┐
                        │ Embedgemma│       │ SQLite DB │
                        │ :8003     │       │clinical.db│
                        └───────────┘       └───────────┘
                               │
                        ┌──────▼──────┐
                        │  MedGemma   │
                        │   :8002     │
                        └─────────────┘
```

### LLM tool calling flow

When the LLM processes a patient message, it can issue tool calls to retrieve structured data before producing its final output:

```
LLM (MedGemma) generates tool_calls in response
  │
  ├─► get_patient_ehr(patient_id, section)  →  SQLite DB  →  returns JSON
  │     sections: summary, problems, medications, allergies,
  │               labs, imaging, encounters
  │
  └─► search_knowledge(query)  →  knowledge base search  →  returns SOP/protocol text
```

The orchestrator executes each tool call, feeds the result back into the LLM context, and repeats until the LLM produces a final response with no further tool calls (up to a configurable maximum of three rounds).

---

## Models

| Model | Port | Purpose |
|-------|------|---------|
| Gemma 3 (router) | 8001 | Intent classification, risk scoring, structured JSON output |
| MedGemma 4B | 8002 | Clinical reasoning, case card generation, reply drafting, lab/imaging analysis |
| Embedgemma (embedding) | 8003 | Semantic embeddings for RAG (optional) |

---

## Quick Start

### 1. Start vLLM servers

```bash
export ROUTER_MODEL_PATH=./routergemma
export MEDICAL_MODEL_PATH=./medgemma-fp8
export EMBEDDING_MODEL_PATH=./embedgemma   # optional, required only for RAG

chmod +x scripts/start_vllm.sh
./scripts/start_vllm.sh
```

This starts three vLLM processes: the router on port 8001, MedGemma on port 8002, and the embedding model on port 8003.

### 2. Start the API server

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```

On first startup the server will:
- Create `clinical.db` with all tables.
- Seed demo patient records from `mock_data/*.json`.
- Create a default administrator account (`admin` / `admin123`).

### 3. Authenticate and test

```bash
# Obtain a JWT token
TOKEN=$(curl -s -X POST http://localhost:8080/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List demo patients
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/v1/demo/patients

# Process a patient message
curl -X POST http://localhost:8080/v1/message \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "我最近頭很痛", "patient_id": "P001"}'
```

### 4. Run tests

```bash
# Full LLM pipeline integration test (requires vLLM servers running)
python test_workflow.py

# RAG pipeline test (requires embedding model)
python test_rag.py

# Unit tests (no servers required)
pytest tests/unit_test.py -v
```

---

## Clinical Workflow

A patient message passes through the following stages in sequence:

```
Patient Message
      │
      ▼
┌─────────────┐
│   Router    │──── Red-flag keywords detected? ──► Emergency response (119)
│  (Gemma 3)  │     (胸痛, 喘不過氣, 中風, etc.)
│  structured │
│   output    │──── LLM classifies intent and risk level
└─────┬───────┘     (lab_results, medication, symptoms, follow_up, ...)
      │
      ▼
┌─────────────┐
│   Intake    │──── LLM extracts chief complaint, symptoms, and missing information
│  (MedGemma) │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│   Context   │──── Retrieves EHR data from SQLite and relevant SOPs via RAG
│   Builder   │
└─────┬───────┘
      │
      ▼
┌─────────────┐     ┌──────────────────────────────────┐
│ Case Card   │────►│ LLM calls tools:                 │
│ (MedGemma   │     │  get_patient_ehr(P001, "labs")    │
│  + tools)   │◄────│  get_patient_ehr(P001, "meds")    │
└─────┬───────┘     │  search_knowledge("糖尿病用藥")   │
      │             └──────────────────────────────────┘
      ▼
┌─────────────┐
│  QA Gate    │──── Validates: no diagnostic statements, safety warnings present
└─────┬───────┘
      │
      ▼
┌─────────────┐
│   Ticket    │──► Staff review (approve / reject)
└─────┬───────┘
      │
      ▼
┌─────────────┐     ┌──────────────────────────────────┐
│   Explain   │────►│ LLM calls tools for context,     │
│ (MedGemma   │     │ drafts patient-facing reply       │
│  + tools)   │◄────│ in Traditional Chinese (繁體中文)  │
└─────┬───────┘     └──────────────────────────────────┘
      │
      ▼
┌─────────────┐
│  QA Gate    │──── Final safety check
└─────┬───────┘
      │
      ▼
   Send Reply
```

---

## Authentication

All endpoints except `/health` and `POST /v1/auth/login` require a JWT bearer token.

```bash
# Login
curl -X POST http://localhost:8080/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Response
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": { "username": "admin", "role": "admin" }
}
```

Include the token in all subsequent requests:

```
Authorization: Bearer eyJ...
```

### Roles and permissions

| Permission | admin | physician | nurse | staff |
|------------|-------|-----------|-------|-------|
| Read EHR | Yes | Yes | Yes | Yes |
| Write medications / problems | Yes | Yes | No | No |
| Write allergies / labs / encounters | Yes | Yes | Yes | No |
| Manage users | Yes | No | No | No |
| View audit log | Yes | Yes | No | No |

---

## API Reference

### Authentication

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/auth/login` | POST | None | Obtain JWT token |
| `/v1/auth/register` | POST | admin | Create a new user account |
| `/v1/auth/me` | GET | Any | Return the authenticated user's details |
| `/v1/auth/users` | GET | admin | List all user accounts |

### Clinical Workflow

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/message` | POST | Any | Submit a patient message and run the full LLM pipeline |
| `/v1/clarification` | POST | Any | Submit answers to clarifying questions |
| `/v1/review` | POST | Any | Approve or reject a staff review ticket |
| `/v1/send` | POST | Any | Send an approved reply to the patient |
| `/v1/session/{id}` | GET | Any | Retrieve session details and audit trail |
| `/v1/sessions` | GET | Any | List all sessions |

### Patient EHR

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/patient` | POST | admin, physician | Create a patient record |
| `/v1/patient/{id}` | GET | Any | Return the full patient summary |
| `/v1/patient/{id}` | PATCH | admin, physician | Update patient demographics |
| `/v1/patient/{id}/medications` | GET | Any | List medications |
| `/v1/patient/{id}/medications` | POST | admin, physician | Add a medication |
| `/v1/patient/{id}/medications/{mid}` | PATCH | admin, physician | Update a medication |
| `/v1/patient/{id}/allergies` | GET | Any | List allergies |
| `/v1/patient/{id}/allergies` | POST | admin, physician, nurse | Add an allergy |
| `/v1/patient/{id}/problems` | GET | Any | List active problems |
| `/v1/patient/{id}/problems` | POST | admin, physician | Add a problem |
| `/v1/patient/{id}/problems/{pid}` | PATCH | admin, physician | Update a problem |
| `/v1/patient/{id}/labs` | GET | Any | List lab results (supports `?days=` filter) |
| `/v1/patient/{id}/labs` | POST | admin, physician, nurse | Record a lab result |
| `/v1/patient/{id}/imaging` | GET | Any | List imaging reports |
| `/v1/patient/{id}/imaging` | POST | admin, physician | Add an imaging report |
| `/v1/patient/{id}/encounters` | GET | Any | List encounters |
| `/v1/patient/{id}/encounters` | POST | admin, physician, nurse | Record an encounter |

### Documents

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/patient/{id}/documents` | POST | Any | Upload a document (multipart, max 10 MB) |
| `/v1/patient/{id}/documents` | GET | Any | List uploaded documents |
| `/v1/patient/{id}/documents/{did}` | GET | Any | Download a document |

### Lab Reports and Analysis

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/lab-report` | POST | admin, physician | Create a structured lab report |
| `/v1/lab-report/{id}` | GET | Any | Retrieve a lab report |
| `/v1/lab-report/{id}/analyze` | POST | Any | Run LLM-powered lab analysis |
| `/v1/patient/{id}/imaging/{idx}/analyze` | POST | Any | Run LLM-powered imaging analysis |

### Knowledge Base

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/knowledge/search` | GET, POST | Any | Search the clinical knowledge base |
| `/v1/demo/knowledge` | GET | Any | List all knowledge base chunks |
| `/v1/demo/patients` | GET | Any | List demo patients |
| `/v1/demo/lab-reports` | GET | Any | List demo lab reports |

### Audit Log

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/audit-log` | GET | admin, physician | View the audit log (`?limit=` and `?resource_type=` supported) |

### RAG Pipeline

Requires the embedding model (Embedgemma) to be running on port 8003.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/rag/health` | GET | Any | Check RAG availability |
| `/v1/rag/ingest/text` | POST | Any | Ingest a plain-text document |
| `/v1/rag/ingest/file` | POST | Any | Ingest a file (PDF, DOCX) |
| `/v1/rag/search` | GET, POST | Any | Semantic or hybrid search |
| `/v1/rag/documents` | GET | Any | List ingested RAG documents |
| `/v1/rag/seed` | POST | Any | Seed the RAG store with demo clinical documents |
| `/health` | GET | None | System health check |

---

## Configuration

All configuration is read from environment variables at startup.

```bash
# LLM servers
ROUTER_LLM_URL=http://localhost:8001/v1
ROUTER_MODEL=router
MEDICAL_LLM_URL=http://localhost:8002/v1
MEDICAL_MODEL=medgemma

# Embedding model (optional; required for RAG)
EMBEDDING_URL=http://localhost:8003/v1
EMBEDDING_MODEL=embedgemma

# Database
DB_PATH=./clinical.db
MOCK_DATA_DIR=./mock_data

# Authentication
JWT_SECRET=change-me-in-production
TOKEN_EXPIRE_MINUTES=480

# Storage
CHROMA_DIR=./chroma_db
MAX_UPLOAD_SIZE_MB=10

# Locale for patient-facing replies
LOCALE=zh-TW
```

> **Security note**: Set `JWT_SECRET` to a cryptographically random value in any non-development deployment.

---

## Database Schema

The SQLite database (`clinical.db`) is created automatically on first startup. All foreign key constraints are enforced.

| Table | Description |
|-------|-------------|
| `users` | User accounts: username, bcrypt password hash, role |
| `patients` | Patient demographics |
| `medications` | Patient medications, linked to `patients` |
| `allergies` | Documented allergies, linked to `patients` |
| `problems` | ICD-coded active and historical problems, linked to `patients` |
| `lab_results` | Individual discrete lab values, linked to `patients` |
| `lab_reports` | Lab report headers, linked to `patients` |
| `lab_report_results` | Line items within a lab report, linked to `lab_reports` |
| `lab_report_critical_values` | Critical value flags, linked to `lab_reports` |
| `imaging_reports` | Imaging study headers, linked to `patients` |
| `imaging_findings` | Individual findings per study, linked to `imaging_reports` |
| `imaging_impressions` | Impression statements, linked to `imaging_reports` |
| `imaging_critical_findings` | Critical imaging findings, linked to `imaging_reports` |
| `encounters` | Clinical encounter records, linked to `patients` |
| `encounter_diagnoses` | Diagnoses recorded at an encounter, linked to `encounters` |
| `documents` | Binary file uploads stored as BLOBs, linked to `patients` |
| `audit_log` | Append-only log of all write operations with user, action, resource, and timestamp |

---

## Demo Patients

Four synthetic patient records are seeded from `mock_data/` on first startup.

| ID | Name | Age | Conditions |
|----|------|-----|------------|
| P001 | 王小明 | 45 | Type 2 diabetes mellitus, hypertension, hyperlipidemia |
| P002 | 李美玲 | 32 | Hypothyroidism |
| P003 | 陳大偉 | 68 | Atrial fibrillation, congestive heart failure, CKD stage 3, type 2 DM |
| P004 | 張淑芬 | 55 | Type 2 diabetes mellitus, hypertension, early diabetic nephropathy |

---

## Safety Features

| Feature | Description |
|---------|-------------|
| Red-flag keyword detection | Predefined keywords (胸痛, 喘不過氣, 中風, 大量出血, 意識不清, 自殺念頭, 嚴重過敏反應) bypass all LLM processing and return immediate emergency instructions (119). |
| QA gate — case card | Validates that the clinical case card contains no diagnostic statements before routing to staff review. |
| QA gate — patient reply | Performs a final safety check on the patient-facing reply before transmission. |
| No-diagnosis constraint | All agent system prompts explicitly prohibit diagnostic statements; the QA gate enforces this programmatically. |
| Audit logging | Every database write is recorded in `audit_log` with the authenticated user, action type, resource identifier, and UTC timestamp. |
| JWT authentication | All non-public endpoints require a valid, unexpired bearer token. |
| Role-based access control | Permission checks are enforced in each endpoint handler before any database operation. |
| Model health checks | The server returns HTTP 503 with a descriptive error if vLLM servers are unavailable at request time. |

---

## Agent Reference

The following agent classes are defined in `agents.py`. Each agent wraps an LLM call with a dedicated system prompt from `prompts.py`.

| Agent | Model | Description |
|-------|-------|-------------|
| `RouterAgent` | Gemma 3 | Classifies intent (symptoms, lab_results, medication, follow_up, etc.) and assigns a risk level. Returns structured JSON. |
| `IntakeAgent` | MedGemma | Extracts chief complaint, symptom onset, severity, and identifies missing information. |
| `CaseCardAgent` | MedGemma + tools | Generates a structured clinical case summary. May issue up to three rounds of tool calls to retrieve EHR sections and knowledge base entries. |
| `ClarifierAgent` | MedGemma | Produces PQRST-style follow-up questions in Chinese when the chief complaint is insufficiently specific. |
| `ExplainAgent` | MedGemma + tools | Drafts a patient-facing reply in Traditional Chinese with acknowledgment, action items, warning signs, and follow-up instructions. |
| `LabAnalysisAgent` | MedGemma | Interprets a structured lab report: flags abnormal and critical values, identifies trends, and recommends follow-up. |
| `ImagingAnalysisAgent` | MedGemma | Summarises an imaging report, highlights critical findings, and recommends next steps. |
| `QAGateAgent` | MedGemma | Reviews agent output for safety violations (diagnostic statements, missing safety warnings) and returns a pass/fail decision with rationale. |

---

## File Reference

```
clinical-agents/
├── server.py              FastAPI application and all endpoint handlers
├── orchestrator.py        Clinical workflow state machine
├── agents.py              LLM agent classes
├── prompts.py             System prompts for each agent
├── llm_client.py          vLLM OpenAI-compatible HTTP client with tool calling support
├── ehr_db.py              SQLite schema, migrations, and query helpers
├── auth.py                JWT issuance and validation, RBAC enforcement
├── models.py              Pydantic data models (30+ types)
├── config.py              Environment variable configuration
├── demo_data.py           Demo patient and knowledge base seed data
├── rag_pipeline.py        ChromaDB ingestion, BM25 + semantic hybrid search
├── rag_api.py             FastAPI router for RAG endpoints
├── mock_data/
│   ├── P001.json          Demo patient: 王小明
│   ├── P002.json          Demo patient: 李美玲
│   ├── P003.json          Demo patient: 陳大偉
│   └── P004.json          Demo patient: 張淑芬
├── scripts/
│   ├── start_vllm.sh      Starts all three vLLM servers
│   └── tool_chat_template.jinja  Jinja2 chat template for tool calling
├── tests/
│   ├── conftest.py        Pytest fixtures
│   ├── unit_test.py       Unit tests (no server required)
│   └── integration_test.py  Integration tests
├── test_workflow.py        Full LLM pipeline end-to-end test
├── test_rag.py             RAG pipeline test
└── requirements.txt        Python dependencies
```

---

## Integration Test Coverage

`test_workflow.py` exercises the full LLM pipeline end-to-end and requires all three vLLM servers to be running.

| Test | Description |
|------|-------------|
| Router intent classification | Verifies that a lab inquiry is classified as `lab_results` and an appointment request as `follow_up`. |
| Emergency escalation | Confirms that messages containing `胸痛` and `喘不過氣` return an emergency status with 119 instructions without calling the LLM. |
| Intake and tool calling | Verifies that chief complaint extraction succeeds and that the pipeline reaches the `casecard_generated` stage, confirming tool calls to the database succeeded. |
| Clarification flow | Confirms that a vague symptom ("頭痛") triggers PQRST follow-up questions in Chinese. |
| Case card generation | Verifies that the LLM generates a clinical summary populated with EHR context for patient P003 (warfarin, CHF). |
| Review and reply | Verifies that an LLM-drafted patient reply in Traditional Chinese passes the QA gate and contains action items and warning signs. |
| Lab analysis | Verifies that the LLM correctly identifies abnormal values (HbA1c, glucose, INR, BNP) in demo lab reports LAB001 and LAB002. |
| Knowledge search | Verifies that RAG retrieval returns relevant SOPs for 糖尿病, 胸痛, 心衰竭, and 抗凝血. |
| Session audit trail | Verifies a complete pipeline trace from `message_received` to `reply_sent`. |
| Database CRUD | Verifies create/read/update operations, document upload and download, and audit log integrity. |
