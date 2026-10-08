from fastapi import APIRouter
import time
from app.core.config import settings
from app.repositories.factory import graph_client

router = APIRouter(tags=["health"])

@router.get("/api/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}


def _check_gemini() -> dict:
    if not settings.gemini_configured:
        return {"status": "not_configured", "model": settings.GEMINI_MODEL}
        
    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        models_to_try = [settings.GEMINI_MODEL, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
        last_error = ""
        for m in models_to_try:
            try:
                res = client.models.generate_content(
                    model=m,
                    contents="ping"
                )
                if res.text:
                    return {"status": "connected", "model": m}
            except Exception as ex:
                last_error = str(ex)
                continue
        return {"status": "error", "model": settings.GEMINI_MODEL, "error": last_error or "Empty response"}
    except Exception as e:
        return {"status": "error", "model": settings.GEMINI_MODEL, "error": str(e)}

def _check_graph() -> dict:
    if not settings.graph_configured:
        return {
            "status": "not_configured",
            "site": "not_configured",
            "equipment_list": "not_configured",
            "requests_list": "not_configured"
        }
        
    result = {
        "status": "connected",
        "site": "found",
        "equipment_list": "not_found",
        "requests_list": "not_found"
    }
    
    try:
        # Check site
        site_res = graph_client.get(f"/sites/{settings.MICROSOFT_SITE_ID}")
        if "id" not in site_res:
            result["site"] = "not_found"
            result["status"] = "error"
            return result
            
        # Check equipment list
        try:
            eq_res = graph_client.get(f"/sites/{settings.MICROSOFT_SITE_ID}/lists/{settings.MICROSOFT_EQUIPMENT_LIST_ID}")
            if "id" in eq_res:
                result["equipment_list"] = "found"
        except Exception:
            pass
            
        # Check requests list
        try:
            req_res = graph_client.get(f"/sites/{settings.MICROSOFT_SITE_ID}/lists/{settings.MICROSOFT_REQUESTS_LIST_ID}")
            if "id" in req_res:
                result["requests_list"] = "found"
        except Exception:
            pass
            
        if result["equipment_list"] == "not_found" or result["requests_list"] == "not_found":
            result["status"] = "partial_error"
            
    except Exception as e:
        result["status"] = "error"
        result["error_detail"] = str(e)
        
    return result

def _check_email() -> dict:
    if settings.EMAIL_NOTIFICATIONS_ENABLED:
        return {"status": "configured"}
    return {"status": "not_configured"}

def _check_excel() -> dict:
    if settings.DATA_BACKEND != "excel":
        return {"status": "not_configured"}
    try:
        import openpyxl
        path = settings.resolved_excel_path
        if not path.exists():
            return {"status": "error", "detail": f"File không tồn tại: {path}"}
        wb = openpyxl.load_workbook(path, read_only=True)
        sheets = wb.sheetnames
        wb.close()
        if "Equipment" not in sheets or "Equipment_Requests" not in sheets:
            return {"status": "error", "detail": f"Thiếu sheets. Hiện có: {sheets}"}
        return {"status": "connected", "path": str(path)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/api/health/integrations")
def integration_health():
    """Reports actual status of Excel, Gemini, Graph, email. No secrets exposed."""
    return {
        "excel": _check_excel(),
        "gemini": _check_gemini(),
        "microsoft_graph": _check_graph(),
        "email": _check_email(),
    }
