import httpx
import asyncio

BASE_URL = "http://localhost:8080"
from test_mockprocess import query, question, clarification_answers, review_response

patient_id = "P001"


async def req(client, method, url, **kwargs):
    try:
        r = await client.request(method, url, **kwargs)
        print(f"  [{r.status_code}] {method} {url}")

        if r.status_code != 200:
            print(f"  Error: {r.text}")
            return None

        return r.json() if r.text else None
    except httpx.ConnectError:
        print(f"  Cannot connect to {BASE_URL}")
        return None
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
        return None


async def test_workflow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as c:
        
        print("1. Health Check")
        if not await req(c, "GET", "/health"):
            print("Server not running. Start with: uvicorn server:app --port 8080")
            return

        print("2. Demo Patients")
        data = await req(c, "GET", "/v1/demo/patients")
        if data:
            for p in data["patients"]:
                print(f"  {p['mrn']}: {p['name']} ({p['age']}歲)")

        print(f"3. Patient {patient_id} Summary")
        data = await req(c, "GET", f"/v1/patient/{patient_id}")
        if data:
            print(f"  Name: {data['patient']['name']}")
            print(f"  Problems: {[p['description'] for p in data['problems']]}")
            print(f"  Meds: {[m['name'] for m in data['medications']]}")

        print("4. Knowledge Search")
        print(f"  Query: {query['query']}")
        data = await req(c, "GET", "/v1/knowledge/search", params=query)
        if data:
            for chunk in data["results"][:2]:
                print(f"  [{chunk['source_type']}] {chunk['source']}")
        
        print("5. Process Message")
        print(f"  Question: {question['content']}")
        data = await req(
            c,
            "POST",
            "/v1/message",
            json=question,
        )
        if not data:
            return

        session_id = data.get("session_id")
        status = data.get("status")
        print(f"  Status: {status}")
        print(f"  Session: {session_id}")

        if status == "emergency":
            print(f"  Red Flags: {data.get('red_flags')}")
            print(f"  Response: {data.get('response', '')}...")
            return

        if status == "needs_clarification":
            print(f"  Questions: {data.get('questions')}")
            clarification_ans = {
                "session_id": session_id,
                "responses": clarification_answers["responses"],
            }
            print(f"  clarification answers {clarification_answers['responses']}")
            data = await req(
                c,
                "POST",
                "/v1/clarification",
                json=clarification_ans,
            )
            if data:
                status = data.get("status")
                session_id = data.get("session_id", session_id)
                print(f"  New Status: {status}")

        if status == "ready_for_review" and data:
            ticket = data.get("ticket", {})
            print(f"  Ticket: {ticket.get('ticket_id')}")
            print(f"  Destination: {ticket.get('destination')}")
            print(f"  Risk: {ticket.get('risk_level')}")

            print("6. Staff Review")
            review_res = {
                "session_id": session_id,
                "approved": review_response["approved"],
                "physician_notes": review_response["physician_notes"],
            }
            data = await req(
                c,
                "POST",
                "/v1/review",
                json=review_res,
            )
            if data:
                print(f"  Status: {data.get('status')}")
                draft = data.get("draft_reply", {})
                if draft:
                    print(f"  Reply: {draft.get('response', '')}...")
                
                if data.get("status") == "ready_to_send":
                    print("7. Send Reply")
                    await req(c, "POST", "/v1/send", json={"session_id": session_id})

        print("8. Audit Log")
        data = await req(c, "GET", f"/v1/session/{session_id}")
        if data:
            print(f"  Status: {data.get('status')}")
            for e in data.get("audit_log", [])[-5:]:
                print(f"  - {e['action']}")

        print("9. Lab Analysis")
        data = await req(c, "POST", "/v1/lab-report/LAB001/analyze")
        if data:
            print(f"  Summary: {data.get('analysis', {}).get('summary', 'N/A')}")
        
        print("\nDone")


if __name__ == "__main__":
    print("\nCLINICAL AGENT TEST\n")
    asyncio.run(test_workflow())
