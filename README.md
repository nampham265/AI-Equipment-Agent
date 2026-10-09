# Trợ lý Thiết bị Kỹ thuật — AI Equipment Agent (Excel-Backed MVP)

Ứng dụng web Trợ lý AI quản lý thiết bị kỹ thuật, hỗ trợ tra cứu thiết bị, gửi yêu cầu mượn và cung cấp dashboard duyệt yêu cầu kèm gợi ý mức độ ưu tiên từ AI cho Quản lý.

Trong phiên bản MVP này, **hệ thống sử dụng trực tiếp file Excel cục bộ (`backend/data/equipment_agent.xlsx`) làm cơ sở dữ liệu chính** (thay vì SQLite hay Microsoft Graph).

---

## 1. Kiến trúc hệ thống

```text
Frontend (React + TypeScript + Vite)
   ↓ HTTP / REST API (port 5173 ↔ port 8000)
Backend API (FastAPI + Python 3.11)
   ↓ Repository Layer (ExcelEquipmentRepository, ExcelRequestRepository)
Excel Workbook (backend/data/equipment_agent.xlsx via openpyxl + FileLock)
```

| Thành phần | Công nghệ / Vị trí | Mô tả |
|------------|---------------------|-------|
| **Frontend** | React 18, TypeScript, Vite | Giao diện tiếng Việt chuẩn, hỗ trợ Chat Agent, Form mượn, Danh sách yêu cầu, Dashboard Quản lý |
| **Backend API** | FastAPI, Python 3.11 | Xác thực session cookie, kiểm soát quyền hạn (RBAC), API endpoints |
| **Data Store** | `backend/data/equipment_agent.xlsx` | Workbook Excel thật gồm 2 sheets: `Equipment` và `Equipment_Requests` |
| **Data Access** | `openpyxl` + `filelock` | Ghi/đọc an toàn theo tiến trình, safe-save atomic rename |
| **AI Priority** | Demo Provider hoặc Google Gemini | Gợi ý mức độ ưu tiên (`High`, `Medium`, `Low`, `Needs review`). Quản lý đưa ra quyết định cuối cùng |
| **Thông báo** | Console / Email (tuỳ chọn) | Ghi nhận trung thực trạng thái gửi thông báo |

---

## 2. Cấu trúc Workbook Excel (`backend/data/equipment_agent.xlsx`)

File Excel gồm đúng 2 worksheet:

### Sheet 1: `Equipment` (Danh mục thiết bị — Nguồn chân lý)
Dữ liệu thiết bị thật (116 mục), ứng dụng chỉ đọc (`read-only`):
- `EquipmentID`: Mã thiết bị (ví dụ: `TU1-001`)
- `EquipmentName`: Tên thiết bị
- `Category`: Phân loại
- `Description`: Mô tả chi tiết kỹ thuật
- `Quantity`: Tổng số lượng trong kho
- `Unit`: Đơn vị tính (cái, bộ, cuộn, ...)
- `Location`: Vị trí lưu kho (Tủ 1, ...)

### Sheet 2: `Equipment_Requests` (Danh sách yêu cầu mượn)
Được ghi/cập nhật tự động bởi backend khi người dùng gửi yêu cầu hoặc quản lý thao tác:
- `RequestID`: Mã yêu cầu sinh tự động (định dạng `REQ-YYYYMMDD-XXXXXX`)
- `RequesterEmail`: Email người gửi (lấy từ phiên đăng nhập)
- `RequesterName`: Tên người gửi (lấy từ phiên đăng nhập)
- `Project`: Tên dự án cần thiết bị
- `EquipmentID`: Mã thiết bị mượn
- `EquipmentName`: Tên thiết bị tại thời điểm tạo yêu cầu
- `Quantity`: Số lượng mượn (> 0)
- `NeededFrom`: Ngày bắt đầu cần dùng (YYYY-MM-DD)
- `NeededTo`: Ngày dự kiến hoàn trả (YYYY-MM-DD, >= NeededFrom)
- `Purpose`: Mục đích sử dụng
- `PriorityLevel`: Mức ưu tiên do AI đề xuất (`Critical`, `High`, `Medium`, `Low`, `Needs review`)
- `PriorityReason`: Lý do giải thích của AI (không bị sửa đổi sau khi tạo)
- `FinalPriorityLevel`: Mức ưu tiên chính thức do Quản lý xác nhận
- `PriorityReviewedBy`: Email của Quản lý đã xác nhận mức ưu tiên
- `PriorityReviewedAt`: Thời điểm Quản lý xác nhận (ISO timestamp)
- `Status`: Trạng thái (`Pending`, `Approved`, `Rejected`, `Borrowed`, `Returned`, `Cancelled`)
- `ReturnCondition`: Tình trạng khi hoàn trả (`Good`, `Normal`, `Damaged`, ...)
- `ReturnConditionNote`: Ghi chú tình trạng thiết bị khi trả
- `ReturnedAt`: Thời điểm trả thiết bị (ISO timestamp)
- `CreatedAt`: Thời điểm tạo yêu cầu (ISO timestamp)
- `UpdatedAt`: Thời điểm cập nhật cuối cùng (ISO timestamp)

### Sheet 3: `Users` (Danh sách tài khoản & Phân quyền)
Lưu trữ thông tin người dùng và phân quyền RBAC:
- `UserEmail`: Email đăng nhập
- `UserName`: Họ tên người dùng
- `Role`: Vai trò (`USER`, `MANAGER`, `ADMIN`)
- `IsActive`: Trạng thái kích hoạt tài khoản (`TRUE` / `FALSE`)

---

## 3. Biến môi trường (`.env`)

Tạo file `.env` tại thư mục gốc của dự án:

```env
# Môi trường chung
APP_ENV=development
APP_SECRET_KEY=dev-secret-key-equipment-agent-v1-super-secure
FRONTEND_ORIGIN=http://localhost:5173

# Cấu hình lưu trữ chính: "excel"
DATA_BACKEND=excel
EXCEL_DATA_PATH=backend/data/equipment_agent.xlsx

# Danh sách email Quản lý được phép duyệt (ngăn cách bởi dấu phẩy)
MANAGER_EMAILS=manager@company.com

# Tích hợp AI Gemini (tuỳ chọn - để trống sẽ dùng Demo Provider an toàn)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
ALLOW_INVENTORY_DATA_TO_GEMINI=false

# Thông báo Email (tuỳ chọn)
EMAIL_NOTIFICATIONS_ENABLED=false
```

> **Lưu ý:** Trong MVP hiện tại, **không cần cấu hình Microsoft Graph hay SharePoint**. File Excel là nguồn dữ liệu duy nhất đang hoạt động.

---

## 4. Hướng dẫn chạy ứng dụng

### Bước 1: Cài đặt thư viện

```powershell
# Cài đặt Python dependencies
cd backend
python3.11 -m pip install -r requirements.txt

# Cài đặt Node dependencies
cd ..\frontend
npm install
```

### Bước 2: Chạy Backend (Terminal 1)

```powershell
cd backend
python3.11 -m uvicorn app.main:app --reload --port 8000
```
Backend sẽ kiểm tra tính toàn vẹn của file Excel trên đường dẫn cấu hình và báo cáo `Excel workbook validated successfully`.

### Bước 3: Chạy Frontend (Terminal 2)

```powershell
cd frontend
npm run dev
```

Truy cập: **http://localhost:5173**

---

## 5. Quy trình trải nghiệm và kiểm thử

### Kịch bản 1: Đăng nhập & Tạo yêu cầu mượn
1. Truy cập `http://localhost:5173`.
2. Ở chế độ `APP_ENV=development`, giao diện đăng nhập cung cấp 2 nút đăng nhập nhanh:
   - **Đăng nhập với vai trò Người dùng** (`nguyen.van.a@company.com`)
   - **Đăng nhập với vai trò Quản lý** (`manager@company.com`)
3. Đăng nhập người dùng, vào giao diện Chat hoặc Tra cứu thiết bị.
4. Gửi tin nhắn mượn thiết bị (ví dụ: *"Tôi muốn mượn thiết bị TU1-001"*).
5. Điền form yêu cầu (Dự án, Số lượng, Ngày mượn, Ngày trả, Mục đích) và nhấn **Gửi yêu cầu**.
6. Yêu cầu được ghi vào file `equipment_agent.xlsx`, hiển thị mã `REQ-YYYYMMDD-XXXXXX` với trạng thái `Pending` và `FinalPriorityLevel` để trống.

### Kịch bản 2: Quản lý đánh giá ưu tiên & Phê duyệt
1. Đăng xuất và đăng nhập lại bằng tài khoản **Quản lý** (`manager@company.com`).
2. Vào tab **Quản lý**:
   - Xem danh sách yêu cầu chờ duyệt (`Pending`).
   - Mở chi tiết yêu cầu để xem **Ưu tiên do AI đề xuất** kèm giải thích.
   - Tại mục **Mức ưu tiên chính thức (Quản lý duyệt)**, chọn mức ưu tiên (`High` / `Medium` / `Low` / `Needs review`) và nhấn **Lưu mức ưu tiên**. Hệ thống sẽ ghi nhận `FinalPriorityLevel`, `PriorityReviewedBy` và `PriorityReviewedAt` mà không làm thay đổi đề xuất ban đầu của AI.
   - Nhấn **Duyệt** hoặc **Từ chối**.
   - Khi bàn giao thiết bị, nhấn **Bàn giao** (chuyển sang `Borrowed`).

### Kịch bản 3: Người dùng trả thiết bị
1. Người dùng vào tab **Yêu cầu của tôi**, theo dõi trạng thái đã cập nhật `Approved` hoặc `Borrowed`.
2. Khi dùng xong, nhấn **Đã trả thiết bị** (chuyển sang `Returned`).

---

## 6. Giới hạn đồng thời và Sao lưu dữ liệu

- **Giới hạn đồng thời của Excel (Concurrency limitation):**
  - Giải pháp này được thiết kế cho **một backend instance duy nhất** và số lượng người dùng vừa phải trong nội bộ.
  - Mỗi thao tác ghi được bảo vệ bởi cả `threading.Lock` (trong tiến trình) và `filelock.FileLock` (giữa các tiến trình) với timeout 10 giây.
  - Quá trình ghi sử dụng file tạm và `os.replace` để tránh làm hỏng file Excel khi có sự cố bất ngờ.
- **Cách sao lưu (Backup workbook):**
  - Chỉ cần copy file `backend/data/equipment_agent.xlsx` sang thư mục lưu trữ dự phòng khi backend không trong trạng thái ghi, ví dụ:
    ```powershell
    Copy-Item backend\data\equipment_agent.xlsx backend\data\equipment_agent_backup.xlsx
    ```

---

## 7. Chạy bộ kiểm thử tự động (Automated Tests)

Chạy toàn bộ 160 bài kiểm thử tự động của backend:

```powershell
cd backend
python3.11 -m pytest tests/ -v
```

Kết quả: **160/160 tests PASSED (100%)**, bao gồm:
- `test_agent_architecture_upgrade.py`: Kiểm tra 5 capability tools mới, RBAC admin, group reference và failover LLM.
- `test_my_requests_layout.py`: Kiểm tra CSS contract, filter trạng thái (`Approved`, `Pending`, `Borrowed`) và follow-up người quá hạn.
- `test_agent_remediation.py`: Kiểm tra hồi quy phân loại, tìm kiếm đa thuộc tính, bảo vệ không tự duyệt.
- `test_agent_orchestrator.py`: Kiểm tra merging form state, tham chiếu thứ tự, tính thiếu hụt số lượng.
- `test_agent_conversation.py`: Kiểm tra làm rõ thông tin, phân trang xem tiếp, truy vấn vị trí.
- `test_conflict_engine.py`: Kiểm tra engine phát hiện xung đột lịch, deduplication cặp duy nhất và chuẩn hóa KPI.
- `test_return_flow.py`: Kiểm tra luồng trả thiết bị, đánh giá tình trạng hao mòn và phân quyền.
- `test_role_authorization.py`: Kiểm tra phân quyền đa vai trò (USER, MANAGER, ADMIN), bảo vệ không cho tự duyệt đơn của chính mình.
- `test_excel_repository.py`: Kiểm tra tính toàn vẹn, khả năng đọc/ghi an toàn của file Excel.
- `test_excel_user_repository.py`: Kiểm tra quản lý tài khoản người dùng trên worksheet Users.
- `test_excel_api.py`: Kiểm tra luồng gọi API end-to-end với dữ liệu Excel.
- `test_availability.py`: Kiểm tra thuật toán tính toán độ khả dụng theo khung thời gian.
- `test_priority_validation.py`: Kiểm tra schema và tính an toàn của đánh giá AI.
- `test_state_transitions.py`: Kiểm tra máy trạng thái (state machine) nghiêm ngặt.
- `test_api_requests.py`: Kiểm tra quyền hạn và bảo mật endpoint.
