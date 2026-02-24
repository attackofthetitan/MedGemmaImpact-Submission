from asyncio import current_task
import platform
import re
import httpx
from config import AgentConfig, AuthConfig


class Auth_Controller:
    def __init__(self, auth_manager: AuthConfig, client: httpx.AsyncClient):
        self.auth_manager = auth_manager
        self.client = client
        self.token: str = ""
        self.auth_state: dict[str, dict] = {}
        self.auth_role: dict[str, str] = {}
        self.patient_map = {}

    def get_default_staff(self):
        return self.auth_manager.default_staff

    async def get_patient(self, input_id: str):
        if input_id not in self.patient_map:
            res, _ = await self._req(
                "GET",
                "/v1/platform/patient",
                params={
                    "platform_id": input_id,
                },
                headers={"Authorization": f"Bearer {await self.get_token()}"},
            )
            self.patient_map[input_id] = res.get("patient_id") if res else None
        return self.patient_map[input_id]

    async def get_patient_info(self, patient_id: str):
        res, _ = await self._req(
            "GET",
            f"/v1/patient/{patient_id}",
            headers={"Authorization": f"Bearer {await self.get_token()}"},
        )
        return res.get("patient") if res else None

    async def get_staff(self, input_id: str, patient_id: str | None = None):
        if input_id not in self.auth_state:
            relationships = ["physician", "front_desk", "nurse", "staff", "pharmacist", "emergency"]
            self.auth_state[input_id] = {}
            for relation in relationships:
                res, _ = await self._req(
                    "GET",
                    f"/v1/patient/staff/{relation}",
                    params={
                        "patient_id": patient_id
                        if patient_id
                        else await self.get_patient(input_id)
                    },
                    headers={"Authorization": f"Bearer {await self.get_token()}"},
                )
                staff_id = res.get("staff_id") if res else None
                self.auth_state[input_id][relation] = staff_id
                self.auth_role[staff_id] = "STAFF"

        return self.auth_state[input_id]

    async def get_patient_platform_id(self, patient_id: str):
        res, _ = await self._req(
            "GET",
            f"/v1/patients/{patient_id}/platform-id",
            headers={"Authorization": f"Bearer {await self.get_token()}"},
        )
        platform_id = res.get("platform_id") if res else None

        return platform_id

    async def is_staff(self, input_id: str):
        role = self.auth_role.get(input_id)
        if not role:
            role = (
                "STAFF"
                if await self.get_role(input_id)
                in ["admin", "physician", "nurse", "front_desk", "staff"]
                else "NOT_STAFF"
            )
        return role == "STAFF"

    async def get_role(self, input_id: str):
        res, _ = await self._req(
            "GET",
            f"/v1/user/role/{input_id}",
            headers={"Authorization": f"Bearer {await self.get_token()}"},
        )
        return res.get("role") if res else None

    async def get_token(self):
        if await self._is_token_expired():
            await self.login()
        return self.token

    async def _is_token_expired(self, token: str | None = None):
        res, code = await self._req(
            "GET", "/v1/auth/me", headers={"Authorization": f"Bearer {self.token}"}
        )
        if code == 401:
            return True
        return False

    async def login(self, username: str | None = None, password: str | None = None):
        if username is None or password is None:
            res, code = await self._req(
                "POST",
                "/v1/auth/login",
                json={
                    "username": self.auth_manager.username,
                    "password": self.auth_manager.password,
                },
            )
        else:
            res, code = await self._req(
                "POST",
                "/v1/auth/login",
                json={"username": username, "password": password},
            )
        self.token = res.get("access_token") if res else None

    async def _req(self, method, url, **kwargs) -> tuple[dict | None, int]:
        try:
            r = await self.client.request(method, url, **kwargs)
            print(f"Auth {r}")
            print(f"  [{r.status_code}] {method} {url}")

            if r.status_code != 200:
                print(f"  Error: {r.text}")
                return None, r.status_code

            return r.json() if r.text else None, 200
        except httpx.ConnectError:
            print("  Cannot connect to server")
            return None, -1
        except Exception as e:
            print(f"  {type(e).__name__}: {e}")
            return None, -1
