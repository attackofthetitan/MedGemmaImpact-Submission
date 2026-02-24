import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import config
from models import User, UserRole

security = HTTPBearer(auto_error=False)



def hash_password(password: str) -> str:
    # hashin with PBKDF2-HMAC-SHA256 100k iterations and a random salt
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, stored_hash = password_hash.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return secrets.compare_digest(dk.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=config.auth.token_expire_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, config.auth.jwt_secret, algorithm=config.auth.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.auth.jwt_secret, algorithms=[config.auth.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(credentials.credentials)

    from ehr_db import db
    user_data = await db.get_user_by_id(int(payload["sub"]))
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return User(
        id=user_data["id"],
        username=user_data["username"],
        role=UserRole(user_data["role"]),
        name=user_data["name"],
        active=bool(user_data["active"]),
        platform_id=user_data.get("platform_id",None),
    )


def require_roles(*roles: UserRole):
    async def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(r.value for r in roles)}",
            )
        return user
    return check_role