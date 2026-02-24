import json
import re
import uuid
from dataclasses import dataclass

from typing import Callable

from llm_client import LLMClient, LLMConnectionError
from config import config
from models import (
    RouterDecision, RouterOutput, IntakeData, ContextPack, CaseCard, PatientReply,
    TriageRecommendation, TriageDestination, RiskLevel, Intent,
    LabReport, ImagingReport, QAResult
)
from prompts import (
    ROUTER_SYSTEM, INTAKE_SYSTEM, CASECARD_SYSTEM, EXPLAIN_SYSTEM,
    LAB_ANALYSIS_SYSTEM, IMAGING_ANALYSIS_SYSTEM, CLARIFIER_SYSTEM,
    QA_SYSTEM, EMERGENCY_RESPONSE_ZH
)

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search clinical knowledge base for SOPs, protocols, and patient education materials. Use when you need clinical guidelines or reference information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. '胸痛評估' or '糖尿病用藥'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_patient_ehr",
            "description": "Query patient EHR data. Use when you need the patient's medical history, medications, allergies, lab results, or imaging reports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID, e.g. 'P001'"
                    },
                    "section": {
                        "type": "string",
                        "enum": ["summary", "problems", "medications", "allergies", "labs", "imaging", "encounters", "all"],
                        "description": "Which EHR section to retrieve. Use 'all' for complete patient record."
                    }
                },
                "required": ["patient_id", "section"]
            }
        }
    },
]

def extract_json(text: str, default=None):
    if not text:
        return default

    text = re.sub(r"<unused\d+>[\s\S]*?<unused\d+>", "", text)

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        text = code_block.group(1)
    else:
        text = re.sub(r"<[^>]+>", "", text)

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue

    return default

CRITICAL_RED_FLAGS = {
    "chest_pain", "stroke_symptoms", "breathing_difficulty",
    "severe_bleeding", "altered_consciousness", "suicidal_ideation",
    "severe_allergic_reaction"
}

RED_FLAG_KEYWORDS = {
    "chest_pain": ["胸痛", "胸悶", "心絞痛", "胸口壓迫", "胸口緊"],
    "stroke_symptoms": ["中風", "半邊無力", "口齒不清", "臉歪", "突然頭痛", "半身麻"],
    "breathing_difficulty": ["呼吸困難", "喘不過氣", "無法呼吸", "窒息", "喘"],
    "severe_bleeding": ["大量出血", "止不住血", "吐血", "血便", "咳血"],
    "altered_consciousness": ["意識不清", "昏迷", "失去意識", "叫不醒", "暈倒"],
    "severe_allergic_reaction": ["過敏性休克", "嘴唇腫", "舌頭腫", "全身紅疹"],
    "suicidal_ideation": ["想死", "不想活", "自殺", "結束生命", "活不下去"],
    "severe_pain": ["劇烈疼痛", "痛到無法忍受", "劇痛"],
    "high_fever": ["高燒", "發燒超過39", "燒不退", "高熱"],
}

@dataclass
class AgentClients:
    router: LLMClient
    medical: LLMClient

def create_clients() -> AgentClients:
    medical = LLMClient(config.medical_llm)
    return AgentClients(
        router=medical,
        medical=medical,
    )

class RouterAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    def quick_screen(self, text: str) -> list[str]:
        text_lower = text.lower()
        detected = []
        for flag, keywords in RED_FLAG_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected.append(flag)
        return detected

    async def route(self, content: str, patient_context: str | None = None) -> RouterDecision:
        quick_flags = self.quick_screen(content)

        if any(f in CRITICAL_RED_FLAGS for f in quick_flags):
            return RouterDecision(
                intent=Intent.SYMPTOMS,
                risk_level=RiskLevel.CRITICAL,
                red_flags=quick_flags,
                next_action="escalate_now",
                reasoning="red_flag",
            )

        prompt = f'"{content}"'

        output = await self.client.generate_structured(
            prompt, RouterOutput, ROUTER_SYSTEM,
            temperature=0.0, max_tokens=64,
        )
        print(f"[DEBUG] Router: intent={output.intent}, risk={output.risk_level}, action={output.next_action}")

        decision = RouterDecision(
            intent=Intent(output.intent),
            risk_level=RiskLevel(output.risk_level),
            red_flags=quick_flags,
            next_action=output.next_action,
            reasoning="structured_output",
        )

        if quick_flags:
            decision.risk_level = RiskLevel.CRITICAL
            decision.next_action = "escalate_now"

        return decision


class IntakeAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def process(self, content: str, patient_id: str | None = None) -> IntakeData:
        try:
            raw = await self.client.generate(
                f"Extract information from this patient message:\n\n{content}",
                INTAKE_SYSTEM,
            )
            print(f"[DEBUG] Intake LLM raw: {raw[:200] if raw else 'empty'}...")
            parsed = extract_json(raw, None)
            if isinstance(parsed, dict) and "chief_complaint" in parsed:
                parsed.setdefault("intake_id", str(uuid.uuid4())[:8])
                parsed["patient_id"] = patient_id
                if "symptoms" in parsed and isinstance(parsed["symptoms"], list):
                    normalized = []
                    for s in parsed["symptoms"]:
                        if isinstance(s, str):
                            normalized.append({"description": s})
                        elif isinstance(s, dict):
                            if "description" not in s and "symptom" in s:
                                s["description"] = s.pop("symptom")
                            elif "description" not in s:
                                s["description"] = next(
                                    (v for v in s.values() if isinstance(v, str)), "unknown"
                                )
                            if "severity" in s and s["severity"] is not None:
                                sev = s["severity"]
                                parsed_sev = None
                                try:
                                    parsed_sev = int(sev)
                                except (ValueError, TypeError):
                                    m = re.search(r"(\d+)", str(sev))
                                    if m:
                                        num = int(m.group(1))
                                        if 1 <= num <= 10:
                                            parsed_sev = num
                                if parsed_sev is not None and 1 <= parsed_sev <= 10:
                                    s["severity"] = parsed_sev
                                else:
                                    if not s.get("character"):
                                        s["character"] = str(sev)
                                    s["severity"] = None
                            normalized.append(s)
                    parsed["symptoms"] = normalized
                data = IntakeData.model_validate(parsed)
                print(f"[DEBUG] Intake LLM parsed: chief_complaint={data.chief_complaint}")
                return data
            raise ValueError(f"LLM output missing chief_complaint: {parsed}")
        except LLMConnectionError:
            raise
        except Exception as e:
            print(f"[DEBUG] Intake parse error: {e}")

        return IntakeData(
            intake_id=str(uuid.uuid4())[:8],
            patient_id=patient_id,
            chief_complaint=self._extract_complaint(content),
            missing_info=[]
        )

    def _extract_complaint(self, content: str) -> str:
        content_lower = content.lower()
        if any(k in content_lower for k in ["報告", "結果", "抽血", "檢驗", "lab", "result", "test"]):
            return "詢問檢驗報告"
        if any(k in content_lower for k in ["藥", "medication", "drug", "處方"]):
            return "詢問藥物"
        if any(k in content_lower for k in ["預約", "appointment", "掛號"]):
            return "預約相關"
        return content[:200]


class CaseCardAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def generate(
        self,
        context: ContextPack,
        risk_level: RiskLevel,
        red_flags: list[str],
        tool_executor: Callable | None = None,
    ) -> CaseCard:
        prompt = self._build_prompt(context, risk_level, red_flags)

        try:
            raw = await self.client.generate(
                prompt, CASECARD_SYSTEM,
                tools=AGENT_TOOLS if tool_executor else None,
                tool_executor=tool_executor,
            )
            data = extract_json(raw, {})
            if not isinstance(data, dict):
                data = {}
        except LLMConnectionError:
            raise
        except Exception:
            data = {}

        case_id = str(uuid.uuid4())[:8]

        info_gaps = data.get("information_gaps", [])
        is_simple_query = context.intake and any(k in context.intake.chief_complaint for k in ["詢問", "報告", "結果", "藥物", "預約"])

        def _as_str(val, default=""):
            if val is None:
                return default
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                parts = []
                for v in val:
                    parts.append(_as_str(v, ""))
                return "; ".join(p for p in parts if p)
            if isinstance(val, dict):
                parts = []
                for k, v in val.items():
                    v_str = _as_str(v, "")
                    if v_str:
                        parts.append(f"{k}: {v_str}")
                return "; ".join(parts)
            return str(val)

        return CaseCard(
            case_id=case_id,
            context_id=context.context_id,
            patient_id=context.patient_id,
            summary=_as_str(data.get("summary"), f"Patient with {context.intake.chief_complaint if context.intake else 'unknown complaint'}"),
            chief_complaint=_as_str(data.get("chief_complaint"), context.intake.chief_complaint if context.intake else ""),
            relevant_history=_as_str(data.get("relevant_history")),
            current_meds_summary=_as_str(data.get("current_meds_summary"), None),
            recent_labs_summary=_as_str(data.get("recent_labs_summary"), None),
            recent_imaging_summary=_as_str(data.get("recent_imaging_summary"), None),
            pertinent_positives=data.get("pertinent_positives", []),
            pertinent_negatives=data.get("pertinent_negatives", []),
            information_gaps=[] if is_simple_query else info_gaps,
            triage=self._get_triage(data.get("triage"), risk_level, red_flags),
            ready_for_routing=data.get("ready_for_routing", True if is_simple_query else len(info_gaps) == 0),
        )

    def _build_prompt(self, ctx: ContextPack, risk: RiskLevel, flags: list[str]) -> str:
        parts = [f"Risk Level: {risk.value}", f"Red Flags: {flags}"]

        if ctx.intake:
            parts.append(f"\nChief Complaint: {ctx.intake.chief_complaint}")
            if ctx.intake.chief_complaint_duration:
                parts.append(f"Duration: {ctx.intake.chief_complaint_duration}")
            if ctx.intake.symptoms:
                parts.append(f"Symptoms: {[s.model_dump() for s in ctx.intake.symptoms]}")

        if ctx.patient_id:
            parts.append(f"\nPatient ID: {ctx.patient_id}")
        else:
            parts.append("\nNo patient ID available.")

        return "\n".join(parts)

    def _get_triage(self, triage_data: dict | None, risk: RiskLevel, flags: list[str]) -> TriageRecommendation:
        if triage_data:
            try:
                return TriageRecommendation.model_validate(triage_data)
            except Exception:
                pass

        has_critical = any(f in CRITICAL_RED_FLAGS for f in flags)
        flag_note = f" Red flags: {', '.join(flags)}." if flags else ""

        if risk == RiskLevel.CRITICAL or has_critical:
            return TriageRecommendation(destination=TriageDestination.EMERGENCY, urgency="immediate",
                                        reasoning=f"Critical risk.{flag_note}", confidence=0.95)
        if risk == RiskLevel.HIGH:
            return TriageRecommendation(destination=TriageDestination.PHYSICIAN, urgency="same_day",
                                        reasoning=f"High risk.{flag_note}", confidence=0.85)
        if risk == RiskLevel.MEDIUM:
            if flags:
                return TriageRecommendation(destination=TriageDestination.PHYSICIAN, urgency="next_available",
                                            reasoning=f"Medium risk with flags.{flag_note}", confidence=0.75)
            return TriageRecommendation(destination=TriageDestination.NURSE, urgency="next_available",
                                        reasoning="Medium risk.", confidence=0.7)
        return TriageRecommendation(destination=TriageDestination.FRONT_DESK, urgency="routine",
                                    reasoning="Low risk.", confidence=0.7)


class ExplainAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def generate_reply(
        self,
        case_card: CaseCard,
        risk_level: RiskLevel,
        physician_notes: str | None = None,
        tool_executor: Callable | None = None,
    ) -> PatientReply:
        prompt = f"Case Summary: {case_card.summary}\nChief Complaint: {case_card.chief_complaint}\nRisk Level: {risk_level.value}"
        if case_card.relevant_history:
            prompt += f"\nRelevant History: {case_card.relevant_history}"
        if case_card.current_meds_summary:
            prompt += f"\nCurrent Medications: {case_card.current_meds_summary}"
        if physician_notes:
            prompt += f"\nPhysician Notes: {physician_notes}"
        if case_card.patient_id:
            prompt += f"\nPatient ID: {case_card.patient_id} (use get_patient_ehr tool to retrieve relevant EHR data)"

        try:
            raw = await self.client.generate(
                prompt, EXPLAIN_SYSTEM,
                tools=AGENT_TOOLS if tool_executor else None,
                tool_executor=tool_executor,
            )
            parsed = extract_json(raw, None)
            if isinstance(parsed, dict):
                parsed.setdefault("draft_id", str(uuid.uuid4())[:8])
                data = PatientReply.model_validate(parsed)
            else:
                raise ValueError("No valid JSON in response")
        except LLMConnectionError:
            raise
        except Exception:
            data = PatientReply(
                draft_id=str(uuid.uuid4())[:8],
                greeting="您好，",
                acknowledgment="感謝您的來訊，我了解您的擔憂。",
                understanding=f"您提到{case_card.chief_complaint}的問題。",
                response="我們已收到您的訊息，醫療團隊會盡快回覆您。",
                action_items=["請保持聯繫方式暢通"],
                warning_signs=["如有緊急狀況請撥打119"],
                closing="祝您早日康復。"
            )

        data.draft_id = data.draft_id or str(uuid.uuid4())[:8]

        if risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            data.emergency_info = "緊急狀況請撥打119或立即前往急診"
            if not data.warning_signs:
                data.warning_signs = ["症狀惡化", "出現新的嚴重症狀", "意識改變"]

        return data


class LabAnalysisAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def analyze(self, lab_report: LabReport) -> dict:
        prompt = f"Lab Report ID: {lab_report.report_id}\nCollected: {lab_report.collected_date}\n\nResults:\n"
        for r in lab_report.results:
            flag_str = f" [{r.flag}]" if r.flag else ""
            prompt += f"- {r.test_name}: {r.value} {r.unit or ''} (ref: {r.reference_range or 'N/A'}){flag_str}\n"

        if lab_report.critical_values:
            prompt += f"\nCritical Values: {lab_report.critical_values}"

        abnormal = [{"test": r.test_name, "value": f"{r.value} {r.unit or ''}", "interpretation": r.flag}
                    for r in lab_report.results if r.flag and r.flag != "normal"]

        fallback = {
            "summary": f"檢驗報告分析：共{len(lab_report.results)}項檢驗，{len(abnormal)}項異常",
            "abnormal_values": abnormal,
            "critical_values": lab_report.critical_values or [],
            "recommendations": ["請與醫師討論檢驗結果"]
        }

        try:
            raw = await self.client.generate(prompt, LAB_ANALYSIS_SYSTEM)
            result = extract_json(raw, None)
            if isinstance(result, dict) and "summary" in result:
                return result
        except LLMConnectionError:
            raise
        except Exception:
            pass

        return fallback


class ImagingAnalysisAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def analyze(self, imaging_report: ImagingReport) -> dict:
        prompt = f"Study: {imaging_report.study_type}\nBody Part: {imaging_report.body_part}\nDate: {imaging_report.study_date}\n"
        if imaging_report.indication:
            prompt += f"Indication: {imaging_report.indication}\n"
        prompt += "\nFindings:\n"
        for f in imaging_report.findings:
            prompt += f"- {f.location}: {f.finding} ({f.severity or 'N/A'})\n"
        prompt += f"\nImpression: {imaging_report.impression}"
        if imaging_report.critical_findings:
            prompt += f"\nCritical Findings: {imaging_report.critical_findings}"

        fallback = {
            "study_summary": f"{imaging_report.study_type} - {imaging_report.body_part}",
            "key_findings": [f.finding for f in imaging_report.findings],
            "critical_findings": imaging_report.critical_findings or [],
            "recommendations": ["建議臨床相關性評估"]
        }

        try:
            raw = await self.client.generate(prompt, IMAGING_ANALYSIS_SYSTEM)
            result = extract_json(raw, None)
            if isinstance(result, dict) and "study_summary" in result:
                return result
        except LLMConnectionError:
            raise
        except Exception:
            pass

        return fallback


class ClarifierAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def generate_questions(
        self,
        chief_complaint: str,
        missing_info: list[str],
        red_flags: list[str] | None = None,
        has_ehr: bool = False,
        patient_id: str | None = None,
        tool_executor: Callable | None = None,
    ) -> list[str]:
        prompt = f"Chief Complaint: {chief_complaint}\nMissing Information: {missing_info}"
        if red_flags:
            prompt += f"\nPotential Red Flags to Screen: {red_flags}"
        if has_ehr and patient_id:
            prompt += f"\nPatient ID: {patient_id} — EHR data is available. DO NOT ask about medications, allergies, or medical history. Focus only on current symptoms."
        elif has_ehr:
            prompt += "\nNote: Patient has EHR data available. DO NOT ask about medications, allergies, or medical history - focus only on current symptoms."

        fallback = [
            "請問症狀是什麼時候開始的？",
            "疼痛或不適的程度，1-10分您會打幾分？",
            "有沒有什麼情況會讓症狀加重或減輕？",
        ]

        try:
            raw = await self.client.generate(
                prompt, CLARIFIER_SYSTEM,
                tools=AGENT_TOOLS if tool_executor else None,
                tool_executor=tool_executor,
            )
            result = extract_json(raw, fallback)
            if isinstance(result, list) and len(result) > 0:
                return result[:6]
        except LLMConnectionError:
            raise
        except Exception:
            pass

        return fallback


class QAGateAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    async def validate(self, content: str, risk_level: RiskLevel) -> QAResult:
        prompt = (
            f"Risk Level: {risk_level.value}\n\n"
            f"Content to Validate:\n{content}\n\n"
            "Evaluate the content above and return your judgment as JSON.\n"
            "Be practical — minor phrasing issues are suggestions, not failures.\n"
            "Only fail for: explicit diagnoses, missing safety warnings on critical/high risk, or harmful content."
        )

        try:
            raw = await self.client.generate(prompt, QA_SYSTEM)
            data = extract_json(raw, {})
            if not isinstance(data, dict):
                data = {}
        except LLMConnectionError:
            raise
        except Exception:
            data = {}

        checks = data.get("checks", {})
        issues = data.get("issues", [])
        passed = data.get("passed", all(checks.values()) and len(issues) == 0) if checks else False

        return QAResult(
            passed=passed,
            checks=checks,
            issues=issues,
            suggestions=suggestions,
        )


def get_emergency_response() -> str:
    return EMERGENCY_RESPONSE_ZH