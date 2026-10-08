"""Repository factory.

Returns the appropriate EquipmentRepository and RequestRepository
implementation based on the DATA_BACKEND setting.

  DATA_BACKEND=excel           → ExcelEquipmentRepository / ExcelRequestRepository
  DATA_BACKEND=microsoft_graph → GraphEquipmentRepository / GraphRequestRepository
  DATA_BACKEND=sqlite (default) → SQLiteEquipmentRepository / SQLiteRequestRepository
"""
from __future__ import annotations

from app.core.config import settings
from app.repositories.base import EquipmentRepository, RequestRepository


def _get_excel_path() -> str:
    return str(settings.resolved_excel_path)


def _make_graph_app_token_getter():
    """Return a callable that acquires a Graph app-only token via client credentials."""
    def getter() -> str | None:
        import msal
        msal_app = msal.ConfidentialClientApplication(
            settings.MICROSOFT_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}",
            client_credential=settings.MICROSOFT_CLIENT_SECRET,
        )
        result = msal_app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
        if not result:
            result = msal_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        return result.get("access_token") if result else None
    return getter


def get_graph_client():
    from app.repositories.graph_client import GraphClient
    return GraphClient(access_token_getter=_make_graph_app_token_getter())


class _LazyGraphClient:
    def __getattr__(self, name):
        return getattr(get_graph_client(), name)

graph_client = _LazyGraphClient()


def get_equipment_repo(db=None) -> EquipmentRepository:
    if settings.DATA_BACKEND == "excel":
        from app.repositories.excel_equipment import ExcelEquipmentRepository
        return ExcelEquipmentRepository(_get_excel_path())

    if settings.DATA_BACKEND == "microsoft_graph" and settings.graph_configured:
        from app.repositories.graph_client import GraphClient
        from app.repositories.graph_equipment import GraphEquipmentRepository
        graph_client = GraphClient(access_token_getter=_make_graph_app_token_getter())
        return GraphEquipmentRepository(graph_client)

    from app.repositories.sqlite_equipment import SQLiteEquipmentRepository
    return SQLiteEquipmentRepository(db)


def get_request_repo(db=None) -> RequestRepository:
    if settings.DATA_BACKEND == "excel":
        from app.repositories.excel_request import ExcelRequestRepository
        return ExcelRequestRepository(_get_excel_path())

    if settings.DATA_BACKEND == "microsoft_graph" and settings.graph_configured:
        from app.repositories.graph_client import GraphClient
        from app.repositories.graph_request import GraphRequestRepository
        graph_client = GraphClient(access_token_getter=_make_graph_app_token_getter())
        return GraphRequestRepository(graph_client)

    from app.repositories.sqlite_request import SQLiteRequestRepository
    return SQLiteRequestRepository(db)


def get_user_repo():
    from app.repositories.excel_user import ExcelUserRepository
    return ExcelUserRepository(_get_excel_path())

