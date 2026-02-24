import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from fastapi.datastructures import Headers
import httpx


class Bind_Controller:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.binding_state = {}
        self.access_capture_state = {}
        self.binding_store = set()

    async def bind_start(self, headers: Headers, force_regenerate: bool = False):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401
        username = me.get("username")
        role = me.get("role")
        if not username:
            return {"detail": "Not authenticated"}, 401

        for binding in self.binding_state.values():
            self._sync_expiration(binding)
            if (
                binding.get("username") == username
                and binding.get("status") == "pending_verification"
            ):
                if not force_regenerate:
                    return {
                        "detail": {
                            "code": "BINDING_ALREADY_ACTIVE",
                            "message": "An active binding code already exists",
                            "retryable": True,
                        }
                    }, 409
                binding["status"] = "cancelled"
                self.binding_store.discard(binding.get("code"))

        code = await self._generate_code()
        binding_id = f"LB-{uuid.uuid4()}"
        expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        self.binding_state[binding_id] = {
            "binding_id": binding_id,
            "code": code,
            "username": username,
            "role": role,
            "status": "pending_verification",
            "expires_at": expires_at,
            "verified_at": None,
            "bound_platform_id": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.binding_store.add(code)
        return {
            "binding_id": binding_id,
            "code": code,
            "status": "pending_verification",
            "expires_at": expires_at,
            "poll_interval_sec": 2,
            "binding_message": f"請將這個串訊息完整貼入line：\n驗證碼：{code}",
        }, 200

    async def get_code(self, binding_id: str, headers: Headers):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401

        binding = self.binding_state.get(binding_id)
        if not binding:
            return {
                "detail": {
                    "code": "BINDING_NOT_FOUND",
                    "message": "Binding not found",
                    "retryable": False,
                }
            }, 404

        self._sync_expiration(binding)
        if me.get("role") != "admin" and me.get("username") != binding.get("username"):
            return {"detail": "Not authenticated"}, 401

        return {
            "binding_id": binding.get("binding_id"),
            "username": binding.get("username"),
            "role": binding.get("role"),
            "status": binding.get("status"),
            "expires_at": binding.get("expires_at"),
            "verified_at": binding.get("verified_at"),
            "bound_platform_id_masked": self._mask_platform_id(
                binding.get("bound_platform_id")
            )
            if binding.get("bound_platform_id")
            else None,
            "failure_reason": binding.get("failure_reason"),
        }, 200

    async def bind_account(self, input_id: str, message: str, bot_token: str):
        code = await self.is_binding_msg(message)
        if not code:
            return None, 204
        if not bot_token:
            return {"detail": "Not authorized"}, 401

        target_binding = None
        mode = "account_binding"
        for binding in self.binding_state.values():
            if binding.get("code") == code:
                target_binding = binding
                break
        if not target_binding:
            for binding in self.access_capture_state.values():
                if binding.get("code") == code:
                    target_binding = binding
                    mode = "access_capture"
                    break
        if not target_binding:
            return {
                "detail": {
                    "code": "BINDING_CODE_INVALID",
                    "message": "Invalid binding code",
                    "retryable": True,
                }
            }, 400

        self._sync_expiration(target_binding)
        if target_binding.get("status") == "expired":
            self.binding_store.discard(target_binding.get("code"))
            return {
                "detail": {
                    "code": "BINDING_CODE_EXPIRED",
                    "message": "Binding code expired",
                    "retryable": False,
                }
            }, 400
        if target_binding.get("status") != "pending_verification":
            self.binding_store.discard(target_binding.get("code"))
            return {
                "detail": {
                    "code": "BINDING_ALREADY_USED",
                    "message": "Binding code already used",
                    "retryable": False,
                }
            }, 400

        role_res, role_status = await self._req(
            "GET",
            f"/v1/user/role/{input_id}",
            headers={"Authorization": f"Bearer {bot_token}"},
        )
        if role_status == 200 and role_res and role_res.get("role"):
            return {
                "detail": {
                    "code": "LINE_ID_ALREADY_BOUND",
                    "message": "This LINE user is already bound",
                    "retryable": False,
                }
            }, 409

        if mode == "account_binding":
            _, update_status = await self._req(
                "PATCH",
                "/v1/auth/user",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "username": target_binding.get("username"),
                    "platform_id": input_id,
                },
            )
            if update_status != 200:
                target_binding["status"] = "failed"
                target_binding["failure_reason"] = "platform_update_failed"
                self.binding_store.discard(target_binding.get("code"))
                return {
                    "detail": {
                        "code": "BINDING_FAILED",
                        "message": "Failed to bind account",
                        "retryable": True,
                    }
                }, 500

        target_binding["status"] = "verified"
        target_binding["verified_at"] = datetime.now(UTC).isoformat()
        target_binding["bound_platform_id"] = input_id
        if mode == "access_capture":
            target_binding["captured_platform_id"] = input_id
        self.binding_store.discard(target_binding.get("code"))
        return {
            "binding_id": target_binding.get("binding_id"),
            "status": "verified",
            "username": target_binding.get("username"),
            "role": target_binding.get("role"),
            "verified_at": target_binding.get("verified_at"),
            "mode": mode,
        }, 200

    async def start_access_capture(self, headers: Headers, force_regenerate: bool = False):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401
        role = me.get("role")
        if role not in ("admin", "physician"):
            return {"detail": "Not authenticated"}, 401
        username = me.get("username")
        if not username:
            return {"detail": "Not authenticated"}, 401

        for binding in self.access_capture_state.values():
            self._sync_expiration(binding)
            if (
                binding.get("username") == username
                and binding.get("status") == "pending_verification"
            ):
                if not force_regenerate:
                    return {
                        "detail": {
                            "code": "BINDING_ALREADY_ACTIVE",
                            "message": "An active binding code already exists",
                            "retryable": True,
                        }
                    }, 409
                binding["status"] = "cancelled"
                self.binding_store.discard(binding.get("code"))

        code = await self._generate_code()
        binding_id = f"LBA-{uuid.uuid4()}"
        expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        self.access_capture_state[binding_id] = {
            "binding_id": binding_id,
            "code": code,
            "username": username,
            "role": role,
            "status": "pending_verification",
            "expires_at": expires_at,
            "verified_at": None,
            "bound_platform_id": None,
            "captured_platform_id": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.binding_store.add(code)
        return {
            "binding_id": binding_id,
            "code": code,
            "status": "pending_verification",
            "expires_at": expires_at,
            "poll_interval_sec": 2,
            "binding_message": f"請將這個串訊息完整貼入line：\n驗證碼：{code}",
        }, 200

    async def get_access_capture(self, binding_id: str, headers: Headers):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401
        role = me.get("role")
        if role not in ("admin", "physician"):
            return {"detail": "Not authenticated"}, 401

        binding = self.access_capture_state.get(binding_id)
        if not binding:
            return {
                "detail": {
                    "code": "BINDING_NOT_FOUND",
                    "message": "Binding not found",
                    "retryable": False,
                }
            }, 404

        self._sync_expiration(binding)
        if me.get("role") != "admin" and me.get("username") != binding.get("username"):
            return {"detail": "Not authenticated"}, 401

        return {
            "binding_id": binding.get("binding_id"),
            "username": binding.get("username"),
            "role": binding.get("role"),
            "status": binding.get("status"),
            "expires_at": binding.get("expires_at"),
            "verified_at": binding.get("verified_at"),
            "bound_platform_id_masked": self._mask_platform_id(
                binding.get("bound_platform_id")
            )
            if binding.get("bound_platform_id")
            else None,
            "captured_platform_id": binding.get("captured_platform_id"),
            "failure_reason": binding.get("failure_reason"),
        }, 200

    async def cancel_access_capture(self, binding_id: str, headers: Headers):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401
        role = me.get("role")
        if role not in ("admin", "physician"):
            return {"detail": "Not authenticated"}, 401

        binding = self.access_capture_state.get(binding_id)
        if not binding:
            return {
                "detail": {
                    "code": "BINDING_NOT_FOUND",
                    "message": "Binding not found",
                    "retryable": False,
                }
            }, 404

        self._sync_expiration(binding)
        if me.get("role") != "admin" and me.get("username") != binding.get("username"):
            return {"detail": "Not authenticated"}, 401
        if binding.get("status") == "pending_verification":
            binding["status"] = "cancelled"
            self.binding_store.discard(binding.get("code"))
        return {
            "binding_id": binding.get("binding_id"),
            "status": binding.get("status"),
        }, 200

    async def _is_verified(self, headers: Headers):
        auth_header = headers.get("authorization")
        if not auth_header:
            return None, 401
        return await self._req(
            "GET",
            "/v1/auth/me",
            headers={"Authorization": auth_header},
        )

    async def _generate_code(self) -> str:
        code: str
        while True:
            code = str(secrets.randbelow(900000) + 100000)
            if code not in self.binding_store:
                break
        return code

    async def is_binding_msg(self, message: str):
        bind_match = re.match(
            r"驗證碼：(\d{6})$",
            message.strip(),
        )
        if not bind_match:
            return None
        return bind_match.group(1)

    async def cancel_code(self, binding_id: str, headers: Headers):
        me, status_code = await self._is_verified(headers)
        if status_code != 200 or not me:
            return {"detail": "Not authenticated"}, 401

        binding = self.binding_state.get(binding_id)
        if not binding:
            return {
                "detail": {
                    "code": "BINDING_NOT_FOUND",
                    "message": "Binding not found",
                    "retryable": False,
                }
            }, 404

        self._sync_expiration(binding)
        if me.get("role") != "admin" and me.get("username") != binding.get("username"):
            return {"detail": "Not authenticated"}, 401
        if binding.get("status") == "pending_verification":
            binding["status"] = "cancelled"
            self.binding_store.discard(binding.get("code"))
        return {
            "binding_id": binding.get("binding_id"),
            "status": binding.get("status"),
        }, 200

    def _sync_expiration(self, binding: dict):
        if binding.get("status") != "pending_verification":
            return
        expires_at = binding.get("expires_at")
        if not expires_at:
            return
        exp_text = str(expires_at)
        if exp_text.endswith("Z"):
            exp_text = exp_text[:-1] + "+00:00"
        exp_dt = datetime.fromisoformat(exp_text)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=UTC)
        if datetime.now(UTC) > exp_dt:
            binding["status"] = "expired"
            self.binding_store.discard(binding.get("code"))

    def _mask_platform_id(self, platform_id: str):
        if len(platform_id) <= 6:
            return "*" * len(platform_id)
        return f"{platform_id[:3]}***{platform_id[-3:]}"

    async def _req(self, method, url, **kwargs):
        try:
            r = await self.client.request(method, url, **kwargs)
            print(f"  [{r.status_code}] {method} {url}")

            if r.status_code != 200:
                print(f"  Error: {r.text}")
                return None, r.status_code

            return r.json() if r.text else None, r.status_code
        except httpx.ConnectError:
            print("  Cannot connect to server")
            return None, 500
        except Exception as e:
            print(f"  {type(e).__name__}: {e}")
            return None, 500
