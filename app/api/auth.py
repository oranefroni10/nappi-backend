"""
Auth endpoints — user registration, login, baby linking.

Routes (/auth):
  POST /signup          - Register user; optionally match existing baby by name + birthdate
  POST /register-baby   - Create and link a new baby to an existing user
  POST /signin          - Authenticate with username + password
  POST /change-password - Update password (requires old password)
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from datetime import date
from app.services.auth_manager import AuthManager
from app.db.models import BabyResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


class SignUpRequest(BaseModel):
    username: str
    password: str
    repeat_password: str
    first_name: str
    last_name: str
    baby_first_name: Optional[str] = None
    baby_birthdate: Optional[date] = None

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


class SignInRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    user_id: int
    old_password: str
    new_password: str


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


# Used by: Signup page — registers user, checks for existing baby by name + birthdate
@router.post("/signup", response_model=SignUpResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignUpRequest):
    try:
        auth = AuthManager()
        user, baby, found = await auth.signup(
            username=request.username,
            password=request.password,
            first_name=request.first_name,
            last_name=request.last_name,
            baby_first_name=request.baby_first_name,
            baby_birthdate=request.baby_birthdate,
        )

        baby_response = None
        if baby:
            baby_response = BabyResponse(
                id=baby.id,
                first_name=baby.first_name,
                last_name=baby.last_name,
                birthdate=baby.birthdate,
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


# Used by: Onboarding page — register baby when no existing baby found at signup
@router.post("/register-baby", response_model=AuthResponse)
async def register_baby(request: RegisterBabyRequest):
    try:
        auth = AuthManager()
        user, baby = await auth.register_baby(
            user_id=request.user_id,
            first_name=request.first_name,
            birthdate=request.birthdate,
            gender=request.gender,
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
            ),
            message=f"Baby {baby.first_name} {baby.last_name} registered!",
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Used by: Login page
@router.post("/signin", response_model=AuthResponse)
async def signin(request: SignInRequest):
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


# Used by: User Profile page — change password form
@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(request: ChangePasswordRequest):
    try:
        auth = AuthManager()
        result = await auth.change_password(request.user_id, request.old_password, request.new_password)

        return ChangePasswordResponse(
            password_changed=result
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
