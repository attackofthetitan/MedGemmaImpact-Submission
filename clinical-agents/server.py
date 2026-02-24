import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from config import config
from models import (
    PatientAccessCreate,
    User,
    UserRole,
    UserCreate,
    UserLogin,
    TokenResponse,
    PatientInfo,
    Medication,
    Allergy,
    Problem,
    LabResult,
    LabReport,
    ImagingReport,
    ImagingFinding,
    Encounter,
    Document,
    UserUpdate,
)
from auth import (
    get_current_user,
    require_roles,
    hash_password,
    verify_password,
    create_token,
)
from ehr_db import db
from orchestrator import ClinicalOrchestrator


class MessageRequest(BaseModel):
    content: str
    patient_id: str | None = None
    session_id: str | None = None


class ClarificationRequest(BaseModel):
    session_id: str
    responses: dict[str, str]


class ReviewRequest(BaseModel):
    session_id: str
    approved: bool
    physician_notes: str | None = None
    key_points: list[str] | None = None


class SendRequest(BaseModel):
    session_id: str


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 3


class MedicationUpdate(BaseModel):
    name: str | None = None
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    indication: str | None = None
    start_date: str | None = None
    status: str | None = None


class ProblemUpdate(BaseModel):
    icd_code: str | None = None
    description: str | None = None
    onset_date: str | None = None
    status: str | None = None


class PatientUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: str | None = None
    dob: str | None = None


orchestrator: ClinicalOrchestrator | None = None
llm_status: dict = {"router": False, "medical": False, "embedding": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator, llm_status

    print("Initializing database...")
    await db.initialize()

    print("Initializing Clinical Agent System...")
    orchestrator = ClinicalOrchestrator()

    print(f"Checking Medical LLM at {config.medical_llm.base_url}...")
    llm_status["medical"] = await orchestrator.intake.client.health_check()
    print(f"  Medical LLM: {'Connected' if llm_status['medical'] else 'NOT AVAILABLE'}")

    llm_status["router"] = llm_status["medical"]
    print(f"  Router: using Medical LLM (shared)")

    llm_status["embedding"] = False
    print(f"  Embedding: (checked on first RAG request)")

    if not llm_status["router"] or not llm_status["medical"]:
        print("\n⚠ LLM servers unavailable")
    else:
        print("\n✓ All LLM servers connected.\n")

    yield

    print("Shutting down...")
    await db.close()


app = FastAPI(title="Clinical Agent System API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


async def require_llm():
    global llm_status
    if not llm_status["medical"]:
        llm_status["medical"] = await orchestrator.intake.client.health_check()
        llm_status["router"] = llm_status["medical"]
    if not llm_status["medical"]:
        raise HTTPException(
            503, f"Medical LLM not available at {config.medical_llm.base_url}"
        )


async def require_patient(patient_id: str) -> dict:
    patient = await db.get_patient(patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient


async def require_user(username: str) -> dict:
    user = await db.get_user_by_username(username)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@app.get("/health")
async def health():
    return {
        "status": "healthy" if all(llm_status.values()) else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "llm_servers": {
            "router": {
                "url": config.router_llm.base_url,
                "connected": llm_status["router"],
            },
            "medical": {
                "url": config.medical_llm.base_url,
                "connected": llm_status["medical"],
            },
            "embedding": {
                "url": config.embedding.base_url,
                "connected": llm_status["embedding"],
            },
        },
    }


@app.post("/v1/auth/login", response_model=TokenResponse)
async def login(req: UserLogin):
    user_data = await db.get_user_by_username(req.username)
    if not user_data or not verify_password(req.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user_data["id"], user_data["username"], user_data["role"])
    user = User(
        id=user_data["id"],
        username=user_data["username"],
        role=UserRole(user_data["role"]),
        name=user_data["name"],
    )

    await db.log_audit(
        "login", "user", str(user_data["id"]), user_data["id"], user_data["username"]
    )
    return TokenResponse(access_token=token, user=user)


@app.post("/v1/auth/register", response_model=User)
async def register(
    req: UserCreate, user: User = Depends(require_roles(UserRole.ADMIN))
):
    existing = await db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(400, "Username already exists")

    pw_hash = hash_password(req.password)
    user_id = await db.create_user(req.username, pw_hash, req.role.value, req.name)
    await db.log_audit(
        "create_user",
        "user",
        str(user_id),
        user.id,
        user.username,
        {"new_username": req.username, "role": req.role.value},
    )
    return User(id=user_id, username=req.username, role=req.role, name=req.name)


@app.get("/v1/auth/me", response_model=User)
async def get_me(user: User = Depends(get_current_user)):
    return user


@app.get("/v1/auth/users")
async def list_users(user: User = Depends(require_roles(UserRole.ADMIN))):
    users = await db.list_users()
    return {"users": [u.model_dump() for u in users]}


@app.patch("/v1/auth/user")
async def update_user(
    req: UserUpdate, user: User = Depends(require_roles(UserRole.ADMIN))
):
    user_data = await require_user(req.username)
    cur_user = User.model_validate(user_data)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = await db.update_user(cur_user.id, updates)
    await db.log_audit(
        "update_user", "user", str(user.id), user.id, user.username, updates
    )
    return result


@app.get("/v1/user/role/{platform_id}")
async def get_role(
    platform_id: str, user: User = Depends(require_roles(UserRole.ADMIN))
):
    cur_user = await db.get_user_by_platform_id(platform_id)
    if not cur_user or not cur_user.get("role"):
        raise HTTPException(404, "role not found")
    return {"role": cur_user["role"]}


@app.get("/v1/platform/patient")
async def get_patient(platform_id: str, user: User = Depends(get_current_user)):
    patient = await db.get_patient_by_platform_id(platform_id)
    if not patient:
        raise HTTPException(404, "patient not found")
    return {"patient_id": patient["patient_id"]}


@app.get("/v1/patient/staff/{relationship}")
async def get_staff_by_relationship(
    relationship: str,
    patient_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    staff = await db.get_staff_by_relationship(relationship, patient_id)
    if not staff:
        raise HTTPException(404, "staff not found")
    return {"staff_id": staff["platform_id"]}

@app.get("/v1/patients/{patient_id}/platform-id")
async def get_patient_platform_id(
    patient_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    platform_id = await db.get_platform_id_by_patient_id(patient_id)
    if not platform_id:
        raise HTTPException(404, "platform_id not found")
    return {"platform_id": platform_id}



@app.get("/v1/patient_access")
async def check_patient_access(user: User = Depends(require_roles(UserRole.ADMIN))):
    user_access = await db.list_user_patient_access()
    return {"patient_access": user_access}


@app.post("/v1/patient_access")
async def creae_user_patient_access(
    req: PatientAccessCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    try:
        result = await db.creae_user_patient_access(
            req.patient_id,
            req.platform_id,
            req.relationship,
            req.access_level,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, "Patient ID or MRN already exists")
        raise
    await db.log_audit(
        "create_patient_access",
        "patient_access",
        req.patient_id,
        None,
        user.username,
        {
            "patient_id": req.patient_id,
            "platform_id": req.platform_id,
            "relationship": req.relationship,
            "access_level": req.access_level,
        },
    )
    return result


@app.get("/v1/demo/patients")
async def list_demo_patients(user: User = Depends(get_current_user)):
    patients = await db.list_patients()
    return {"patients": patients}


@app.get("/v1/patient/{patient_id}")
async def get_patient_summary(patient_id: str, user: User = Depends(get_current_user)):
    patient = await require_patient(patient_id)
    return {
        "patient": patient,
        "medications": [m.model_dump() for m in await db.get_medications(patient_id)],
        "allergies": [a.model_dump() for a in await db.get_allergies(patient_id)],
        "problems": [p.model_dump() for p in await db.get_problems(patient_id)],
        "recent_labs": [l.model_dump() for l in await db.get_labs(patient_id, 30)],
        "recent_imaging": [
            i.model_dump() for i in await db.get_imaging(patient_id, 180)
        ],
        "recent_encounters": [
            e.model_dump() for e in await db.get_encounters(patient_id, 90)
        ],
    }


@app.post("/v1/patient")
async def create_patient(
    info: PatientInfo,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    try:
        result = await db.create_patient(info)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, "Patient ID or MRN already exists")
        raise
    await db.log_audit(
        "create_patient",
        "patient",
        info.patient_id,
        user.id,
        user.username,
        {"name": info.name, "mrn": info.mrn},
    )
    return result


@app.patch("/v1/patient/{patient_id}")
async def update_patient(
    patient_id: str,
    req: PatientUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = await db.update_patient(patient_id, updates)
    await db.log_audit(
        "update_patient", "patient", patient_id, user.id, user.username, updates
    )
    return result


@app.get("/v1/patient/{patient_id}/medications")
async def get_medications(patient_id: str, user: User = Depends(get_current_user)):
    await require_patient(patient_id)
    meds = await db.get_medications(patient_id)
    return {"patient_id": patient_id, "medications": [m.model_dump() for m in meds]}


@app.post("/v1/patient/{patient_id}/medications")
async def add_medication(
    patient_id: str,
    med: Medication,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    med_id = await db.add_medication(patient_id, med)
    await db.log_audit(
        "add_medication",
        "medication",
        str(med_id),
        user.id,
        user.username,
        {"patient_id": patient_id, "name": med.name, "dose": med.dose},
    )
    return {"id": med_id, "patient_id": patient_id, "name": med.name}


@app.patch("/v1/patient/{patient_id}/medications/{med_id}")
async def update_medication(
    patient_id: str,
    med_id: int,
    req: MedicationUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await db.update_medication(patient_id, med_id, updates)
    if not ok:
        raise HTTPException(404, "Medication not found")
    await db.log_audit(
        "update_medication",
        "medication",
        str(med_id),
        user.id,
        user.username,
        {"patient_id": patient_id, **updates},
    )
    return {"status": "updated", "id": med_id}


@app.get("/v1/patient/{patient_id}/allergies")
async def get_allergies(patient_id: str, user: User = Depends(get_current_user)):
    await require_patient(patient_id)
    allergies = await db.get_allergies(patient_id)
    return {"patient_id": patient_id, "allergies": [a.model_dump() for a in allergies]}


@app.post("/v1/patient/{patient_id}/allergies")
async def add_allergy(
    patient_id: str,
    allergy: Allergy,
    user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.PHYSICIAN, UserRole.NURSE)
    ),
):
    await require_patient(patient_id)
    allergy_id = await db.add_allergy(patient_id, allergy)
    await db.log_audit(
        "add_allergy",
        "allergy",
        str(allergy_id),
        user.id,
        user.username,
        {"patient_id": patient_id, "allergen": allergy.allergen},
    )
    return {"id": allergy_id, "patient_id": patient_id, "allergen": allergy.allergen}


@app.get("/v1/patient/{patient_id}/problems")
async def get_problems(patient_id: str, user: User = Depends(get_current_user)):
    await require_patient(patient_id)
    problems = await db.get_problems(patient_id)
    return {"patient_id": patient_id, "problems": [p.model_dump() for p in problems]}


@app.post("/v1/patient/{patient_id}/problems")
async def add_problem(
    patient_id: str,
    problem: Problem,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    prob_id = await db.add_problem(patient_id, problem)
    await db.log_audit(
        "add_problem",
        "problem",
        str(prob_id),
        user.id,
        user.username,
        {"patient_id": patient_id, "description": problem.description},
    )
    return {"id": prob_id, "patient_id": patient_id, "description": problem.description}


@app.patch("/v1/patient/{patient_id}/problems/{prob_id}")
async def update_problem(
    patient_id: str,
    prob_id: int,
    req: ProblemUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await db.update_problem(patient_id, prob_id, updates)
    if not ok:
        raise HTTPException(404, "Problem not found")
    await db.log_audit(
        "update_problem",
        "problem",
        str(prob_id),
        user.id,
        user.username,
        {"patient_id": patient_id, **updates},
    )
    return {"status": "updated", "id": prob_id}


@app.get("/v1/patient/{patient_id}/labs")
async def get_labs(
    patient_id: str, days: int = 30, user: User = Depends(get_current_user)
):
    await require_patient(patient_id)
    labs = await db.get_labs(patient_id, days)
    return {
        "patient_id": patient_id,
        "days": days,
        "labs": [l.model_dump() for l in labs],
    }


@app.post("/v1/patient/{patient_id}/labs")
async def add_lab_result(
    patient_id: str,
    lab: LabResult,
    user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.PHYSICIAN, UserRole.NURSE)
    ),
):
    await require_patient(patient_id)
    lab_id = await db.add_lab_result(patient_id, lab)
    await db.log_audit(
        "add_lab_result",
        "lab_result",
        str(lab_id),
        user.id,
        user.username,
        {"patient_id": patient_id, "test": lab.test_name, "value": lab.value},
    )
    return {"id": lab_id, "patient_id": patient_id, "test_name": lab.test_name}


@app.get("/v1/lab-report/{report_id}")
async def get_lab_report(report_id: str, user: User = Depends(get_current_user)):
    report = await db.get_lab_report(report_id)
    if not report:
        raise HTTPException(404, "Lab report not found")
    return report.model_dump()


@app.post("/v1/lab-report")
async def add_lab_report(
    report: LabReport,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    try:
        report_id = await db.add_lab_report(report)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, "Report ID already exists")
        raise
    await db.log_audit(
        "add_lab_report",
        "lab_report",
        report_id,
        user.id,
        user.username,
        {"patient_id": report.patient_id},
    )
    return {"report_id": report_id, "status": "created"}


@app.post("/v1/lab-report/{report_id}/analyze")
async def analyze_lab_report(
    report_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    await require_llm()
    result = await orchestrator.analyze_lab_report(report_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/v1/demo/lab-reports")
async def list_demo_lab_reports(user: User = Depends(get_current_user)):
    reports = []
    for rid in ["LAB001", "LAB002"]:
        report = await db.get_lab_report(rid)
        if report:
            reports.append(report.model_dump())
    return {"reports": reports}


@app.get("/v1/patient/{patient_id}/imaging")
async def get_imaging(
    patient_id: str, days: int = 180, user: User = Depends(get_current_user)
):
    await require_patient(patient_id)
    imaging = await db.get_imaging(patient_id, days)
    return {
        "patient_id": patient_id,
        "days": days,
        "imaging": [i.model_dump() for i in imaging],
    }


@app.post("/v1/patient/{patient_id}/imaging")
async def add_imaging_report(
    patient_id: str,
    report: ImagingReport,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    await require_patient(patient_id)
    report_id = await db.add_imaging_report(patient_id, report)
    await db.log_audit(
        "add_imaging_report",
        "imaging_report",
        report_id,
        user.id,
        user.username,
        {"patient_id": patient_id, "study_type": report.study_type},
    )
    return {"report_id": report_id, "patient_id": patient_id}


@app.post("/v1/patient/{patient_id}/imaging/{index}/analyze")
async def analyze_imaging(
    patient_id: str,
    index: int = 0,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    await require_llm()
    result = await orchestrator.analyze_imaging(patient_id, index)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/v1/patient/{patient_id}/encounters")
async def get_encounters(
    patient_id: str, days: int = 90, user: User = Depends(get_current_user)
):
    await require_patient(patient_id)
    encounters = await db.get_encounters(patient_id, days)
    return {
        "patient_id": patient_id,
        "days": days,
        "encounters": [e.model_dump() for e in encounters],
    }


@app.post("/v1/patient/{patient_id}/encounters")
async def add_encounter(
    patient_id: str,
    enc: Encounter,
    user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.PHYSICIAN, UserRole.NURSE)
    ),
):
    await require_patient(patient_id)
    enc_id = await db.add_encounter(patient_id, enc)
    await db.log_audit(
        "add_encounter",
        "encounter",
        enc_id,
        user.id,
        user.username,
        {"patient_id": patient_id, "type": enc.type},
    )
    return {"encounter_id": enc_id, "patient_id": patient_id}


@app.post("/v1/patient/{patient_id}/documents")
async def upload_document(
    patient_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("scan"),
    description: str = Form(None),
    user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.PHYSICIAN, UserRole.NURSE)
    ),
):
    await require_patient(patient_id)

    data = await file.read()
    max_bytes = config.max_upload_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large. Max: {config.max_upload_size_mb}MB")

    doc_id = await db.add_document(
        patient_id=patient_id,
        filename=file.filename or "unnamed",
        data=data,
        mime_type=file.content_type,
        doc_type=doc_type,
        description=description,
        uploaded_by=user.username,
    )
    await db.log_audit(
        "upload_document",
        "document",
        str(doc_id),
        user.id,
        user.username,
        {"patient_id": patient_id, "filename": file.filename, "size": len(data)},
    )
    return {"id": doc_id, "patient_id": patient_id, "filename": file.filename}


@app.get("/v1/patient/{patient_id}/documents")
async def list_documents(patient_id: str, user: User = Depends(get_current_user)):
    await require_patient(patient_id)
    docs = await db.get_documents(patient_id)
    return {"patient_id": patient_id, "documents": [d.model_dump() for d in docs]}


@app.get("/v1/patient/{patient_id}/documents/{doc_id}")
async def download_document(
    patient_id: str, doc_id: int, user: User = Depends(get_current_user)
):
    await require_patient(patient_id)
    result = await db.get_document_data(doc_id, patient_id)
    if not result:
        raise HTTPException(404, "Document not found")
    data, filename, mime_type = result
    return Response(
        content=data,
        media_type=mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/audit-log")
async def get_audit_log(
    limit: int = 100,
    resource_type: str | None = None,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    entries = await db.get_audit_log(limit, resource_type)
    return {"entries": [e.model_dump() for e in entries], "total": len(entries)}


@app.post("/v1/message")
async def process_message(
    request: MessageRequest, user: User = Depends(get_current_user)
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    await require_llm()
    return await orchestrator.process_message(
        request.content, request.patient_id, request.session_id
    )


@app.post("/v1/clarification")
async def process_clarification(
    request: ClarificationRequest, user: User = Depends(get_current_user)
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    await require_llm()
    return await orchestrator.process_clarification(
        request.session_id, request.responses
    )


@app.post("/v1/review")
async def process_review(
    request: ReviewRequest,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PHYSICIAN)),
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    await require_llm()
    return await orchestrator.process_review(
        request.session_id,
        request.approved,
        request.physician_notes,
        request.key_points,
    )


@app.post("/v1/send")
async def send_reply(request: SendRequest, user: User = Depends(get_current_user)):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    return await orchestrator.send_reply(request.session_id)


@app.get("/v1/session/{session_id}")
async def get_session(session_id: str, user: User = Depends(get_current_user)):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    session = orchestrator.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.get("/v1/sessions")
async def list_sessions(user: User = Depends(get_current_user)):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    return orchestrator.list_sessions()


@app.post("/v1/knowledge/search")
async def search_knowledge_post(
    request: KnowledgeSearchRequest, user: User = Depends(get_current_user)
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    return await orchestrator.search_knowledge_base(request.query, request.top_k)


@app.get("/v1/knowledge/search")
async def search_knowledge_get(
    query: str, top_k: int = 3, user: User = Depends(get_current_user)
):
    if not orchestrator:
        raise HTTPException(503, "System not initialized")
    return await orchestrator.search_knowledge_base(query, top_k)


@app.get("/v1/demo/knowledge")
async def list_knowledge_base(user: User = Depends(get_current_user)):
    from demo_data import KNOWLEDGE_BASE

    return {"chunks": [c.model_dump() for c in KNOWLEDGE_BASE]}


try:
    from rag_api import router as rag_router

    app.include_router(rag_router)
except ImportError:
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
