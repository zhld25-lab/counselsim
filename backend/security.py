"""Password hashing (bcrypt) and stateless signed tokens (HMAC)."""
import base64
import hashlib
import hmac
import time

import bcrypt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as OrmSession

from config import SECRET_KEY, TOKEN_TTL_SECONDS
from db import get_db
from models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _sign(payload: str) -> str:
    digest = hmac.new(
        SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def decode_token(token: str):
    try:
        user_id, issued, sig = token.split(".")
    except ValueError:
        return None
    payload = f"{user_id}.{issued}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    if time.time() - int(issued) > TOKEN_TTL_SECONDS:
        return None
    return int(user_id)


def current_user(
    authorization: str = Header(default=""),
    db: OrmSession = Depends(get_db),
) -> User:
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    user_id = decode_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
