import json
import re
from typing import Callable, Type, TypeVar
import httpx
from pydantic import BaseModel

from config import LLMConfig

T = TypeVar("T", bound=BaseModel)


class LLMConnectionError(Exception):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = httpx.AsyncClient(base_url=config.base_url, timeout=60.0)
        self._healthy = False
    
    async def health_check(self) -> bool:
        try:
            r = await self.client.get("/models", timeout=5.0)
            self._healthy = r.status_code == 200
            return self._healthy
        except Exception:
            self._healthy = False
            return False
    
    @property
    def is_healthy(self) -> bool:
        return self._healthy
    

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_executor: Callable | None = None,
        max_tool_rounds: int = 3,
    ) -> str:
        if not self._healthy:
            raise LLMConnectionError(f"LLM server not available at {self.config.base_url}")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for _ in range(max_tool_rounds):
            body = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or self.config.max_tokens,
            }
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            try:
                response = await self.client.post(
                    "/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
                response.raise_for_status()
            except httpx.ConnectError:
                self._healthy = False
                raise LLMConnectionError(f"LLM server connection lost: {self.config.base_url}")
            except httpx.HTTPStatusError as e:
                print(f"[DEBUG] LLM HTTP {e.response.status_code}: {e.response.text[:300]}")
                raise

            choice = response.json()["choices"][0]
            msg = choice["message"]
            tool_calls = msg.get("tool_calls")

            if tools:
                if tool_calls:
                    print(f"[DEBUG] LLM round {round_num}: {len(tool_calls)} tool call(s)")
                else:
                    print(f"[DEBUG] LLM round {round_num}: no tool calls, returning text")

            if not tool_calls or not tool_executor:
                return (msg.get("content") or "").strip()

            messages.append({**msg, "content": None})

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args_raw = tc["function"]["arguments"]
                fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                print(f"[DEBUG] Tool call: {fn_name}({fn_args})")
                result = await tool_executor(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        return (msg.get("content") or "").strip()

    
    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        if not self._healthy:
            raise LLMConnectionError(f"LLM server not available at {self.config.base_url}")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        json_schema = schema.model_json_schema()

        try:
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": self.config.model_name,
                    "messages": messages,
                    "temperature": temperature or self.config.temperature,
                    "max_tokens": max_tokens or self.config.max_tokens,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "schema": json_schema,
                            "strict": True,
                        },
                    },
                },
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            print(f"[DEBUG] Structured output raw: {raw}...")
            parsed = json.loads(raw)
            return schema.model_validate(parsed)
        except httpx.ConnectError:
            self._healthy = False
            raise LLMConnectionError(f"LLM server connection lost: {self.config.base_url}")
    
    async def generate_completion(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if not self._healthy:
            raise LLMConnectionError(f"LLM server not available at {self.config.base_url}")
        
        try:
            response = await self.client.post(
                "/completions",
                json={
                    "model": self.config.model_name,
                    "prompt": prompt,
                    "temperature": temperature or self.config.temperature,
                    "max_tokens": max_tokens or self.config.max_tokens,
                    "stop": ["\n\n", "</s>", "<|eot_id|>"],
                },
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["text"].strip()
        except httpx.HTTPStatusError:
            return ""
        except httpx.ConnectError:
            self._healthy = False
            raise LLMConnectionError(f"LLM server connection lost: {self.config.base_url}")
        except httpx.HTTPStatusError as e:
            raise LLMConnectionError(f"LLM server error: {e.response.status_code} - {e.response.text}")
    
    async def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        system: str | None = None,
    ) -> T:
        raw = await self.generate(prompt, system)
        print(f"[DEBUG] LLM raw output: {raw}...")
        return self._parse_json(raw, schema)
    
    def _parse_json(self, text: str, schema: Type[T]) -> T:
        text = re.sub(r"<unused\d+>[\s\S]*?<unused\d+>", "", text)
        
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            text = json_match.group(1)
        else:
            text = re.sub(r"<[^>]+>", "", text)
            json_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
            if json_match:
                text = json_match.group(1)
        
        data = json.loads(text.strip())
        return schema.model_validate(data)
    
    async def close(self):
        await self.client.aclose()