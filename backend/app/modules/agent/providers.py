"""Small provider adapters with predictable fallback and no frontend secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


class ProviderFailure(RuntimeError):
    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class NoProviderAvailable(RuntimeError):
    def __init__(self, attempts: list[str]) -> None:
        super().__init__("No configured AI provider was available.")
        self.attempts = attempts


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderReply:
    provider: str
    content: str
    tool_calls: list[ToolCall]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 429, 500, 502, 503, 504}


class BaseProvider:
    name: str

    def configured(self) -> bool:
        raise NotImplementedError

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderReply:
        raise NotImplementedError

    @staticmethod
    def _post(
        provider: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=settings.ai_request_timeout_seconds) as client:
                response = client.post(url, headers=headers, params=params, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderFailure(provider, "request timed out", retryable=True) from exc
        except httpx.RequestError as exc:
            raise ProviderFailure(provider, "network request failed", retryable=True) from exc
        if response.is_error:
            raise ProviderFailure(
                provider,
                f"provider returned HTTP {response.status_code}",
                retryable=_is_retryable_status(response.status_code),
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderFailure(provider, "provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderFailure(provider, "provider returned an invalid response")
        return payload


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, name: str, api_key: str | None, model: str | None, base_url: str) -> None:
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderReply:
        if not self.configured():
            raise ProviderFailure(self.name, "provider is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            headers["HTTP-Referer"] = settings.frontend_url
            headers["X-Title"] = settings.app_name
        payload = self._post(
            self.name,
            f"{self.base_url}/chat/completions",
            headers=headers,
            body={
                "model": self.model,
                "messages": _openai_messages(messages),
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": 800,
            },
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderFailure(self.name, "provider returned no completion")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderFailure(self.name, "provider returned no assistant message")
        tool_calls: list[ToolCall] = []
        for index, item in enumerate(message.get("tool_calls") or []):
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                continue
            tool_calls.append(
                ToolCall(
                    id=str(item.get("id") or f"{self.name}-tool-{index}"),
                    name=function["name"],
                    arguments=_json_object(function.get("arguments")),
                )
            )
        return ProviderReply(self.name, _content_text(message.get("content")), tool_calls)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self.api_key = api_key
        self.model = model

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderReply:
        if not self.configured():
            raise ProviderFailure(self.name, "provider is not configured")
        system_parts = [_content_text(item.get("content")) for item in messages if item.get("role") == "system"]
        body: dict[str, Any] = {
            "contents": _gemini_contents(messages),
            "generationConfig": {"temperature": 0, "maxOutputTokens": 800},
        }
        if tools:
            body["tools"] = [
                {"functionDeclarations": [_gemini_function(item["function"]) for item in tools]}
            ]
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        payload = self._post(
            self.name,
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            params={"key": self.api_key or ""},
            body=body,
        )
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            raise ProviderFailure(self.name, "provider returned no completion")
        content = candidates[0].get("content")
        if not isinstance(content, dict):
            raise ProviderFailure(self.name, "provider returned no assistant message")
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for index, part in enumerate(content.get("parts") or []):
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                text_parts.append(part["text"])
            function_call = part.get("functionCall")
            if isinstance(function_call, dict) and isinstance(function_call.get("name"), str):
                tool_calls.append(
                    ToolCall(
                        id=f"gemini-tool-{index}",
                        name=function_call["name"],
                        arguments=_json_object(function_call.get("args")),
                    )
                )
        return ProviderReply(self.name, "\n".join(text_parts), tool_calls)


def _openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate internal graph messages to the OpenAI-compatible tool protocol."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            converted.append({
                "role": "tool",
                "tool_call_id": str(message.get("tool_call_id") or "tool-call"),
                "content": _content_text(message.get("content")),
            })
            continue
        item: dict[str, Any] = {"role": role, "content": _content_text(message.get("content"))}
        if role == "assistant" and message.get("tool_calls"):
            item["tool_calls"] = [
                {
                    "id": str(call.get("id") or f"tool-{index}"),
                    "type": "function",
                    "function": {
                        "name": str(call.get("name") or "tool"),
                        "arguments": json.dumps(_json_object(call.get("arguments"))),
                    },
                }
                for index, call in enumerate(message["tool_calls"])
                if isinstance(call, dict)
            ]
        converted.append(item)
    return converted
def _gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            result = _json_object(message.get("content"))
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": str(message.get("name") or "tool"),
                                "response": {"result": result},
                            }
                        }
                    ],
                }
            )
            continue
        parts: list[dict[str, Any]] = []
        if _content_text(message.get("content")):
            parts.append({"text": _content_text(message.get("content"))})
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                parts.append(
                    {
                        "functionCall": {
                            "name": str(call.get("name") or "tool"),
                            "args": _json_object(call.get("arguments")),
                        }
                    }
                )
        if parts:
            contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    return contents


def _gemini_function(function: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": function["name"],
        "description": function.get("description", ""),
        "parameters": _gemini_schema(function.get("parameters") or {"type": "object"}),
    }


def _gemini_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_gemini_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    converted = {key: _gemini_schema(value) for key, value in schema.items()}
    schema_type = converted.get("type")
    if isinstance(schema_type, str):
        converted["type"] = {
            "object": "OBJECT",
            "array": "ARRAY",
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
        }.get(schema_type.lower(), schema_type.upper())
    return converted


class FallbackModelClient:
    """Try the configured providers in order without leaking provider errors to users."""

    def __init__(self) -> None:
        self.providers: dict[str, BaseProvider] = {
            "groq": OpenAICompatibleProvider(
                "groq", settings.ai_groq_api_key, settings.ai_groq_model, "https://api.groq.com/openai/v1"
            ),
            "openrouter": OpenAICompatibleProvider(
                "openrouter", settings.ai_openrouter_api_key, settings.ai_openrouter_model, "https://openrouter.ai/api/v1"
            ),
            "gemini": GeminiProvider(settings.ai_gemini_api_key, settings.ai_gemini_model),
        }
        self.order = [item.strip().lower() for item in settings.ai_provider_order.split(",") if item.strip()]

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[ProviderReply, list[str]]:
        attempts: list[str] = []
        for name in self.order:
            provider = self.providers.get(name)
            if provider is None:
                attempts.append(f"{name}: unknown provider")
                continue
            if not provider.configured():
                attempts.append(f"{name}: not configured")
                continue
            try:
                reply = provider.complete(messages, tools)
                attempts.append(f"{name}: selected")
                return reply, attempts
            except ProviderFailure as exc:
                reason = "temporarily unavailable" if exc.retryable else "unavailable"
                attempts.append(f"{name}: {reason}")
        raise NoProviderAvailable(attempts)

    def status(self) -> list[dict[str, str | bool]]:
        return [
            {"name": name, "configured": provider.configured()}
            for name, provider in self.providers.items()
        ]
