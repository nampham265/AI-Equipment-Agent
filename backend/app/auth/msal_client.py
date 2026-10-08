"""
MSAL-based OAuth2 flow for Microsoft Entra ID (work/school accounts).
Handles: /auth/login redirect, /auth/callback token exchange, /auth/logout.
Tokens stored server-side in signed cookie session ONLY.
Never sends tokens to browser JS.
"""
import json
import msal
from app.core.config import settings
from urllib.parse import urlencode

# In-memory cache for simplicity in this MVP
token_cache = msal.TokenCache()

def _build_msal_app(cache=None):
    if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_TENANT_ID:
        return None
    authority = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
    return msal.ConfidentialClientApplication(
        settings.MICROSOFT_CLIENT_ID,
        authority=authority,
        client_credential=settings.MICROSOFT_CLIENT_SECRET,
        token_cache=cache or token_cache
    )

def get_auth_url(state: str, nonce: str) -> str | None:
    app = _build_msal_app()
    if not app:
        return None
    
    scopes = settings.MICROSOFT_SCOPES.split(" ")
    auth_url = app.get_authorization_request_url(
        scopes,
        state=state,
        redirect_uri=settings.MICROSOFT_REDIRECT_URI,
        nonce=nonce
    )
    return auth_url

def exchange_code(code: str, state: str) -> dict | None:
    app = _build_msal_app()
    if not app:
        return None
    
    scopes = settings.MICROSOFT_SCOPES.split(" ")
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=scopes,
        redirect_uri=settings.MICROSOFT_REDIRECT_URI
    )
    return result

def get_token_from_cache(account_dict: dict) -> str | None:
    """Gets token silently from cache if available."""
    if not account_dict:
        return None
    app = _build_msal_app()
    if not app:
        return None
    
    scopes = settings.MICROSOFT_SCOPES.split(" ")
    result = app.acquire_token_silent(scopes, account=account_dict)
    if result and "access_token" in result:
        return result["access_token"]
    return None
