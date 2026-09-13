from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ...core.auth import create_access_token, current_user, hash_password, revoke_access_token, seed_demo_users, verify_password
from ...core.database import SessionLocal
from ...models.users import UserModel
from ...schemas.auth_schema import LoginRequest, LoginResponse, RegisterRequest, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logout_bearer = HTTPBearer()

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.username == payload.username, UserModel.is_active.is_(True)).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Username hoặc password không chính xác.")
        return LoginResponse(access_token=create_access_token(user), user=UserResponse(id=user.id, username=user.username, role=user.role, teacher_id=user.teacher_id))
    finally:
        db.close()

@router.post("/register", response_model=LoginResponse, status_code=201)
def register(payload: RegisterRequest):
    db = SessionLocal()
    try:
        if db.query(UserModel).filter(UserModel.username == payload.username).first():
            raise HTTPException(status_code=409, detail="Username đã tồn tại.")
        from ...models.resources import TeacherModel
        teacher = TeacherModel(name=payload.teacher_name)
        db.add(teacher)
        db.flush()
        user = UserModel(username=payload.username, password_hash=hash_password(payload.password), role="TEACHER", teacher_id=teacher.id)
        db.add(user)
        db.commit()
        db.refresh(user)
        return LoginResponse(access_token=create_access_token(user), user=UserResponse(id=user.id, username=user.username, role=user.role, teacher_id=user.teacher_id))
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Không thể đăng ký: {error}")
    finally:
        db.close()

@router.get("/me", response_model=UserResponse)
def me(user=Depends(current_user)):
    return UserResponse(id=user["sub"], username=user["username"], role=user["role"], teacher_id=user.get("teacher_id"))

@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(logout_bearer), user=Depends(current_user)):
    revoke_access_token(credentials.credentials)
    return {"status": "logged_out", "username": user["username"]}
