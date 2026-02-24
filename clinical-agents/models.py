import uuid
from datetime import datetime, date
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, computed_field

class Intent(str, Enum):
    SYMPTOMS = "symptoms"
    LAB_RESULTS = "lab_results"
    IMAGING = "imaging"
    MEDICATION = "medication"
    FOLLOW_UP = "follow_up"
    ADMIN = "admin"
    OTHER = "other"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TriageDestination(str, Enum):
    EMERGENCY = "emergency"
    PHYSICIAN = "physician"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    FRONT_DESK = "front_desk"


class UserRole(str, Enum):
    ADMIN = "admin"
    PHYSICIAN = "physician"
    NURSE = "nurse"
    STAFF = "staff"


class Symptom(BaseModel):
    description: str
    location: str | None = None
    onset: str | None = None
    duration: str | None = None
    severity: int | None = Field(None, ge=1, le=10)
    character: str | None = None
    radiation: str | None = None
    aggravating_factors: list[str] = Field(default_factory=list)
    relieving_factors: list[str] = Field(default_factory=list)
    associated_symptoms: list[str] = Field(default_factory=list)
    progression: Literal["improving", "stable", "worsening"] | None = None


class Medication(BaseModel):
    id: int | None = None
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    indication: str | None = None
    start_date: date | None = None
    status: Literal["active", "discontinued", "on_hold"] = "active"


class Allergy(BaseModel):
    id: int | None = None
    allergen: str
    reaction: str | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None
    verified: bool = False


class Problem(BaseModel):
    id: int | None = None
    icd_code: str | None = None
    description: str
    onset_date: date | None = None
    status: Literal["active", "resolved", "inactive"] = "active"


class LabResult(BaseModel):
    id: int | None = None
    test_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: Literal["normal", "low", "high", "critical_low", "critical_high"] | None = (
        None
    )
    collected_date: date | None = None
    notes: str | None = None


class LabReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"LAB-{uuid.uuid4().hex[:8]}")
    patient_id: str | None = None
    collected_date: date | None = None
    reported_date: date | None = None
    ordering_provider: str | None = None
    results: list[LabResult] = Field(default_factory=list)
    critical_values: list[str] = Field(default_factory=list)
    interpretation: str | None = None


class ImagingFinding(BaseModel):
    location: str
    finding: str
    severity: Literal["normal", "mild", "moderate", "severe"] | None = None


class ImagingReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"IMG-{uuid.uuid4().hex[:8]}")
    patient_id: str | None = None
    study_type: str
    study_date: date | None = None
    body_part: str
    indication: str | None = None
    technique: str | None = None
    findings: list[ImagingFinding] = Field(default_factory=list)
    impression: list[str] = Field(default_factory=list)
    critical_findings: list[str] = Field(default_factory=list)
    radiologist: str | None = None


class Encounter(BaseModel):
    encounter_id: str
    date: date
    type: str
    provider: str
    chief_complaint: str | None = None
    diagnoses: list[str] = Field(default_factory=list)
    summary: str | None = None


class RAGChunk(BaseModel):
    chunk_id: str
    source: str
    source_type: Literal["clinical_note", "sop", "education", "protocol"]
    content: str
    relevance_score: float = Field(ge=0, le=1)


class PatientInfo(BaseModel):
    patient_id: str = Field(default_factory=lambda: f"P{uuid.uuid4().hex[:6].upper()}")
    name: str
    sex: Literal["male", "female", "other"]
    mrn: str = Field(default_factory=lambda: f"MRN-{uuid.uuid4().hex[:8].upper()}")
    dob: date

    @computed_field
    @property
    def age(self) -> int:
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {"examples": [{"name": "王小明", "sex": "male", "dob": "1958-03-15"}]},
    }


class PatientRecord(BaseModel):
    patient_id: str
    info: PatientInfo
    medications: list[Medication] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    labs: list[LabResult] = Field(default_factory=list)
    imaging: list[ImagingReport] = Field(default_factory=list)
    encounters: list[Encounter] = Field(default_factory=list)


class User(BaseModel):
    id: int | None = None
    platform_id: str | None = None
    username: str
    role: UserRole
    name: str
    active: bool = True
    created_at: datetime | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.STAFF
    name: str


class UserUpdate(BaseModel):
    username: str
    platform_id: str | None = None
    role: UserRole | None = None
    name: str | None = None
    active: bool | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class PatientAccess(BaseModel):
    id: int | None = None
    patient_id: str
    platform_id: str
    relationship: Literal[
        "family", "self", "front_desk", "admin", "physician", "nurse", "staff", "pharmacist", "emergency",
    ]
    access_level: Literal["full", "limited", "read_only"] = "read_only"


class PatientAccessCreate(BaseModel):
    patient_id: str
    platform_id: str
    relationship: str
    access_level: Literal["full", "limited", "read_only"] = "read_only"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User

class Document(BaseModel):
    id: int | None = None
    patient_id: str
    doc_type: Literal["scan", "photo", "report", "other"] = "scan"
    filename: str
    mime_type: str | None = None
    description: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None


class AuditEntry(BaseModel):
    id: int | None = None
    user_id: int | None = None
    username: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict = Field(default_factory=dict)
    timestamp: datetime | None = None



class RouterOutput(BaseModel):
    intent: Literal["symptoms", "lab_results", "imaging", "medication", "follow_up", "admin", "other"]
    risk_level: Literal["critical", "high", "medium", "low"]
    next_action: Literal["escalate_now", "ask_clarifying", "proceed"]


class RouterDecision(BaseModel):
    intent: Intent
    risk_level: RiskLevel
    red_flags: list[str] = Field(default_factory=list, max_length=5)
    next_action: Literal["escalate_now", "ask_clarifying", "proceed"]
    clarifying_questions: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str | None = Field(None, max_length=200)


class IntakeData(BaseModel):
    intake_id: str
    patient_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    chief_complaint: str
    chief_complaint_duration: str | None = None
    symptoms: list[Symptom] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class ContextPack(BaseModel):
    context_id: str
    patient_id: str | None = None
    intake: IntakeData | None = None


class TriageRecommendation(BaseModel):
    destination: TriageDestination
    urgency: Literal["immediate", "same_day", "next_available", "routine"]
    reasoning: str
    confidence: float = Field(ge=0, le=1)


class CaseCard(BaseModel):
    case_id: str
    context_id: str
    patient_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    chief_complaint: str
    relevant_history: str
    current_meds_summary: str | None = None
    recent_labs_summary: str | None = None
    recent_imaging_summary: str | None = None
    pertinent_positives: list[str] = Field(default_factory=list)
    pertinent_negatives: list[str] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    triage: TriageRecommendation
    ready_for_routing: bool = False


class PatientReply(BaseModel):
    draft_id: str
    locale: str = "zh-TW"
    greeting: str
    acknowledgment: str
    understanding: str
    response: str
    action_items: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    follow_up: str | None = None
    closing: str
    emergency_info: str | None = None


class Ticket(BaseModel):
    ticket_id: str
    patient_id: str | None = None
    intent: Intent
    risk_level: RiskLevel
    red_flags: list[str] = Field(default_factory=list)
    destination: TriageDestination
    urgency: str
    case_card: CaseCard
    draft_reply: PatientReply | None = None
    status: Literal["pending", "in_review", "approved", "sent", "escalated"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    physician_notes: str | None = None


class QAResult(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)