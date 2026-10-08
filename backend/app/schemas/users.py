"""Pydantic schemas for User Management and Role-based Access Control."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRole(str, Enum):
    USER = "USER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class UserRead(BaseModel):
    user_email: str
    user_name: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    user_email: EmailStr
    user_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole = Field(..., description="Role must be USER or MANAGER")

    @field_validator("role")
    @classmethod
    def validate_role_not_admin(cls, v: UserRole) -> UserRole:
        if v == UserRole.ADMIN:
            raise ValueError("Không thể tạo trực tiếp tài khoản ADMIN qua giao diện thông thường.")
        return v


class UserRoleUpdate(BaseModel):
    role: UserRole = Field(..., description="Target role: USER or MANAGER")

    @field_validator("role")
    @classmethod
    def validate_role_not_admin(cls, v: UserRole) -> UserRole:
        if v == UserRole.ADMIN:
            raise ValueError("Không thể nâng cấp tài khoản lên ADMIN qua giao diện thông thường.")
        return v


class UserActiveUpdate(BaseModel):
    is_active: bool
