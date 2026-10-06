"""手机号验证码登录 + HttpOnly Cookie 中的 JWT。"""
import secrets
import threading
import time
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .models import User

COOKIE_NAME = "sy_session"
TOKEN_TTL = timedelta(days=7)
CODE_TTL_S = 300
CODE_MIN_INTERVAL_S = 60


class CodeStore:
    """验证码只存在内存里（单进程部署足够）。"""

    def __init__(self):
        self._codes: dict[str, tuple[str, float, int]] = {}
        self._lock = threading.Lock()

    def issue(self, phone: str) -> str:
        with self._lock:
            old = self._codes.get(phone)
            if old and time.time() - (old[1] - CODE_TTL_S) < CODE_MIN_INTERVAL_S:
                raise HTTPException(429, "验证码发送太频繁，请 1 分钟后再试")
            code = f"{secrets.randbelow(1_000_000):06d}"
            self._codes[phone] = (code, time.time() + CODE_TTL_S, 0)
            return code

    def verify(self, phone: str, code: str) -> bool:
        with self._lock:
            item = self._codes.get(phone)
            if not item:
                return False
            real, expires, tries = item
            if time.time() > expires or tries >= 5:
                self._codes.pop(phone, None)
                return False
            if secrets.compare_digest(real, code):
                self._codes.pop(phone, None)
                return True
            self._codes[phone] = (real, expires, tries + 1)
            return False


codes = CodeStore()


def make_token(user: User) -> str:
    s = get_settings()
    payload = {"sub": str(user.id), "role": user.role, "exp": utcnow() + TOKEN_TTL}
    return jwt.encode(payload, s.app_secret_key, algorithm="HS256")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "请先登录")
    try:
        payload = jwt.decode(token, get_settings().app_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "登录已过期，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "账号不存在，请重新登录")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "只有管理员可以进行此操作")
    return user
