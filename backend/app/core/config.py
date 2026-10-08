"""Application configuration via pydantic-settings.

Reads from .env file located at the workspace root (one level above backend/).
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Workspace root is two levels up from this file: backend/app/core/config.py
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    APP_ENV: str = "development"
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    APP_SECRET_KEY: str = "change-me-in-production"  # for session signing

    # Data backend: "excel" | "sqlite" | "microsoft_graph"
    DATA_BACKEND: str = "excel"
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Excel workbook (primary data store when DATA_BACKEND=excel)
    EXCEL_DATA_PATH: str = "backend/data/equipment_agent.xlsx"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    ALLOW_INVENTORY_DATA_TO_GEMINI: bool = False

    # Microsoft Entra / Graph
    MICROSOFT_TENANT_ID: str = ""
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    MICROSOFT_SITE_ID: str = ""
    MICROSOFT_EQUIPMENT_LIST_ID: str = ""
    MICROSOFT_REQUESTS_LIST_ID: str = ""
    MICROSOFT_SCOPES: str = "openid profile offline_access User.Read Sites.ReadWrite.All"

    # Manager authorization (comma-separated emails, lowercased)
    MANAGER_EMAILS: str = ""

    # Email notifications via Graph
    EMAIL_NOTIFICATIONS_ENABLED: bool = False

    # Computed helpers
    @property
    def manager_email_set(self) -> set[str]:
        emails = {e.strip().lower() for e in self.MANAGER_EMAILS.split(',') if e.strip()}
        if not emails and self.APP_ENV == "development":
            emails.add("manager@company.com")
        return emails

    @property
    def graph_configured(self) -> bool:
        return bool(self.MICROSOFT_TENANT_ID and self.MICROSOFT_CLIENT_ID and 
                    self.MICROSOFT_SITE_ID and self.MICROSOFT_EQUIPMENT_LIST_ID and
                    self.MICROSOFT_REQUESTS_LIST_ID)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def resolved_excel_path(self) -> Path:
        p = Path(self.EXCEL_DATA_PATH)
        if p.is_absolute() and p.exists():
            return p
        if p.exists():
            return p.resolve()
        ws_root = Path(__file__).resolve().parents[3]
        ws_p = ws_root / self.EXCEL_DATA_PATH
        if ws_p.exists():
            return ws_p.resolve()
        if self.EXCEL_DATA_PATH.startswith("backend/") or self.EXCEL_DATA_PATH.startswith("backend\\"):
            sub_path = self.EXCEL_DATA_PATH[8:]
            if Path(sub_path).exists():
                return Path(sub_path).resolve()
            backend_dir = Path(__file__).resolve().parents[2]
            backend_p = backend_dir / sub_path
            if backend_p.exists():
                return backend_p.resolve()
        return (ws_root / self.EXCEL_DATA_PATH).resolve()

    @property
    def excel_configured(self) -> bool:
        return self.resolved_excel_path.exists()


settings = Settings()
