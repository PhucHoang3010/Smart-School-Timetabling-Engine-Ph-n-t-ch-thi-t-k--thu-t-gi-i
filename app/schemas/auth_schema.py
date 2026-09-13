from typing import Optional
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    teacher_name: str = Field(min_length=2, max_length=100)

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    teacher_id: Optional[int] = None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
