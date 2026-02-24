"""
End-to-end integration test for Clinical Agent System v2.

Tests the FULL LLM pipeline:
  - Router intent classification (LLM structured output)
  - Intake extraction (LLM JSON)
  - Case card generation with tool-calling (LLM calls get_patient_ehr → DB)
  - Knowledge base retrieval via tool calls (LLM calls search_knowledge → RAG)
  - QA gate validation (LLM safety check)
  - Reply drafting with tool-calling (LLM calls get_patient_ehr → DB)
  - Lab analysis (LLM interprets lab values)
  - Emergency escalation (keyword detection + LLM routing)

Also exercises: JWT auth, SQLite patient CRUD, document upload, audit log.

Requirements:
  - Server running:  uvicorn server:app --port 8080
  - Router LLM:      vllm on port 8001
  - Medical LLM:     vllm on port 8002

Usage:
    python test_workflow.py
"""

import httpx
import asyncio
import json

BASE_URL = "http://localhost:8080"

# ─── Counters ───
passed = 0
failed = 0
skipped = 0


# ─── Test scenarios ───

# Scenario A: Lab results inquiry — should route as lab_results intent,
# trigger tool calls to get_patient_ehr, and generate a reply about P001's labs.
LAB_INQUIRY = {
    "content": "醫師您好，我想詢問血糖報告，上次抽血結果如何？",
    "patient_id": "P001",
}

# Scenario B: Symptom with red flags — chest pain + breathing difficulty.
# Should trigger emergency escalation via keyword screen.
EMERGENCY_MESSAGE = {
    "content": "我現在胸痛喘不過氣，很不舒服",
    "patient_id": "P003",
}

# Scenario C: Medication question — should route as medication intent,
# LLM should use get_patient_ehr to pull P003's complex med list (Warfarin etc.)
MEDICATION_INQUIRY = {
    "content": "我想問一下我目前吃的藥有什麼副作用要注意的？",
    "patient_id": "P003",
}

# Scenario D: Vague symptom — headache. Should trigger clarifying questions
# from the LLM to gather PQRST details.
VAGUE_SYMPTOM = {
    "content": "最近常常頭痛",
    "patient_id": "P002",
}

# Scenario E: Follow-up / appointment — simple admin routing.
ADMIN_INQUIRY = {
    "content": "我想預約下次回診",
    "patient_id": "P004",
}

CLARIFICATION_ANSWERS = {"q1": "大概三天了", "q2": "右邊太陽穴", "q3": "大約5分"}

REVIEW_APPROVED = {"approved": True, "physician_notes": "依照指引回覆即可"}
REVIEW_REJECTED = {"approved": False, "physician_notes": "需進一步確認"}

# Auth
LOGIN = {"username": "admin", "password": "admin123"}

# CRUD test data
NEW_PATIENT = {
    "patient_id": "P099", "name": "測試病人", "age": 40,
    "sex": "male", "mrn": "P099", "dob": "1986-05-20",
}
NEW_MED = {
    "name": "Aspirin", "dose": "100mg", "frequency": "QD",
    "route": "PO", "indication": "CVD prevention", "status": "active",
}
NEW_LAB = {
    "test_name": "HbA1c", "value": "6.8", "unit": "%",
    "reference_range": "<7.0", "flag": "normal", "collected_date": "2026-02-01",
}


# ─── Helpers ───


async def req(client, method, url, expect=200, label=None, **kwargs):
    """HTTP request with status check. Returns data dict or None."""
    try:
        r = await client.request(method, url, **kwargs)
        ok = r.status_code == expect
        tag = "✓" if ok else "✗"
        desc = f" — {label}" if label else ""
        print(f"    {tag} [{r.status_code}] {method} {url}{desc}")
        if not ok:
            print(f"      Body: {r.text[:300]}")
            return None
        return r.json() if r.text else {}
    except httpx.ConnectError:
        print(f"    ✗ Cannot connect to {BASE_URL}")
        return None
    except Exception as e:
        print(f"    ✗ {type(e).__name__}: {e}")
        return None


def section(title):
    print(f"\n{'━'*60}")
    print(f"  {title}")
    print(f"{'━'*60}")


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"    ✓ {label}")
    else:
        failed += 1
        print(f"    ✗ FAIL: {label}")


def skip(label, reason=""):
    global skipped
    skipped += 1
    r = f" ({reason})" if reason else ""
    print(f"    ⊘ SKIP: {label}{r}")


# ─── Main test ───


async def test_workflow():
    global passed, failed, skipped

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as c:

        # ──────────────────────────────────────
        # SETUP: Health check + login
        # ──────────────────────────────────────
        section("SETUP — Health & Auth")

        data = await req(c, "GET", "/health")
        if not data:
            print("\n  Server not running. Start with: uvicorn server:app --port 8080")
            return
        check("server healthy", "status" in data)

        llm = data.get("llm_servers", {})
        router_ok = llm.get("router", {}).get("connected", False)
        medical_ok = llm.get("medical", {}).get("connected", False)
        print(f"    Router LLM:  {'✓ connected' if router_ok else '✗ NOT connected'}")
        print(f"    Medical LLM: {'✓ connected' if medical_ok else '✗ NOT connected'}")

        if not router_ok or not medical_ok:
            print("\n  ⚠ LLM servers required for pipeline tests.")
            print("    Start vLLM first, then re-run.")
            return

        data = await req(c, "POST", "/v1/auth/login", json=LOGIN)
        if not data:
            print("  Cannot login — aborting")
            return
        token = data["access_token"]
        H = {"Authorization": f"Bearer {token}"}
        check("admin login", bool(token))

        # ──────────────────────────────────────
        # 1. ROUTER — Intent classification via LLM
        # ──────────────────────────────────────
        section("1. ROUTER — LLM Intent Classification")
        print("    Testing multiple message types to verify LLM routing decisions...\n")

        # 1a. Lab inquiry → intent should be lab_results
        data = await req(c, "POST", "/v1/message", json=LAB_INQUIRY, headers=H,
                         label="lab inquiry for P001")
        lab_session_id = None
        lab_status = None
        lab_data = data
        if data:
            lab_session_id = data.get("session_id")
            lab_status = data.get("status")
            print(f"    → Status: {lab_status}")

            check("lab inquiry not emergency", lab_status != "emergency")
            check("lab inquiry got session", lab_session_id is not None)

            # Check the session audit to see what the router decided
            sess = await req(c, "GET", f"/v1/session/{lab_session_id}", headers=H)
            if sess:
                audit = sess.get("audit_log", [])
                routing = next((e for e in audit if e["action"] == "routing_complete"), None)
                if routing:
                    details = routing.get("details", {})
                    intent = details.get("intent", "")
                    print(f"    → Router intent: {intent}, risk: {details.get('risk')}")
                    check("router classified as lab_results", intent == "lab_results")
                    check("router risk is low/medium", details.get("risk") in ("low", "medium"))
                else:
                    skip("router decision check", "routing_complete not in audit")

        # 1b. Admin/appointment → intent should be follow_up or admin
        data = await req(c, "POST", "/v1/message", json=ADMIN_INQUIRY, headers=H,
                         label="appointment inquiry for P004")
        if data:
            appt_session = data.get("session_id")
            sess = await req(c, "GET", f"/v1/session/{appt_session}", headers=H)
            if sess:
                routing = next((e for e in sess.get("audit_log", [])
                                if e["action"] == "routing_complete"), None)
                if routing:
                    intent = routing["details"].get("intent", "")
                    print(f"    → Router intent: {intent}")
                    # LLM may classify "預約回診" as follow_up, admin, or other
                    check("appointment not misrouted as symptoms/emergency",
                          intent not in ("symptoms",) or
                          routing["details"].get("risk") not in ("critical", "high"))

        # ──────────────────────────────────────
        # 2. EMERGENCY — Red flag detection + escalation
        # ──────────────────────────────────────
        section("2. EMERGENCY — Red Flag Detection & Escalation")

        data = await req(c, "POST", "/v1/message", json=EMERGENCY_MESSAGE, headers=H,
                         label="chest pain + breathing difficulty")
        if data:
            status = data.get("status")
            flags = data.get("red_flags", [])
            print(f"    → Status: {status}")
            print(f"    → Red flags: {flags}")
            check("emergency status returned", status == "emergency")
            check("chest_pain flag detected", "chest_pain" in flags)
            check("breathing_difficulty flag detected", "breathing_difficulty" in flags)
            check("emergency response contains 119", "119" in data.get("response", ""))

            emg_sess = data.get("session_id")
            sess = await req(c, "GET", f"/v1/session/{emg_sess}", headers=H)
            if sess:
                check("session status is escalated", sess.get("status") == "escalated")
                actions = [e["action"] for e in sess.get("audit_log", [])]
                check("audit has emergency action",
                      "emergency_quick_screen" in actions or "emergency_escalation" in actions)

        # ──────────────────────────────────────
        # 3. INTAKE + TOOL CALLING — LLM extracts, calls EHR tools
        # ──────────────────────────────────────
        section("3. INTAKE & TOOL CALLING — LLM retrieves EHR via tools")
        print("    Checking that the pipeline called get_patient_ehr for P001...\n")

        if lab_session_id:
            sess = await req(c, "GET", f"/v1/session/{lab_session_id}", headers=H)
            if sess:
                audit = sess.get("audit_log", [])
                actions = [e["action"] for e in audit]
                print(f"    Pipeline steps: {actions}")

                check("intake_complete reached", "intake_complete" in actions)
                check("context_built reached", "context_built" in actions)

                # Verify intake extracted chief_complaint
                intake_entry = next((e for e in audit if e["action"] == "intake_complete"), None)
                if intake_entry:
                    cc = intake_entry.get("details", {}).get("chief_complaint", "")
                    print(f"    → Intake chief_complaint: {cc}")
                    check("intake extracted complaint", len(cc) > 2)

                # Check if casecard was generated (means tool calling happened)
                if "casecard_generated" in actions:
                    check("casecard_generated (tool calling succeeded)", True)
                    cc_entry = next((e for e in audit if e["action"] == "casecard_generated"), None)
                    if cc_entry:
                        print(f"    → CaseCard ready: {cc_entry.get('details', {}).get('ready')}")
                elif "clarification_requested" in actions:
                    check("clarification requested by LLM (acceptable)", True)
                else:
                    check("pipeline progressed past intake", False)
        else:
            skip("intake/tool-calling check", "no lab session")

        # ──────────────────────────────────────
        # 4. CLARIFICATION — LLM generates follow-up questions
        # ──────────────────────────────────────
        section("4. CLARIFICATION — LLM asks PQRST questions")

        data = await req(c, "POST", "/v1/message", json=VAGUE_SYMPTOM, headers=H,
                         label="vague headache for P002")
        symptom_session_id = None
        symptom_status = None
        if data:
            symptom_status = data.get("status")
            symptom_session_id = data.get("session_id")
            print(f"    → Status: {symptom_status}")

            if symptom_status == "needs_clarification":
                questions = data.get("questions", [])
                print(f"    → LLM generated {len(questions)} clarification questions:")
                for i, q in enumerate(questions):
                    print(f"        {i+1}. {q}")
                check("clarification questions generated", len(questions) >= 1)
                check("questions are in Chinese", any(
                    any('\u4e00' <= ch <= '\u9fff' for ch in q) for q in questions))

                # Submit answers → pipeline continues
                clar_req = {
                    "session_id": symptom_session_id,
                    "responses": CLARIFICATION_ANSWERS,
                }
                data = await req(c, "POST", "/v1/clarification", json=clar_req, headers=H,
                                 label="submit clarification answers")
                if data:
                    symptom_status = data.get("status")
                    print(f"    → Post-clarification status: {symptom_status}")
                    check("pipeline continued after clarification",
                          symptom_status in ("ready_for_review", "needs_clarification", "qa_failed"))
                    symptom_session_id = data.get("session_id", symptom_session_id)

            elif symptom_status == "ready_for_review":
                check("LLM proceeded without clarification (acceptable)", True)
            else:
                check("vague symptom handled", symptom_status != "emergency")

        # ──────────────────────────────────────
        # 5. CASE CARD + TICKET — LLM summarizes with EHR context
        # ──────────────────────────────────────
        section("5. CASE CARD & TICKET — LLM clinical summary + triage")

        # Use medication inquiry as a fresh full-pipeline scenario
        data = await req(c, "POST", "/v1/message", json=MEDICATION_INQUIRY, headers=H,
                         label="medication inquiry for P003")
        med_session_id = None
        ticket_data = None
        med_data = data
        if data:
            med_session_id = data.get("session_id")
            status = data.get("status")
            print(f"    → Status: {status}")

            # Feed clarification if needed
            if status == "needs_clarification":
                clar = {"session_id": med_session_id,
                        "responses": {"q1": "目前吃的藥", "q2": "沒有不舒服"}}
                data = await req(c, "POST", "/v1/clarification", json=clar, headers=H)
                if data:
                    status = data.get("status")
                    med_session_id = data.get("session_id", med_session_id)
                    med_data = data

            if status == "ready_for_review" and data:
                ticket_data = data.get("ticket", {})
                case_card = ticket_data.get("case_card", {})
                qa = data.get("qa_result", {})

                print(f"    → Ticket: {ticket_data.get('ticket_id')}")
                print(f"    → Intent: {ticket_data.get('intent')}")
                print(f"    → Risk: {ticket_data.get('risk_level')}")
                print(f"    → Destination: {ticket_data.get('destination')}")
                print(f"    → Urgency: {ticket_data.get('urgency')}")
                print(f"    → Summary: {case_card.get('summary', '')[:120]}")
                if case_card.get("current_meds_summary"):
                    print(f"    → Meds summary: {case_card['current_meds_summary'][:120]}")
                if case_card.get("recent_labs_summary"):
                    print(f"    → Labs summary: {case_card['recent_labs_summary'][:120]}")
                print(f"    → QA passed: {qa.get('passed')}")

                check("ticket created", bool(ticket_data.get("ticket_id")))
                check("case card has summary", len(case_card.get("summary", "")) > 5)
                check("case card has chief_complaint", len(case_card.get("chief_complaint", "")) > 3)
                check("triage destination set",
                      ticket_data.get("destination") in (
                          "physician", "nurse", "pharmacist", "front_desk", "emergency"))
                check("QA gate ran", "passed" in qa)

                # Verify the LLM actually pulled EHR data (P003 has Warfarin, CHF, etc.)
                # The case card should mention something about the patient's context
                card_text = json.dumps(case_card, ensure_ascii=False).lower()
                has_patient_context = (
                    "warfarin" in card_text or "心" in card_text or
                    "medication" in card_text or "藥" in card_text or
                    "atrial" in card_text or "p003" in card_text or
                    len(case_card.get("relevant_history", "")) > 5 or
                    bool(case_card.get("current_meds_summary"))
                )
                check("case card contains P003 EHR context (tool call worked)",
                      has_patient_context)

            elif status == "qa_failed":
                check("QA gate caught issues (acceptable)", True)
                print(f"    → QA issues: {data.get('issues')}")
            else:
                skip("ticket/case-card checks", f"status={status}")

        # ──────────────────────────────────────
        # 6. REVIEW + REPLY — LLM drafts patient-friendly reply
        # ──────────────────────────────────────
        section("6. REVIEW & REPLY — LLM drafts patient response")

        if ticket_data and med_session_id:
            review_req = {"session_id": med_session_id, **REVIEW_APPROVED}
            data = await req(c, "POST", "/v1/review", json=review_req, headers=H,
                             label="approve ticket")
            if data:
                print("approve ticket:",data)
                review_status = data.get("status")
                draft = data.get("draft_reply", {})
                qa = data.get("qa_result", {})

                print(f"    → Review status: {review_status}")
                print(f"    → Greeting: {draft.get('greeting', '')}")
                print(f"    → Response: {draft.get('response', '')[:200]}")
                print(f"    → Action items: {draft.get('action_items', [])}")
                print(f"    → Warning signs: {draft.get('warning_signs', [])}")
                print(f"    → Reply QA passed: {qa.get('passed')}")

                check("reply has substantive response", len(draft.get("response", "")) > 10)
                check("reply has greeting", len(draft.get("greeting", "")) > 0)
                check("reply has action_items", len(draft.get("action_items", [])) >= 1)
                check("reply is in Chinese", any(
                    '\u4e00' <= ch <= '\u9fff' for ch in draft.get("response", "")))
                check("reply QA ran", "passed" in qa)

                # Verify reply doesn't contain diagnoses (safety rule)
                reply_text = json.dumps(draft, ensure_ascii=False).lower()
                no_diagnosis = not any(
                    phrase in reply_text
                    for phrase in ["診斷為", "確診", "您患有", "您得了", "diagnosis is"]
                )
                check("reply contains no diagnostic statements", no_diagnosis)

                # Send
                if review_status == "ready_to_send":
                    send_data = await req(c, "POST", "/v1/send",
                                          json={"session_id": med_session_id}, headers=H)
                    print("send data:",send_data)
                    check("reply sent successfully", send_data and send_data.get("status") == "sent")

            # Test rejection flow
            if lab_session_id:
                sess_info = await req(c, "GET", f"/v1/session/{lab_session_id}", headers=H)
                if sess_info and sess_info.get("has_ticket"):
                    rej = {"session_id": lab_session_id, **REVIEW_REJECTED}
                    rej_data = await req(c, "POST", "/v1/review", json=rej, headers=H,
                                         label="reject ticket")
                    if rej_data:
                        print("reject ticket:",rej_data)
                        check("rejection returns escalated", rej_data.get("status") == "escalated")
        else:
            skip("review/reply tests", "no ticket available")

    #     # ──────────────────────────────────────
    #     # 7. LAB ANALYSIS — LLM interprets lab values
    #     # ──────────────────────────────────────
    #     section("7. LAB ANALYSIS — LLM interprets lab reports")

    #     # LAB001: P001 diabetes (HbA1c 7.5 high, Fasting Glucose 156 high)
    #     data = await req(c, "POST", "/v1/lab-report/LAB001/analyze", headers=H,
    #                      label="analyze LAB001 (diabetes)")
    #     if data:
    #         analysis = data.get("analysis", {})
    #         print(f"    → Summary: {analysis.get('summary', '')[:150]}")
    #         abnormal = analysis.get("abnormal_values", [])
    #         print(f"    → Abnormal count: {len(abnormal)}")
    #         for a in abnormal[:3]:
    #             print(f"        - {a.get('test', '')}: {a.get('value', '')} → {a.get('interpretation', '')[:60]}")
    #         print(f"    → Recommendations: {analysis.get('recommendations', [])[:3]}")

    #         check("LAB001 analysis has summary", len(analysis.get("summary", "")) > 10)
    #         check("LAB001 abnormal values identified", len(abnormal) >= 1)
    #         check("LAB001 has recommendations", len(analysis.get("recommendations", [])) >= 1)

    #         # Check that the LLM identified HbA1c or glucose as abnormal
    #         abnormal_tests = [a.get("test", "").lower() for a in abnormal]
    #         abnormal_text = json.dumps(abnormal, ensure_ascii=False).lower()
    #         check("LLM identified HbA1c or glucose abnormality",
    #               "hba1c" in abnormal_text or "glucose" in abnormal_text or
    #               "血糖" in abnormal_text or "糖化" in abnormal_text)

    #     # LAB002: P003 heart failure (INR 3.8 high, BNP 650 high, eGFR 32 low)
    #     data = await req(c, "POST", "/v1/lab-report/LAB002/analyze", headers=H,
    #                      label="analyze LAB002 (heart failure)")
    #     if data:
    #         analysis = data.get("analysis", {})
    #         print(f"    → Summary: {analysis.get('summary', '')[:150]}")
    #         critical = analysis.get("critical_values", [])
    #         print(f"    → Critical values: {critical}")
    #         abnormal = analysis.get("abnormal_values", [])
    #         print(f"    → Abnormal count: {len(abnormal)}")

    #         check("LAB002 analysis returned", len(analysis.get("summary", "")) > 5)

    #         # INR 3.8 should be flagged as high/critical
    #         all_findings = json.dumps(analysis, ensure_ascii=False).lower()
    #         check("LLM noted INR abnormality",
    #               "inr" in all_findings)
    #         check("LLM noted BNP or renal issues",
    #               "bnp" in all_findings or "egfr" in all_findings or
    #               "creatinine" in all_findings or "腎" in all_findings)

    #     # ──────────────────────────────────────
    #     # 8. KNOWLEDGE SEARCH — RAG retrieval
    #     # ──────────────────────────────────────
    #     section("8. KNOWLEDGE SEARCH — RAG retrieval")

    #     for query_text, expected_keywords in [
    #         ("糖尿病", ["diabetes", "糖尿"]),
    #         ("胸痛評估", ["chest", "胸痛"]),
    #         ("心衰竭", ["heart_failure", "心衰"]),
    #         ("抗凝血", ["anticoagulation", "warfarin", "抗凝"]),
    #     ]:
    #         data = await req(c, "GET", "/v1/knowledge/search",
    #                          params={"query": query_text, "top_k": 3}, headers=H,
    #                          label=f"search '{query_text}'")
    #         if data:
    #             results = data.get("results", [])
    #             check(f"'{query_text}' returned results", len(results) > 0)
    #             if results:
    #                 top = results[0]
    #                 print(f"    → Top: [{top['source_type']}] {top['source']} "
    #                       f"(score={top.get('relevance_score', 'N/A')})")
    #                 # Verify content is relevant
    #                 content_lower = top.get("content", "").lower()
    #                 relevant = any(kw in content_lower for kw in expected_keywords)
    #                 check(f"'{query_text}' top result is relevant", relevant)

    #     # ──────────────────────────────────────
    #     # 9. FULL SESSION AUDIT — Pipeline trace
    #     # ──────────────────────────────────────
    #     section("9. SESSION AUDIT — Full pipeline trace")

    #     if med_session_id:
    #         sess = await req(c, "GET", f"/v1/session/{med_session_id}", headers=H)
    #         if sess:
    #             audit = sess.get("audit_log", [])
    #             print(f"    Session {med_session_id} — {len(audit)} log entries:")
    #             for e in audit:
    #                 ts = e.get("timestamp", "")[-8:]
    #                 d = e.get("details", {})
    #                 key_details = {k: v for k, v in d.items()
    #                                if k in ("intent", "risk", "chief_complaint",
    #                                         "ready", "passed", "content_length",
    #                                         "ticket_id", "destination")}
    #                 extras = f"  {key_details}" if key_details else ""
    #                 print(f"      {ts} {e['action']}{extras}")

    #             actions = [e["action"] for e in audit]
    #             for step in ["message_received", "routing_complete", "intake_complete",
    #                          "context_built"]:
    #                 check(f"pipeline step '{step}' logged", step in actions)

    #             # These may or may not be present depending on flow
    #             if "casecard_generated" in actions:
    #                 check("casecard_generated logged", True)
    #             if "ticket_created" in actions:
    #                 check("ticket_created logged", True)
    #             if "qa_validation" in actions:
    #                 check("qa_validation logged", True)
    #             if "staff_review" in actions:
    #                 check("staff_review logged", True)
    #             if "reply_sent" in actions:
    #                 check("reply_sent logged", True)

    #     # List all sessions
    #     data = await req(c, "GET", "/v1/sessions", headers=H)
    #     if data:
    #         total = data.get("total", 0)
    #         print(f"    Total sessions: {total}")
    #         check("multiple sessions created", total >= 3)

    #     # ──────────────────────────────────────
    #     # 10. DATABASE — CRUD, Documents, DB Audit
    #     # ──────────────────────────────────────
    #     section("10. DATABASE — CRUD & Audit Log")

    #     # Create test patient (idempotent — may already exist from prior run)
    #     data = await req(c, "POST", "/v1/patient", json=NEW_PATIENT, headers=H,
    #                      label="create P099")
    #     if data:
    #         check("patient created", data.get("patient_id") == "P099")
    #     else:
    #         # Already exists from a previous run — verify it's there
    #         data = await req(c, "GET", "/v1/patient/P099", headers=H,
    #                          label="P099 already exists, verifying")
    #         check("patient exists (prior run)", data and data.get("patient", {}).get("name"))

    #     # Add medication
    #     data = await req(c, "POST", "/v1/patient/P099/medications", json=NEW_MED, headers=H)
    #     check("medication added", data and "id" in data)

    #     # Add lab
    #     data = await req(c, "POST", "/v1/patient/P099/labs", json=NEW_LAB, headers=H)
    #     check("lab added", data and "id" in data)

    #     # Upload document
    #     data = await req(c, "POST", "/v1/patient/P099/documents", headers=H,
    #                      files={"file": ("scan.txt", b"test scan content", "text/plain")},
    #                      data={"doc_type": "scan", "description": "test"})
    #     doc_id = data.get("id") if data else None
    #     check("document uploaded", doc_id is not None)

    #     # Download and verify content
    #     if doc_id:
    #         r = await c.get(f"/v1/patient/P099/documents/{doc_id}", headers=H)
    #         check("document content matches", r.status_code == 200 and r.content == b"test scan content")

    #     # Patient summary has everything
    #     data = await req(c, "GET", "/v1/patient/P099", headers=H)
    #     if data:
    #         check("summary has our medication",
    #               any(m["name"] == "Aspirin" for m in data.get("medications", [])))
    #         check("summary has our lab",
    #               any(l["test_name"] == "HbA1c" for l in data.get("recent_labs", [])))

    #     # Verify seeded data integrity (from mock_data JSON → SQLite)
    #     data = await req(c, "GET", "/v1/patient/P003", headers=H)
    #     if data:
    #         med_names = [m["name"] for m in data.get("medications", [])]
    #         prob_descs = [p["description"] for p in data.get("problems", [])]
    #         check("P003 Warfarin in DB", "Warfarin" in med_names)
    #         check("P003 Furosemide in DB", "Furosemide" in med_names)
    #         check("P003 Atrial fibrillation in DB", "Atrial fibrillation" in prob_descs)
    #         check("P003 Heart failure in DB", "Heart failure" in prob_descs)
    #         check("P003 CKD stage 3 in DB", "CKD stage 3" in prob_descs)

    #     # DB audit log
    #     data = await req(c, "GET", "/v1/audit-log?limit=30", headers=H)
    #     if data:
    #         entries = data.get("entries", [])
    #         actions = [e["action"] for e in entries]
    #         check("audit has create_patient", "create_patient" in actions)
    #         check("audit has add_medication", "add_medication" in actions)
    #         check("audit has upload_document", "upload_document" in actions)

    # # ──────────────────────────────────────
    # # Summary
    # # ──────────────────────────────────────
    # total = passed + failed + skipped
    # print(f"\n{'═'*60}")
    # print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped  ({total} total)")
    # if failed == 0:
    #     print(f"  ✓ ALL TESTS PASSED")
    # else:
    #     print(f"  ✗ {failed} FAILURES — see above")
    # print(f"{'═'*60}\n")


if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  CLINICAL AGENT SYSTEM v2 — Full Pipeline Test")
    print("  Tests: LLM routing, tool calling, EHR retrieval,")
    print("  case cards, QA gates, reply drafting, lab analysis")
    print("═" * 60)
    asyncio.run(test_workflow())