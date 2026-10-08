import json
import secrets
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from app.auth import msal_client
from app.auth.session import SessionData, get_session, set_session, clear_session
from app.core.config import settings
from app.repositories.factory import get_user_repo

router = APIRouter(tags=["auth"])

@router.get("/auth/login")
def login(request: Request):
    if not settings.graph_configured:
        raise HTTPException(503, "Microsoft Graph integration is not configured. Vui lòng cấu hình các biến môi trường Microsoft trong file .env.")
        
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    
    request.session["oauth_state"] = state
    request.session["oauth_nonce"] = nonce
    
    auth_url = msal_client.get_auth_url(state=state, nonce=nonce)
    if not auth_url:
        raise HTTPException(503, "Failed to build MSAL auth URL.")
        
    return RedirectResponse(auth_url)


@router.post("/auth/dev-login")
def dev_login(request: Request, response: Response, payload: dict | None = None):
    """Available in development environment to allow testing before Entra setup."""
    if settings.APP_ENV != "development":
        raise HTTPException(403, "Development login is only available when APP_ENV=development.")
    
    payload = payload or {}
    email = payload.get("email", "nampham.31231023820@st.ueh.edu.vn")
    
    user_repo = get_user_repo()
    user = user_repo.get_by_email(email)
    if user is None:
        raise HTTPException(
            403,
            detail=f"Tài khoản '{email}' chưa được cấp quyền trong hệ thống. Vui lòng liên hệ Quản trị viên."
        )
    if not user.is_active:
        raise HTTPException(
            403,
            detail=f"Tài khoản '{email}' đã bị vô hiệu hóa. Vui lòng liên hệ Quản trị viên."
        )

    session_data = SessionData(
        user_email=user.user_email,
        user_name=user.user_name,
        user_oid=f"dev-oid-{user.user_email}",
        role=user.role,
        is_active=user.is_active,
    )
    
    res = Response(
        content=json.dumps({
            "ok": True,
            "email": user.user_email,
            "name": user.user_name,
            "role": user.role,
            "is_manager": session_data.is_manager,
            "is_admin": session_data.is_admin,
        }),
        media_type="application/json"
    )
    set_session(res, session_data)
    return res


@router.get("/auth/dev-users")
def dev_users():
    """List available users in development mode for easy testing."""
    if settings.APP_ENV != "development":
        raise HTTPException(403, "Development users list is only available when APP_ENV=development.")
    user_repo = get_user_repo()
    users = user_repo.list_all()
    return [
        {
            "email": u.user_email,
            "name": u.user_name,
            "role": u.role,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.get("/auth/callback")
def auth_callback(request: Request, response: Response, code: str = None, state: str = None, error: str = None, error_description: str = None):
    if error:
        raise HTTPException(400, f"Auth error: {error} - {error_description}")
        
    saved_state = request.session.pop("oauth_state", None)
    nonce = request.session.pop("oauth_nonce", None)
    
    if not state or state != saved_state:
        raise HTTPException(400, "Invalid state")
        
    if not code:
        raise HTTPException(400, "Missing authorization code")
        
    result = msal_client.exchange_code(code, state)
    if not result or "error" in result:
        err = result.get("error_description", "Unknown error") if result else "Unknown error"
        raise HTTPException(400, f"Token exchange failed: {err}")
        
    id_token_claims = result.get("id_token_claims", {})
    account = result.get("account", {})
    
    email = id_token_claims.get("preferred_username") or id_token_claims.get("email") or ""
    name = id_token_claims.get("name") or "Unknown"
    oid = id_token_claims.get("oid") or ""
    
    user_repo = get_user_repo()
    user = user_repo.get_by_email(email)
    if user is None:
        raise HTTPException(403, detail=f"Tài khoản '{email}' chưa được cấp quyền trong hệ thống. Vui lòng liên hệ Quản trị viên.")
    if not user.is_active:
        raise HTTPException(403, detail=f"Tài khoản '{email}' đã bị vô hiệu hóa.")
    
    session_data = SessionData(
        user_email=user.user_email,
        user_name=user.user_name or name,
        user_oid=oid,
        role=user.role,
        is_active=user.is_active,
        msal_account_json=json.dumps(account) if account else None
    )
    
    # We redirect to the frontend. The cookie is set on the response.
    redirect_res = RedirectResponse(url=settings.FRONTEND_ORIGIN)
    set_session(redirect_res, session_data)
    
    return redirect_res


@router.get("/auth/logout")
@router.post("/auth/logout")
def logout(response: Response):
    res = Response(content=json.dumps({"ok": True}), media_type="application/json")
    clear_session(res)
    return res


@router.get("/api/me")
def get_me(request: Request):
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not authenticated")
    if not session.is_active:
        raise HTTPException(403, "Tài khoản đã bị vô hiệu hóa.")
    return {
        "email": session.user_email,
        "name": session.user_name,
        "role": session.role,
        "is_manager": session.is_manager,
        "is_admin": session.is_admin,
    }
