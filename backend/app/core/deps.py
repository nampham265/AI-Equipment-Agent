"""FastAPI dependency injection helpers."""
from __future__ import annotations

from typing import Generator

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.auth.session import SessionData, get_session

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request) -> SessionData:
    """Get authenticated user from session. Raises 401 if not logged in, 403 if deactivated."""
    session = get_session(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không có quyền truy cập. Vui lòng đăng nhập."
        )
    if not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đã bị vô hiệu hóa. Vui lòng liên hệ Quản trị viên."
        )
    return session

def require_manager(current_user: SessionData = Depends(get_current_user)) -> SessionData:
    """Raise 403 if user is not a manager or admin."""
    if not current_user.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản lý (MANAGER) hoặc Quản trị viên (ADMIN) mới có quyền thực hiện thao tác này."
        )
    return current_user

def require_admin(current_user: SessionData = Depends(get_current_user)) -> SessionData:
    """Raise 403 if user is not an administrator."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên (ADMIN) mới có quyền thực hiện thao tác này."
        )
    return current_user

