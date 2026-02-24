import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from models import (
    Intent, RiskLevel, TriageDestination, TriageRecommendation,
    RouterDecision, IntakeData, ContextPack, CaseCard, Ticket, PatientReply,
    LabReport, ImagingReport, Medication, Allergy, Problem
)
from agents import (
    RouterAgent, IntakeAgent, CaseCardAgent, ExplainAgent,
    LabAnalysisAgent, ImagingAnalysisAgent, ClarifierAgent, QAGateAgent,
    create_clients, get_emergency_response, CRITICAL_RED_FLAGS
)
from llm_client import LLMConnectionError
from ehr_db import db
from demo_data import search_knowledge

MAX_CLARIFICATION_ROUNDS = 2
MAX_QA_RETRIES = 2


@dataclass 
class Session:
    session_id: str
    patient_id: str | None = None
    context: ContextPack | None = None
    route_decision: RouterDecision | None = None
    ticket: Ticket | None = None
    status: str = "active"
    clarification_count: int = 0
    qa_retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    audit_log: list[dict] = field(default_factory=list)
    
    def log(self, action: str, details: dict | None = None):
        self.audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "details": details or {}
        })


class ClinicalOrchestrator:
    def __init__(self):
        clients = create_clients()
        self.router = RouterAgent(clients.router)
        self.intake = IntakeAgent(clients.medical)
        self.casecard = CaseCardAgent(clients.medical)
        self.explain = ExplainAgent(clients.medical)
        self.lab_analysis = LabAnalysisAgent(clients.medical)
        self.imaging_analysis = ImagingAnalysisAgent(clients.medical)
        self.clarifier = ClarifierAgent(clients.medical)
        self.qa_gate = QAGateAgent(clients.medical)
        self.sessions: dict[str, Session] = {}

    async def _execute_tool(self, name: str, args: dict) -> str:
        if name == "search_knowledge":
            chunks = search_knowledge(args.get("query", ""), top_k=3)
            if not chunks:
                return "No relevant documents found."
            parts = []
            for c in chunks:
                parts.append(f"[{c.source_type}] {c.source}:\n{c.content[:500]}")
            return "\n\n".join(parts)

        if name == "get_patient_ehr":
            pid = args.get("patient_id", "")
            section = args.get("section", "")
            patient = await db.get_patient(pid)
            if not patient:
                return f"Patient {pid} not found."

            if section == "all":
                problems = [{"description": p.description, "status": p.status, "icd": p.icd_code} for p in await db.get_problems(pid)]
                meds = [{"name": m.name, "dose": m.dose, "frequency": m.frequency, "indication": m.indication} for m in await db.get_medications(pid)]
                allergies = [{"allergen": a.allergen, "reaction": a.reaction, "severity": a.severity} for a in await db.get_allergies(pid)]
                labs = [{"test": l.test_name, "value": l.value, "unit": l.unit, "flag": l.flag, "date": str(l.collected_date)} for l in await db.get_labs(pid, 30)]
                imaging = [{"study": i.study_type, "date": str(i.study_date), "impression": i.impression} for i in await db.get_imaging(pid, 180)]
                encounters = [{"date": str(e.date), "type": e.type, "provider": e.provider, "summary": e.summary} for e in await db.get_encounters(pid, 90)]
                return json.dumps({
                    "patient": patient,
                    "problems": problems,
                    "medications": meds,
                    "allergies": allergies,
                    "recent_labs": labs,
                    "recent_imaging": imaging,
                    "recent_encounters": encounters,
                }, ensure_ascii=False)

            if section == "summary":
                problems = [p.description for p in await db.get_problems(pid)]
                meds = [f"{m.name} {m.dose or ''}" for m in await db.get_medications(pid)]
                allergies = [a.allergen for a in await db.get_allergies(pid)]
                return json.dumps({"patient": patient, "problems": problems, "medications": meds, "allergies": allergies}, ensure_ascii=False)

            if section == "problems":
                items = await db.get_problems(pid)
                return json.dumps([{"description": p.description, "status": p.status, "icd": p.icd_code} for p in items], ensure_ascii=False)

            if section == "medications":
                items = await db.get_medications(pid)
                return json.dumps([{"name": m.name, "dose": m.dose, "frequency": m.frequency, "indication": m.indication} for m in items], ensure_ascii=False)

            if section == "allergies":
                items = await db.get_allergies(pid)
                return json.dumps([{"allergen": a.allergen, "reaction": a.reaction, "severity": a.severity} for a in items], ensure_ascii=False)

            if section == "labs":
                items = await db.get_labs(pid, 30)
                return json.dumps([{"test": l.test_name, "value": l.value, "unit": l.unit, "flag": l.flag, "date": str(l.collected_date)} for l in items], ensure_ascii=False)

            if section == "imaging":
                items = await db.get_imaging(pid, 180)
                return json.dumps([{"study": i.study_type, "date": str(i.study_date), "impression": i.impression} for i in items], ensure_ascii=False)

            if section == "encounters":
                items = await db.get_encounters(pid, 90)
                return json.dumps([{"date": str(e.date), "type": e.type, "provider": e.provider, "summary": e.summary} for e in items], ensure_ascii=False)

            return f"Unknown section: {section}"

        return f"Unknown tool: {name}"


    def _response(self, session: Session, **kwargs) -> dict:
        base = {
            "session_id": session.session_id,
            "patient_id": session.patient_id,
        }
        base.update(kwargs)
        return base

    async def process_message(
        self,
        content: str,
        patient_id: str | None = None,
        session_id: str | None = None
    ) -> dict:
        session = self._get_or_create_session(session_id, patient_id)
        session.log("message_received", {"content_length": len(content)})
        
        quick_flags = self.router.quick_screen(content)
        if any(f in CRITICAL_RED_FLAGS for f in quick_flags):
            session.log("emergency_quick_screen", {"flags": quick_flags})
            return await self._emergency_response(session, quick_flags, content)
        
        route = await self.router.route(content)
        session.route_decision = route
        session.log("routing_complete", {
            "intent": route.intent.value, 
            "risk": route.risk_level.value, 
            "flags": route.red_flags,
            "next_action": route.next_action
        })
        
        print(f"[DEBUG] Router decision: intent={route.intent.value}, risk={route.risk_level.value}, next_action={route.next_action}")
        
        if route.next_action == "escalate_now":
            return await self._emergency_response(session, route.red_flags, content)
        
        intake = await self.intake.process(content, patient_id)
        session.log("intake_complete", {"chief_complaint": intake.chief_complaint})
        
        print(f"[DEBUG] Intake: chief_complaint={intake.chief_complaint}, missing_info={intake.missing_info}")
        
        context = await self._build_context(intake, patient_id)
        session.context = context
        session.log("context_built", {"ehr_available": bool(patient_id and await db.get_patient(patient_id))})
        
        if route.next_action == "ask_clarifying":
            return await self._request_clarification(session, intake)
        
        return await self._generate_ticket(session, intake, route)

    async def process_clarification(
        self,
        session_id: str,
        responses: dict[str, str]
    ) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        session.clarification_count += 1
        session.log("clarification_received", {
            "response_count": len(responses),
            "round": session.clarification_count,
        })

        combined = "\n".join([f"Q: {q}\nA: {a}" for q, a in responses.items()])
        original = session.context.intake.chief_complaint if session.context and session.context.intake else ""
        enriched_content = f"{original}\n\n追加資訊：\n{combined}"

        # Rerun intake 
        intake = await self.intake.process(enriched_content, session.patient_id)
        session.log("intake_complete", {"chief_complaint": intake.chief_complaint})

        context = await self._build_context(intake, session.patient_id)
        session.context = context

        route = session.route_decision
        if not route:
            route = await self.router.route(enriched_content)
            session.route_decision = route

        return await self._generate_ticket(session, intake, route)

    async def process_review(
        self,
        session_id: str,
        approved: bool,
        physician_notes: str | None = None,
        key_points: list[str] | None = None
    ) -> dict:
        session = self.sessions.get(session_id)
        if not session or not session.ticket:
            return {"error": "Session or ticket not found"}
        
        session.log("staff_review", {
            "approved": approved,
            "has_notes": physician_notes is not None,
            "previous_status": session.ticket.status,
        })
        
        if not approved:
            session.ticket.status = "escalated"
            session.ticket.physician_notes = physician_notes
            session.status = "escalated"
            return self._response(session,
                status="escalated",
                ticket_id=session.ticket.ticket_id,
                ticket=session.ticket.model_dump(),
                physician_notes=physician_notes,
                next_action="manual_handling",
                hint="Re-submit POST /v1/review with approved=true to re-enter pipeline",
            )
        
        draft = await self.explain.generate_reply(
            session.ticket.case_card,
            session.ticket.risk_level,
            physician_notes,
            tool_executor=self._execute_tool,
        )
        
        if key_points:
            draft.action_items = key_points + draft.action_items
        
        qa_result = await self.qa_gate.validate(draft.model_dump_json(), session.ticket.risk_level)
        session.log("reply_qa", {"passed": qa_result.passed, "retry": session.qa_retry_count})
        
        session.ticket.draft_reply = draft
        session.ticket.physician_notes = physician_notes
        session.ticket.reviewed_at = datetime.utcnow()

        if qa_result.passed:
            session.qa_retry_count = 0
            session.ticket.status = "approved"
            return self._response(session,
                status="ready_to_send",
                ticket_id=session.ticket.ticket_id,
                draft_reply=draft.model_dump(),
                qa_result=qa_result.model_dump(),
                next_action="send_to_patient",
            )
        
        session.qa_retry_count += 1
        if session.qa_retry_count >= MAX_QA_RETRIES:
            # Auto-approve with warning after max retries
            session.log("qa_circuit_breaker", {
                "retries": session.qa_retry_count,
                "issues": qa_result.issues,
            })
            session.qa_retry_count = 0
            session.ticket.status = "approved"
            return self._response(session,
                status="ready_to_send",
                ticket_id=session.ticket.ticket_id,
                draft_reply=draft.model_dump(),
                qa_result=qa_result.model_dump(),
                qa_warning="Auto-approved after QA retry limit. Please review carefully.",
                next_action="send_to_patient",
            )
        
        session.ticket.status = "in_review"
        return self._response(session,
            status="needs_revision",
            ticket_id=session.ticket.ticket_id,
            draft_reply=draft.model_dump(),
            qa_result=qa_result.model_dump(),
            qa_retry=session.qa_retry_count,
            qa_max_retries=MAX_QA_RETRIES,
            next_action="revise_reply",
            hint="Re-submit POST /v1/review with physician_notes to regenerate the draft",
        )

    async def send_reply(self, session_id: str) -> dict:
        session = self.sessions.get(session_id)
        if not session or not session.ticket or not session.ticket.draft_reply:
            return {"error": "No approved reply to send"}
        
        session.ticket.status = "sent"
        session.status = "completed"
        session.log("reply_sent")
        
        return self._response(session,
            status="sent",
            ticket_id=session.ticket.ticket_id,
            reply=session.ticket.draft_reply.model_dump(),
            message="Reply sent to patient",
        )

    async def analyze_lab_report(self, report_id: str) -> dict:
        report = await db.get_lab_report(report_id)
        if not report:
            return {"error": "Lab report not found"}
        
        analysis = await self.lab_analysis.analyze(report)
        return {
            "report_id": report_id,
            "report": report.model_dump(),
            "analysis": analysis
        }
    
    async def analyze_imaging(self, patient_id: str, report_index: int = 0) -> dict:
        imaging_reports = await db.get_imaging(patient_id)
        if not imaging_reports or report_index >= len(imaging_reports):
            return {"error": "Imaging report not found"}
        
        report = imaging_reports[report_index]
        analysis = await self.imaging_analysis.analyze(report)
        return {
            "report_id": report.report_id,
            "report": report.model_dump(),
            "analysis": analysis
        }
    
    async def get_patient_summary(self, patient_id: str) -> dict:
        patient = await db.get_patient(patient_id)
        if not patient:
            return {"error": "Patient not found"}
        
        return {
            "patient": patient,
            "medications": [m.model_dump() for m in await db.get_medications(patient_id)],
            "allergies": [a.model_dump() for a in await db.get_allergies(patient_id)],
            "problems": [p.model_dump() for p in await db.get_problems(patient_id)],
            "recent_labs": [l.model_dump() for l in await db.get_labs(patient_id, 30)],
            "recent_imaging": [i.model_dump() for i in await db.get_imaging(patient_id, 180)],
            "recent_encounters": [e.model_dump() for e in await db.get_encounters(patient_id, 90)],
        }
    
    async def search_knowledge_base(self, query: str, top_k: int = 3) -> dict:
        chunks = search_knowledge(query, top_k)
        return {
            "query": query,
            "results": [c.model_dump() for c in chunks]
        }

    def get_session(self, session_id: str) -> dict | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "patient_id": session.patient_id,
            "status": session.status,
            "clarification_count": session.clarification_count,
            "has_ticket": session.ticket is not None,
            "ticket_status": session.ticket.status if session.ticket else None,
            "ticket": session.ticket.model_dump() if session.ticket else None,
            "created_at": session.created_at.isoformat(),
            "audit_log": session.audit_log,
        }
    
    def list_sessions(self) -> dict:
        sessions_list = []
        for session in self.sessions.values():
            sessions_list.append({
                "session_id": session.session_id,
                "patient_id": session.patient_id,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
            })
        return {"sessions": sessions_list, "total": len(sessions_list)}
    
    async def _build_context(self, intake: IntakeData, patient_id: str | None) -> ContextPack:
        context = ContextPack(
            context_id=f"CTX-{uuid.uuid4().hex[:8]}",
            patient_id=patient_id,
            intake=intake,
        )
        return context
    
    def _get_or_create_session(self, session_id: str | None, patient_id: str | None) -> Session:
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        
        new_id = session_id or f"SES-{uuid.uuid4().hex[:8]}"
        session = Session(session_id=new_id, patient_id=patient_id)
        self.sessions[new_id] = session
        return session

    async def _emergency_response(self, session: Session, red_flags: list[str], content: str = "") -> dict:
        session.status = "escalated"
        session.log("emergency_escalation", {"red_flags": red_flags})

        # Run intake so the emergency ticket has context
        intake = None
        if content:
            try:
                intake = await self.intake.process(content, session.patient_id)
                session.log("emergency_intake", {"chief_complaint": intake.chief_complaint})
            except Exception:
                pass

        # create emergency ticket with whatever info we have 
        ticket = Ticket(
            ticket_id=f"TKT-{uuid.uuid4().hex[:8]}",
            patient_id=session.patient_id,
            intent=Intent.SYMPTOMS,
            risk_level=RiskLevel.CRITICAL,
            red_flags=red_flags,
            destination=TriageDestination.EMERGENCY,
            urgency="immediate",
            case_card=CaseCard(
                case_id=f"CC-{uuid.uuid4().hex[:8]}",
                context_id=f"CTX-{uuid.uuid4().hex[:8]}",
                patient_id=session.patient_id,
                summary=intake.chief_complaint if intake else content[:200],
                chief_complaint=intake.chief_complaint if intake else content[:200],
                relevant_history="Emergency — not assessed",
                triage=TriageRecommendation(
                    destination=TriageDestination.EMERGENCY,
                    urgency="immediate",
                    reasoning="Emergency red flags detected",
                    confidence=1.0,
                ),
                ready_for_routing=True,
            ),
            status="escalated",
        )
        session.ticket = ticket
        session.log("ticket_created", {"ticket_id": ticket.ticket_id, "destination": "emergency"})

        return self._response(session,
            status="emergency",
            ticket_id=ticket.ticket_id,
            response=get_emergency_response(),
            red_flags=red_flags,
            chief_complaint=intake.chief_complaint if intake else None,
            next_action="immediate_human_contact",
            hint="Patient flagged for emergency. Review via GET /v1/session/{session_id}",
        )

    async def _request_clarification(self, session: Session, intake: IntakeData) -> dict:
        if session.clarification_count >= MAX_CLARIFICATION_ROUNDS:
            session.log("clarification_circuit_breaker", {
                "rounds_completed": session.clarification_count,
            })
            route = session.route_decision
            if route:
                return await self._generate_ticket(session, intake, route)

        critical_missing = [
            m for m in (intake.missing_info or [])
            if m not in ["medications", "allergies", "medical_history"]
        ]
        if not critical_missing:
            critical_missing = ["symptom details"]

        questions = await self.clarifier.generate_questions(
            intake.chief_complaint,
            critical_missing,
            session.route_decision.red_flags if session.route_decision else [],
            has_ehr=bool(session.patient_id and await db.get_patient(session.patient_id)),
            patient_id=session.patient_id,
            tool_executor=self._execute_tool,
        )
        session.log("clarification_requested", {"question_count": len(questions)})

        return self._response(session,
            status="needs_clarification",
            questions=questions,
            intake_summary=intake.chief_complaint,
            clarification_round=session.clarification_count + 1,
            max_rounds=MAX_CLARIFICATION_ROUNDS,
            next_action="await_response",
        )

    async def _generate_ticket(self, session: Session, intake: IntakeData, route: RouterDecision) -> dict:
        context = session.context
        if not context:
            context = await self._build_context(intake, session.patient_id)
            session.context = context

        case_card = await self.casecard.generate(
            context, route.risk_level, route.red_flags,
            tool_executor=self._execute_tool,
        )
        session.log("casecard_generated", {"ready": case_card.ready_for_routing})
        
        print(f"[DEBUG] CaseCard: ready={case_card.ready_for_routing}, gaps={case_card.information_gaps}")
        
        # Case card says more info needed — try clarification (with circuit breaker)
        if not case_card.ready_for_routing and case_card.information_gaps:
            if session.clarification_count < MAX_CLARIFICATION_ROUNDS:
                questions = await self.clarifier.generate_questions(
                    intake.chief_complaint, case_card.information_gaps, route.red_flags,
                    has_ehr=bool(session.patient_id and await db.get_patient(session.patient_id)),
                    patient_id=session.patient_id,
                    tool_executor=self._execute_tool,
                )
                return self._response(session,
                    status="needs_clarification",
                    questions=questions,
                    information_gaps=case_card.information_gaps,
                    clarification_round=session.clarification_count + 1,
                    max_rounds=MAX_CLARIFICATION_ROUNDS,
                    next_action="await_response",
                )
            else:
                session.log("clarification_circuit_breaker", {
                    "gaps": case_card.information_gaps,
                })
                # Proceed with incomplete info
        
        ticket = Ticket(
            ticket_id=f"TKT-{uuid.uuid4().hex[:8]}",
            patient_id=session.patient_id,
            intent=route.intent,
            risk_level=route.risk_level,
            red_flags=route.red_flags,
            destination=case_card.triage.destination,
            urgency=case_card.triage.urgency,
            case_card=case_card,
        )
        session.ticket = ticket
        session.log("ticket_created", {"ticket_id": ticket.ticket_id, "destination": ticket.destination.value})
        
        qa_result = await self.qa_gate.validate(case_card.model_dump_json(), route.risk_level)
        session.log("qa_validation", {"passed": qa_result.passed})

        return self._response(session,
            status="ready_for_review",
            ticket_id=ticket.ticket_id,
            ticket=ticket.model_dump(),
            qa_result=qa_result.model_dump(),
            next_action="await_staff_review",
        )