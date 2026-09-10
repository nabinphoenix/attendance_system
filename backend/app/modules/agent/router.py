from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.dependencies import DbSession, require_role
from app.modules.identity.models import User

from .graph import run_agent
from .providers import FallbackModelClient
from .schemas import (
    AgentCancelRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentConfirmRequest,
    AgentConfirmResponse,
    AgentStatusResponse,
)
from .tools import AgentActionError, cancel_approval, confirm_approval

router = APIRouter(prefix="/agent", tags=["AI assistant"])
Admin = Annotated[User, Depends(require_role("admin"))]


@router.get("/status", response_model=AgentStatusResponse)
def agent_status(user: Admin) -> AgentStatusResponse:
    return AgentStatusResponse(
        enabled=settings.ai_enabled,
        providers=FallbackModelClient().status(),
        confirmation_expire_minutes=settings.ai_confirmation_expire_minutes,
    )


@router.post("/chat", response_model=AgentChatResponse)
def chat(payload: AgentChatRequest, user: Admin, db: DbSession) -> AgentChatResponse:
    if not settings.ai_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The AI assistant is disabled.")
    try:
        result = run_agent(db, user, payload.message.strip())
        db.commit()
    except Exception:
        db.rollback()
        raise
    return AgentChatResponse(**result)


@router.post("/confirm", response_model=AgentConfirmResponse)
def confirm(payload: AgentConfirmRequest, user: Admin, db: DbSession) -> AgentConfirmResponse:
    try:
        result = confirm_approval(db, user, payload.confirmation_token, payload.reason)
        db.commit()
    except AgentActionError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The data changed while this approval was waiting. Create a fresh preview.") from exc
    return AgentConfirmResponse(message="The approved action has been applied and recorded in the audit log.", result=result)


@router.post("/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel(payload: AgentCancelRequest, user: Admin, db: DbSession) -> None:
    try:
        cancel_approval(db, user, payload.confirmation_token)
        db.commit()
    except AgentActionError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
