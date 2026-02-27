"""Chat API — AI chat with full baby context via Gemini."""

import logging
from typing import List, Literal, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..services.chat_service import get_chat_service
from ..services.babies_data import BabyDataManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    baby_id: int
    user_id: int
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str


# Used by: Chat page — AI conversational interface (Gemini with full baby context)
@router.post("", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    """Chat history is session-only (sent from frontend, not persisted)."""
    baby_manager = BabyDataManager()
    
    if not await baby_manager.validate_baby_ownership(request.user_id, request.baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to access this baby's data"
        )
    
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )
    
    chat_service = get_chat_service()
    response = await chat_service.chat(
        baby_id=request.baby_id,
        user_message=request.message.strip(),
        conversation_history=[m.model_dump() for m in request.history]
    )
    
    return ChatResponse(response=response)
