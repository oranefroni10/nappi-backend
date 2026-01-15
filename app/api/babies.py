"""
Baby API - Endpoints for baby-related operations.

Provides:
- GET /babies/{baby_id}/notes - Get baby notes
- PUT /babies/{baby_id}/notes - Update baby notes
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..services.babies_data import BabyDataManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/babies", tags=["babies"])

# Maximum notes length
MAX_NOTES_LENGTH = 2000


# ============================================
# Request/Response Models
# ============================================

class NotesResponse(BaseModel):
    """Response containing baby notes."""
    baby_id: int
    notes: Optional[str] = None


class UpdateNotesRequest(BaseModel):
    """Request to update baby notes."""
    notes: str


class UpdateNotesResponse(BaseModel):
    """Response after updating notes."""
    success: bool
    notes: str


# ============================================
# Endpoints
# ============================================

@router.get("/{baby_id}/notes", response_model=NotesResponse)
async def get_baby_notes(
    baby_id: int,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Get notes for a baby.
    
    Validates that the user owns this baby before returning notes.
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to view this baby's notes"
        )
    
    notes = await baby_manager.get_baby_notes(baby_id)
    
    return NotesResponse(
        baby_id=baby_id,
        notes=notes
    )


@router.put("/{baby_id}/notes", response_model=UpdateNotesResponse)
async def update_baby_notes(
    baby_id: int,
    request: UpdateNotesRequest,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Update notes for a baby.
    
    Notes are truncated to 2000 characters if longer.
    Validates that the user owns this baby before updating.
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to update this baby's notes"
        )
    
    # Truncate notes if too long
    notes = request.notes[:MAX_NOTES_LENGTH] if request.notes else ""
    
    # Update notes
    success = await baby_manager.update_baby_notes(baby_id, notes)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notes"
        )
    
    logger.info(f"Updated notes for baby {baby_id} (length: {len(notes)})")
    
    return UpdateNotesResponse(
        success=True,
        notes=notes
    )
