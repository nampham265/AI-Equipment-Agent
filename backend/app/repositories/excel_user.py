"""ExcelUserRepository - data access layer for the Users worksheet in equipment_agent.xlsx."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from filelock import FileLock
import openpyxl

from app.models.excel_user import ExcelUserModel

_SHEET_NAME = "Users"
_REQUIRED_COLUMNS = ["UserEmail", "UserName", "Role", "IsActive"]
_ALLOWED_ROLES = {"USER", "MANAGER", "ADMIN"}

_WRITE_LOCK = threading.Lock()


def _is_truthy(val) -> bool:
    if val is True:
        return True
    if isinstance(val, str) and val.strip().upper() in ("TRUE", "1", "YES"):
        return True
    return False


class ExcelUserRepository:
    """Repository for managing application users in equipment_agent.xlsx."""

    def __init__(self, workbook_path: str) -> None:
        self._path = Path(workbook_path)
        self._lock_path = self._path.with_suffix(".lock")
        self._validate_workbook()

    # ------------------------------------------------------------------
    # Startup / Schema Validation
    # ------------------------------------------------------------------

    def _validate_workbook(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(
                f"Workbook không tồn tại: {self._path}. "
                "Kiểm tra EXCEL_DATA_PATH trong .env"
            )

        try:
            wb = openpyxl.load_workbook(self._path, read_only=True, data_only=True)
        except Exception as exc:
            raise RuntimeError(f"Không thể mở workbook {self._path}: {exc}") from exc

        if _SHEET_NAME not in wb.sheetnames:
            wb.close()
            raise ValueError(
                f"Workbook thiếu sheet '{_SHEET_NAME}'. "
                f"Các sheet hiện có: {wb.sheetnames}"
            )

        ws = wb[_SHEET_NAME]
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        headers = {str(c).strip() for c in first_row if c is not None}
        missing = set(_REQUIRED_COLUMNS) - headers
        wb.close()

        if missing:
            raise ValueError(
                f"Sheet '{_SHEET_NAME}' thiếu các cột: {missing}. "
                f"Các cột hiện có: {headers}"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_workbook(self) -> openpyxl.Workbook:
        return openpyxl.load_workbook(self._path, data_only=True)

    def _safe_save(self, wb: openpyxl.Workbook) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        wb.save(tmp_path)
        os.replace(tmp_path, self._path)

    def _col_index(self, ws) -> dict[str, int]:
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        return {str(h).strip(): i + 1 for i, h in enumerate(first_row) if h is not None}

    def _load_all_rows(self) -> list[ExcelUserModel]:
        wb = self._load_workbook()
        ws = wb[_SHEET_NAME]
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, ())
        col_idx = {str(h).strip(): i for i, h in enumerate(header_row) if h is not None}

        users: list[ExcelUserModel] = []
        for row in rows_iter:
            if not row:
                continue

            def cell(name: str) -> Optional[str]:
                idx = col_idx.get(name)
                if idx is None or idx >= len(row):
                    return None
                val = row[idx]
                return str(val).strip() if val is not None else None

            email = cell("UserEmail")
            if not email:
                continue

            name = cell("UserName") or ""
            role = (cell("Role") or "USER").upper()
            raw_active = row[col_idx["IsActive"]] if "IsActive" in col_idx and col_idx["IsActive"] < len(row) else True
            is_active = _is_truthy(raw_active)

            users.append(
                ExcelUserModel(
                    user_email=email,
                    user_name=name,
                    role=role,
                    is_active=is_active,
                )
            )

        wb.close()
        return users

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def get_by_email(self, email: str) -> Optional[ExcelUserModel]:
        """Look up user by email (case-insensitive)."""
        target = email.strip().lower()
        for user in self._load_all_rows():
            if user.user_email.strip().lower() == target:
                return user
        return None

    def list_all(self) -> list[ExcelUserModel]:
        """List all users in the Users sheet."""
        return self._load_all_rows()

    def get_all(self) -> list[ExcelUserModel]:
        """Alias for list_all."""
        return self.list_all()

    def count_active_admins(self) -> int:
        """Count total active ADMIN accounts in the sheet."""
        return sum(1 for u in self._load_all_rows() if u.is_admin and u.is_active)

    # ------------------------------------------------------------------
    # Public write operations (Thread-safe + Process-safe via FileLock)
    # ------------------------------------------------------------------

    def create(self, user: ExcelUserModel) -> ExcelUserModel:
        """Add a new user to the Users sheet.
        
        Validates email uniqueness and role (cannot create ADMIN directly).
        """
        email_clean = user.user_email.strip().lower()
        role_upper = user.role.strip().upper()

        if role_upper not in _ALLOWED_ROLES:
            raise ValueError(f"Vai trò không hợp lệ: '{user.role}'. Chỉ chấp nhận USER hoặc MANAGER.")

        with _WRITE_LOCK:
            with FileLock(str(self._lock_path), timeout=10):
                wb = self._load_workbook()
                ws = wb[_SHEET_NAME]
                col_idx = self._col_index(ws)

                # Check uniqueness
                email_col = col_idx.get("UserEmail")
                for row_num in range(2, ws.max_row + 1):
                    val = ws.cell(row_num, email_col).value
                    if val and str(val).strip().lower() == email_clean:
                        wb.close()
                        raise ValueError(f"Email '{user.user_email}' đã tồn tại trong hệ thống.")

                new_row = ws.max_row + 1
                ws.cell(new_row, col_idx["UserEmail"]).value = user.user_email.strip()
                ws.cell(new_row, col_idx["UserName"]).value = user.user_name.strip()
                ws.cell(new_row, col_idx["Role"]).value = role_upper
                ws.cell(new_row, col_idx["IsActive"]).value = "TRUE" if user.is_active else "FALSE"

                self._safe_save(wb)
                wb.close()

        return ExcelUserModel(
            user_email=user.user_email.strip(),
            user_name=user.user_name.strip(),
            role=role_upper,
            is_active=user.is_active,
        )

    def update_role(self, email: str, new_role: str) -> ExcelUserModel:
        """Change a user's role (USER <-> MANAGER).
        
        Protects the final active ADMIN from demotion.
        """
        email_clean = email.strip().lower()
        new_role_upper = new_role.strip().upper()

        if new_role_upper not in ("USER", "MANAGER"):
            raise ValueError(f"Vai trò chỉ có thể đổi thành USER hoặc MANAGER. Không thể gán '{new_role}'.")

        with _WRITE_LOCK:
            with FileLock(str(self._lock_path), timeout=10):
                wb = self._load_workbook()
                ws = wb[_SHEET_NAME]
                col_idx = self._col_index(ws)
                email_col = col_idx.get("UserEmail")
                role_col = col_idx.get("Role")
                active_col = col_idx.get("IsActive")

                target_row = None
                current_user = None

                # Count active admins to protect the last one
                active_admins = 0
                for row_num in range(2, ws.max_row + 1):
                    em = ws.cell(row_num, email_col).value
                    rl = ws.cell(row_num, role_col).value
                    act = ws.cell(row_num, active_col).value
                    is_act = _is_truthy(act)
                    is_adm = str(rl).strip().upper() == "ADMIN" if rl else False

                    if is_adm and is_act:
                        active_admins += 1

                    if em and str(em).strip().lower() == email_clean:
                        target_row = row_num
                        current_user = ExcelUserModel(
                            user_email=str(em).strip(),
                            user_name=str(ws.cell(row_num, col_idx["UserName"]).value or "").strip(),
                            role=str(rl).strip().upper() if rl else "USER",
                            is_active=is_act,
                        )

                if target_row is None or current_user is None:
                    wb.close()
                    raise ValueError(f"Không tìm thấy người dùng với email '{email}'.")

                # Guard: cannot demote the last active admin
                if current_user.is_admin and current_user.is_active and active_admins <= 1:
                    wb.close()
                    raise ValueError("Không thể hạ quyền Quản trị viên (ADMIN) cuối cùng đang hoạt động trong hệ thống.")

                ws.cell(target_row, role_col).value = new_role_upper
                self._safe_save(wb)
                wb.close()

                current_user.role = new_role_upper
                return current_user

    def set_active(self, email: str, is_active: bool) -> ExcelUserModel:
        """Activate or deactivate a user.
        
        Protects the final active ADMIN from deactivation.
        """
        email_clean = email.strip().lower()

        with _WRITE_LOCK:
            with FileLock(str(self._lock_path), timeout=10):
                wb = self._load_workbook()
                ws = wb[_SHEET_NAME]
                col_idx = self._col_index(ws)
                email_col = col_idx.get("UserEmail")
                role_col = col_idx.get("Role")
                active_col = col_idx.get("IsActive")

                target_row = None
                current_user = None

                active_admins = 0
                for row_num in range(2, ws.max_row + 1):
                    em = ws.cell(row_num, email_col).value
                    rl = ws.cell(row_num, role_col).value
                    act = ws.cell(row_num, active_col).value
                    is_act = _is_truthy(act)
                    is_adm = str(rl).strip().upper() == "ADMIN" if rl else False

                    if is_adm and is_act:
                        active_admins += 1

                    if em and str(em).strip().lower() == email_clean:
                        target_row = row_num
                        current_user = ExcelUserModel(
                            user_email=str(em).strip(),
                            user_name=str(ws.cell(row_num, col_idx["UserName"]).value or "").strip(),
                            role=str(rl).strip().upper() if rl else "USER",
                            is_active=is_act,
                        )

                if target_row is None or current_user is None:
                    wb.close()
                    raise ValueError(f"Không tìm thấy người dùng với email '{email}'.")

                # Guard: cannot deactivate the last active admin
                if not is_active and current_user.is_admin and active_admins <= 1:
                    wb.close()
                    raise ValueError("Không thể vô hiệu hóa Quản trị viên (ADMIN) cuối cùng đang hoạt động trong hệ thống.")

                ws.cell(target_row, active_col).value = "TRUE" if is_active else "FALSE"
                self._safe_save(wb)
                wb.close()

                current_user.is_active = is_active
                return current_user
