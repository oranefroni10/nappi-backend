"""
Baby API - Endpoints for baby-related operations.

Provides multi-note CRUD:
- GET /babies/{baby_id}/notes - List all notes for a baby
- POST /babies/{baby_id}/notes - Create a new note
- PUT /babies/{baby_id}/notes/{note_id} - Update a note
- DELETE /babies/{baby_id}/notes/{note_id} - Delete a note
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..services.babies_data import BabyDataManager
from ..db.models import BabyNote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/babies", tags=["babies"])


# ============================================
# Request/Response Models
# ============================================

class NoteCreate(BaseModel):
    """Request to create a new note."""
    title: str
    content: str


class NoteUpdate(BaseModel):
    """Request to update an existing note."""
    title: str
    content: str


class NoteResponse(BaseModel):
    """Response containing a single note."""
    id: int
    baby_id: int
    title: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class NotesListResponse(BaseModel):
    """Response containing list of notes."""
    baby_id: int
    notes: List[NoteResponse]


class DeleteResponse(BaseModel):
    """Response for delete operation."""
    success: bool
    message: str


# ============================================
# Endpoints
# ============================================

@router.get("/{baby_id}/notes", response_model=NotesListResponse)
async def list_notes(
    baby_id: int,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Get all notes for a baby.
    
    Returns a list of notes ordered by creation date (newest first).
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to view this baby's notes"
        )
    
    notes = await baby_manager.get_baby_notes(baby_id)
    
    return NotesListResponse(
        baby_id=baby_id,
        notes=[
            NoteResponse(
                id=n.id,
                baby_id=n.baby_id,
                title=n.title,
                content=n.content,
                created_at=n.created_at.isoformat() if n.created_at else None,
                updated_at=n.updated_at.isoformat() if n.updated_at else None,
            )
            for n in notes
        ]
    )


@router.post("/{baby_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    baby_id: int,
    request: NoteCreate,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Create a new note for a baby.
    
    Title is limited to 200 characters.
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to add notes for this baby"
        )
    
    # Validate input
    if not request.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title cannot be empty"
        )
    
    if not request.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content cannot be empty"
        )
    
    # Create note
    note = await baby_manager.create_baby_note(
        baby_id=baby_id,
        title=request.title.strip(),
        content=request.content.strip()
    )
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create note"
        )
    
    logger.info(f"Created note '{note.title}' for baby {baby_id}")
    
    return NoteResponse(
        id=note.id,
        baby_id=note.baby_id,
        title=note.title,
        content=note.content,
        created_at=note.created_at.isoformat() if note.created_at else None,
        updated_at=note.updated_at.isoformat() if note.updated_at else None,
    )


@router.put("/{baby_id}/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    baby_id: int,
    note_id: int,
    request: NoteUpdate,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Update an existing note.
    
    Title is limited to 200 characters.
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to update this note"
        )
    
    # Validate input
    if not request.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title cannot be empty"
        )
    
    if not request.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content cannot be empty"
        )
    
    # Update note
    note = await baby_manager.update_baby_note(
        note_id=note_id,
        baby_id=baby_id,
        title=request.title.strip(),
        content=request.content.strip()
    )
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found or you don't have permission to update it"
        )
    
    logger.info(f"Updated note {note_id} for baby {baby_id}")
    
    return NoteResponse(
        id=note.id,
        baby_id=note.baby_id,
        title=note.title,
        content=note.content,
        created_at=note.created_at.isoformat() if note.created_at else None,
        updated_at=note.updated_at.isoformat() if note.updated_at else None,
    )


@router.delete("/{baby_id}/notes/{note_id}", response_model=DeleteResponse)
async def delete_note(
    baby_id: int,
    note_id: int,
    user_id: int = Query(..., description="User ID for ownership validation")
):
    """
    Delete a note.
    """
    baby_manager = BabyDataManager()
    
    # Validate ownership
    if not await baby_manager.validate_baby_ownership(user_id, baby_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you don't have permission to delete this note"
        )
    
    # Delete note
    success = await baby_manager.delete_baby_note(note_id=note_id, baby_id=baby_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found or you don't have permission to delete it"
        )
    
    logger.info(f"Deleted note {note_id} for baby {baby_id}")
    
    return DeleteResponse(
        success=True,
        message="Note deleted successfully"
    )
