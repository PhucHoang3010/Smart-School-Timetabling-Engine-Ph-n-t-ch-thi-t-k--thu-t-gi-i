import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import SessionLocal
from ..models.users import UserModel

AUTH_SECRET = os.getenv("AUTH_SECRET", "development-demo-secret-change-me").encode()
PASSWORD_ITERATIONS = 120_000
bearer = HTTPBearer(auto_error=False)
REVOKED_TOKENS: set[str] = set()

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def create_access_token(user: UserModel, expires_in: int = 8 * 60 * 60) -> str:
    payload = {"sub": user.id, "username": user.username, "role": user.role, "teacher_id": user.teacher_id, "jti": secrets.token_hex(16), "exp": int(time.time()) + expires_in}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(AUTH_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"

def decode_access_token(token: str) -> Dict:
    try:
        if token in REVOKED_TOKENS:
            raise ValueError
        encoded, signature = token.split(".", 1)
        expected = hmac.new(AUTH_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["exp"] < time.time():
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ hoặc đã hết hạn.")

def revoke_access_token(token: str):
    REVOKED_TOKENS.add(token)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> Dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cần đăng nhập.")
    return decode_access_token(credentials.credentials)

def require_roles(*roles: str):
    def dependency(user: Dict = Depends(current_user)) -> Dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền thực hiện thao tác này.")
        return user
    return dependency

def seed_demo_users():
    db: Session = SessionLocal()
    try:
        from ..models.resources import TeacherModel
        teacher = db.get(TeacherModel, 1)
        if not teacher:
            teacher = TeacherModel(id=1, name="Teacher Demo")
            db.add(teacher)
            db.flush()
        demo_users = [("admin", "admin123", "ADMIN", None), ("teacher1", "teacher123", "TEACHER", teacher.id)]
        for username, password, role, teacher_id in demo_users:
            if not db.query(UserModel).filter(UserModel.username == username).first():
                db.add(UserModel(username=username, password_hash=hash_password(password), role=role, teacher_id=teacher_id))
        db.commit()
    finally:
        db.close()
