from asyncio import current_task
import re
import httpx
from config import AgentConfig, AuthConfig


class Bot_Controller:
    def __init__(self, agent: AgentConfig, client: httpx.AsyncClient):
        self.agent = agent
        self.client = client
        self.session_state = {}
        self.session_map = {}

    async def health_check(self):
        print("Health Check")
        res = await self._req("GET", "/health")
        if not res:
            print("cannot connect to agent server. Please start the server first.")
        return

    def is_review_msg(self, message: str):
        pattern = (
            r"^session\s*[:：]\s*(?P<session_id>.*?)\s+"
            r"回覆\s*[:：]\s*(?P<status>同意|不同意)\s+"
            r"病患\s*[:：]\s*(?P<patient_id>.*?)\s+"
            r"醫生註記\s*[:：]\s*(?P<notes>.*)"
        )
        review_match = re.match(pattern, message.strip(), re.S | re.I)

        if not review_match:
            return False, None

        res = review_match.groupdict()

        return True, {
            "session_id": res["session_id"],
            "approved": res["status"] == "同意",
            "patient_id": res["patient_id"],
            "physician_notes": res["notes"].strip(),
        }
    def is_reply_approved_msg(self, message: str):
        pattern = (
            r"病患\s*[:：]\s*(?P<patient_id>.*?)\s+"
            r"session\s*[:：]\s*(?P<session_id>.*?)\s+"
            r"傳送回覆\s*[:：]\s*(?P<status>同意|不同意)"
        )
        reply_match = re.match(pattern, message.strip(), re.S | re.I)

        if not reply_match:
            return False, None

        res = reply_match.groupdict()

        return True, {
            "session_id": res["session_id"],
            "approved": res["status"] == "同意",
            "patient_id": res["patient_id"],
        }

    async def process_query(
        self, patient_id: str, query: str, token: str, input_id: str | None = None
    ):
        res: dict = {}
        session_info = self.session_state.get(input_id, {})
        session_id = session_info.get("id")
        status = session_info.get("status", "")
        function: str
        query_body: dict = {}
        if not status:
            function = "message"
            query_body = {"content": query, "patient_id": patient_id}
        elif status == "needs_clarification":
            current_q = session_info["questions"][session_info["current_question"]]
            session_info["qa_sets"][current_q] = query
            session_info["current_question"] += 1
            session_info["questions_left"] -= 1
            if session_info["questions_left"] <= 0:
                function = "clarification"
                query_body = {
                    "session_id": session_id,
                    "responses": session_info["qa_sets"],
                }
            else:
                next_q = session_info["questions"][session_info["current_question"]]
                return {
                    "reply": next_q,
                }
        res = await self._process_message(
            query=query_body, input_id=input_id, function=function, token=token
        )
        if res is None:
            return {"error": "Failed to process the query. Please try again later."}
        if res.get("status") == "needs_clarification":
            session_info = self.session_state.get(input_id, {})
            # print(f"  Questions: {session_info}")
            current_q = session_info["questions"][session_info["current_question"]]
            return {
                "reply": current_q,
            }
        if res.get("status") == "emergency":
            self.session_state.pop(input_id, None)
            return {
                "reply": res.get(
                    "reply",
                    "The system has detected an emergency condition. Please seek immediate medical attention.",
                ),
                "data": res.get("data", {}),
                "need_push": True,
                "target": "physician",
                "status": "emergency",
            }
        if res.get("status") == "need_review":
            self.session_state.pop(input_id, None)
            return {
                "reply": "我們的醫療人員正在處理您的情況，請您耐心等待。",
                "need_push": True,
                "target": res.get("data").get("ticket").get("destination"),
                "data": res.get("data"),
                "status": "need_review",
            }
        if res.get("status") == "need_manual_review":
            self.session_state.pop(input_id, None)
            return {
                "data": res,
                "need_push": True,
                "target": "physician",
                "status": "need_manual_review",
            }
    
    async def process_review(self, session_id: str, review_response: dict, token: str):

        review_res = {
            "session_id": session_id,
            "approved": review_response["approved"],
            "physician_notes": review_response["physician_notes"],
        }
        data = await self._req(
            "POST",
            "/v1/review",
            json=review_res,
            headers={"Authorization": f"Bearer {token}"},
        )
        # if data.get("status") == "ready_to_send":
        # await self._process_send_reply(session_id)
        if data and data.get("status") == "ready_to_send":
            return {
                "data": data,
                "reply": data.get("draft_reply", {}),
                "need_push": True,
                "target": "physician",
                "status": "ready_to_send",
            }
        if data and data.get("status") == "needs_revision":
            return {
                "data": data,
                "need_push": True,
                "target": "physician",
                "status": "needs_revision",
            }
        if data and data.get("status") == "escalated":
            return {
                "data": data,
                "need_push": True,
                "target": "physician",
                "status": "escalated",
            }
        else:
            return {
                "data": data,
                "need_push": True,
                "target": "physician",
                "status": "error",
            }
        
    async def process_send_reply(self, session_id: str, token: str):
        data = await self._req(
            "POST",
            "/v1/send",
            json={"session_id": session_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        if data and data.get("status") == "sent":
            return {
                "reply": data.get("reply")
            }       

    async def _process_message(
        self, query: dict, input_id: str, function: str, token: str
    ):
        data = await self._req(
            "POST",
            f"/v1/{function}",
            json=query,
            headers={"Authorization": f"Bearer {token}"},
        )
        print(data)
        if not data:
            return None
        session_id = data.get("session_id")
        status = data.get("status")
        self.session_state[input_id] = {"id": session_id, "status": status}
        print(f"  Status: {status}")
        print(f"  Session: {session_id}")

        if status == "emergency":
            print(f"  Red Flags: {data.get('red_flags')}")
            print(f"  Response: {data.get('response', '')}...")
            return {
                "reply": data.get("response", ""),
                "data": data,
                "status": "emergency",
            }

        if status == "needs_clarification":
            print(f"  Questions: {data.get('questions')}")
            question_list = data.get("questions", [])
            self.session_state[input_id]["questions"] = question_list
            self.session_state[input_id]["qa_sets"] = {i: None for i in question_list}
            self.session_state[input_id]["current_question"] = 0
            self.session_state[input_id]["questions_left"] = len(question_list)

            return {
                "data": data.get("questions"),
                "status": "needs_clarification",
            }
            #
        if status == "qa_failed":
            return {
                "data": data,
                "status": "need_manual_review",
            }
        if status == "ready_for_review" and data:
            return {"data": data, "status": "need_review"}

    async def _req(self, method, url, **kwargs):
        try:
            r = await self.client.request(method, url, **kwargs)
            print(f"  [{r.status_code}] {method} {url}")

            if r.status_code != 200:
                print(f"  Error: {r.text}")
                return None

            return r.json() if r.text else None
        except httpx.ConnectError:
            print(f"  Cannot connect to server {self.agent.base_url}")
            return None
        except Exception as e:
            print(f"  {type(e).__name__}: {e}")
            return None
