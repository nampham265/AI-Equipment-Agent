"""Tests for ExcelUserRepository - Users sheet in equipment_agent.xlsx."""
from __future__ import annotations

from pathlib import Path
import pytest
import openpyxl

from app.models.excel_user import ExcelUserModel
from app.repositories.excel_user import ExcelUserRepository


@pytest.fixture
def temp_workbook(tmp_path) -> Path:
    wb_path = tmp_path / "test_equipment.xlsx"
    wb = openpyxl.Workbook()
    # Users sheet
    ws = wb.active
    ws.title = "Users"
    ws.append(["UserEmail", "UserName", "Role", "IsActive"])
    ws.append(["admin@example.com", "Admin User", "ADMIN", "TRUE"])
    ws.append(["manager@example.com", "Manager User", "MANAGER", "TRUE"])
    ws.append(["user@example.com", "Regular User", "USER", "TRUE"])
    ws.append(["inactive@example.com", "Inactive User", "USER", "FALSE"])
    wb.save(wb_path)
    wb.close()
    return wb_path


class TestExcelUserRepository:
    def test_list_all(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        users = repo.list_all()
        assert len(users) == 4
        emails = {u.user_email for u in users}
        assert "admin@example.com" in emails
        assert "manager@example.com" in emails
        assert "user@example.com" in emails

    def test_get_by_email_case_insensitive(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        admin = repo.get_by_email("ADMIN@EXAMPLE.COM")
        assert admin is not None
        assert admin.user_name == "Admin User"
        assert admin.role == "ADMIN"
        assert admin.is_active is True
        assert admin.is_admin is True

        user = repo.get_by_email("user@example.com")
        assert user is not None
        assert user.is_user is True

        none_user = repo.get_by_email("unknown@example.com")
        assert none_user is None

    def test_create_user_success(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        new_u = ExcelUserModel(
            user_email="newbie@example.com",
            user_name="Newbie",
            role="USER",
            is_active=True,
        )
        created = repo.create(new_u)
        assert created.user_email == "newbie@example.com"
        assert created.role == "USER"

        # Verify persisted
        found = repo.get_by_email("newbie@example.com")
        assert found is not None
        assert found.user_name == "Newbie"

    def test_create_duplicate_email_fails(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        dup = ExcelUserModel(
            user_email="admin@example.com",
            user_name="Another Admin",
            role="USER",
            is_active=True,
        )
        with pytest.raises(ValueError, match="đã tồn tại"):
            repo.create(dup)

    def test_create_invalid_role_fails(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        invalid = ExcelUserModel(
            user_email="hacker@example.com",
            user_name="Hacker",
            role="SUPERADMIN",
            is_active=True,
        )
        with pytest.raises(ValueError, match="Vai trò không hợp lệ"):
            repo.create(invalid)

    def test_update_role_user_to_manager(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        updated = repo.update_role("user@example.com", "MANAGER")
        assert updated.role == "MANAGER"

        # Verify persisted
        found = repo.get_by_email("user@example.com")
        assert found.role == "MANAGER"

    def test_guard_cannot_demote_last_active_admin(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        assert repo.count_active_admins() == 1
        with pytest.raises(ValueError, match="Không thể hạ quyền Quản trị viên"):
            repo.update_role("admin@example.com", "MANAGER")

    def test_guard_cannot_deactivate_last_active_admin(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        with pytest.raises(ValueError, match="Không thể vô hiệu hóa Quản trị viên"):
            repo.set_active("admin@example.com", False)

    def test_set_active_toggle(self, temp_workbook):
        repo = ExcelUserRepository(str(temp_workbook))
        updated = repo.set_active("user@example.com", False)
        assert updated.is_active is False

        re_active = repo.set_active("user@example.com", True)
        assert re_active.is_active is True

    def test_missing_sheet_raises_error(self, tmp_path):
        bad_path = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        wb.active.title = "Other"
        wb.save(bad_path)
        wb.close()

        with pytest.raises(ValueError, match="thiếu sheet 'Users'"):
            ExcelUserRepository(str(bad_path))
