from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


class AgentChatResponse(BaseModel):
    status: Literal["completed", "confirmation_required", "error"]
    message: str
    provider: str | None = None
    fallback_attempts: list[str] = Field(default_factory=list)
    preview: dict[str, Any] | None = None
    confirmation_token: str | None = None


class AgentConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=256)
    reason: str | None = Field(default=None, max_length=500)


class AgentConfirmResponse(BaseModel):
    status: Literal["completed"] = "completed"
    message: str
    result: dict[str, Any]


class AgentCancelRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=256)


class AgentStatusResponse(BaseModel):
    enabled: bool
    providers: list[dict[str, str | bool]]
    confirmation_expire_minutes: int
