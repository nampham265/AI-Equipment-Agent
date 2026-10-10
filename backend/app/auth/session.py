"""
Signed cookie session using itsdangerous.
Stores: user_email, user_name, user_oid, is_manager, msal_account_json.
Never stores raw access tokens in cookie (only MSAL cache handles tokens).
"""
import json
from typing import Any
from pydantic import BaseModel, model_validator
from fastapi import Request, Response
from itsdangerous import URLSafeSerializer, BadSignature
from app.core.config import settings

COOKIE_NAME = "session"

class SessionData(BaseModel):
    model_config = {"extra": "ignore"}

    user_email: str
    user_name: str
    user_oid: str = "oid-user"
    role: str = "USER"
    is_active: bool = True
    msal_account_json: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "role" not in data or not data.get("role"):
                if data.get("is_admin"):
                    data["role"] = "ADMIN"
                elif data.get("is_manager"):
                    data["role"] = "MANAGER"
                else:
                    data["role"] = "USER"
        return data

    @property
    def is_admin(self) -> bool:
        return self.role.upper() == "ADMIN"

    @property
    def is_manager(self) -> bool:
        return self.role.upper() in ("MANAGER", "ADMIN")

    @property
    def is_user(self) -> bool:
        return self.role.upper() == "USER"

def get_session(request: Request) -> SessionData | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    
    serializer = URLSafeSerializer(settings.APP_SECRET_KEY, salt="session-cookie")
    try:
        data = serializer.loads(cookie)
        return SessionData(**data)
    except BadSignature:
        return None

def set_session(response: Response, data: SessionData) -> None:
    serializer = URLSafeSerializer(settings.APP_SECRET_KEY, salt="session-cookie")
    cookie_value = serializer.dumps(data.model_dump())
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV != "development",
        max_age=86400 * 7 # 7 days
    )

def clear_session(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV != "development"
    )
