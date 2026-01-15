"""Authentication API endpoints"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from datetime import date
from app.services.auth_manager import AuthManager
from app.db.models import BabyResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


# ========== Request Models ==========

class SignUpRequest(BaseModel):
    username: str
    password: str
    repeat_password: str
    first_name: str
    last_name: str
    baby_first_name: str
    baby_birthdate: date

    @field_validator('repeat_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class RegisterBabyRequest(BaseModel):
    user_id: int
    first_name: str
    birthdate: date
    gender: Optional[str] = None
    notes: Optional[str] = None  # Parent notes: allergies, conditions, health info


class SignInRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    user_id: int
    old_password: str
    new_password: str


# ========== Response Models ==========

class SignUpResponse(BaseModel):
    user_id: int
    username: str
    baby_registered: bool
    baby: Optional[BabyResponse] = None
    message: str
    first_name: str
    last_name: str


class AuthResponse(BaseModel):
    user_id: int
    username: str
    baby_id: Optional[int] = None
    baby: Optional[BabyResponse] = None
    message: str
    first_name: str
    last_name: str


class ChangePasswordResponse(BaseModel):
    password_changed: bool


# ========== Endpoints ==========

@router.post("/signup", response_model=SignUpResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignUpRequest):
    """Register new user, check for existing baby using user's last name"""
    try:
        auth = AuthManager()
        user, baby, found = await auth.signup(
            username=request.username,
            password=request.password,
            first_name=request.first_name,
            last_name=request.last_name,
            baby_first_name=request.baby_first_name,
            baby_birthdate=request.baby_birthdate
        )

        baby_response = None
        if baby:
            baby_response = BabyResponse(
                id=baby.id,
                first_name=baby.first_name,
                last_name=baby.last_name,
                birthdate=baby.birthdate,
                notes=getattr(baby, 'notes', None)
            )

        return SignUpResponse(
            user_id=user.id,
            username=user.username,
            baby_registered=found,
            baby=baby_response,
            message="Welcome!" if found else "Please register your baby",
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/register-baby", response_model=AuthResponse)
async def register_baby(request: RegisterBabyRequest):
    """Register baby using user's last name and link to user"""
    try:
        auth = AuthManager()
        # Truncate notes to 2000 chars max
        notes = request.notes[:2000] if request.notes else None
        
        user, baby = await auth.register_baby(
            user_id=request.user_id,
            first_name=request.first_name,
            birthdate=request.birthdate,
            gender=request.gender,
            notes=notes
        )

        return AuthResponse(
            user_id=user.id,
            username=user.username,
            baby_id=baby.id,
            baby=BabyResponse(
                id=baby.id,
                first_name=baby.first_name,
                last_name=baby.last_name,
                birthdate=baby.birthdate,
                notes=getattr(baby, 'notes', None)
            ),
            message=f"Baby {baby.first_name} {baby.last_name} registered!",
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/signin", response_model=AuthResponse)
async def signin(request: SignInRequest):
    """Authenticate user"""
    try:
        auth = AuthManager()
        user, baby = await auth.signin(request.username, request.password)

        baby_response = None
        if baby:
            baby_response = BabyResponse(
                id=baby.id,
                first_name=baby.first_name,
                last_name=baby.last_name,
                birthdate=baby.birthdate,
                notes=getattr(baby, 'notes', None)
            )

        return AuthResponse(
            user_id=user.id,
            username=user.username,
            baby_id=user.baby_id,
            baby=baby_response,
            message="Sign in successful",
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(request: ChangePasswordRequest):
    """Change user password"""
    try:
        auth = AuthManager()
        result = await auth.change_password(request.user_id, request.old_password, request.new_password)

        return ChangePasswordResponse(
            password_changed=result
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
