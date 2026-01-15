"""
Chat API - AI-powered conversational interface for baby sleep questions.

Provides a chat endpoint where parents can ask questions about their baby
with full context about:
- Baby profile and parent notes
- Sleep patterns and statistics
- Room conditions and optimal settings
- Awakening history and correlations
"""

import logging
from typing import List, Literal, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..services.chat_service import get_chat_service
from ..services.babies_data import BabyDataManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================
# Request/Response Models
# ============================================

class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    baby_id: int
    user_id: int  # For ownership validation
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    """Response containing the AI-generated reply."""
    response: str


# ============================================
# Endpoints
# ============================================

@router.post("", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    """
    Send a message to the AI chat and get a personalized response.
    
    The AI has full context about the baby including:
    - Profile information and parent notes
    - Optimal sleep conditions
    - Recent awakenings with insights
    - Correlation analysis (what caused awakenings)
    - Sleep patterns and daily summaries
    - Current room conditions
    
    Chat history is session-only (sent from frontend, not persisted).
    """
    baby_manager = BabyDataManager()
    
    # Validate user owns this baby
    if not await baby_manager.validate_baby_ownership(request.user_id, request.baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to access this baby's data"
        )
    
    # Validate message is not empty
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )
    
    # Process chat
    chat_service = get_chat_service()
    response = await chat_service.chat(
        baby_id=request.baby_id,
        user_message=request.message.strip(),
        conversation_history=[m.model_dump() for m in request.history]
    )
    
    return ChatResponse(response=response)
