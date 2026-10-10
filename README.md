# Trợ lý Thiết bị Kỹ thuật — AI Equipment Agent V1

Ứng dụng web Trợ lý AI hỗ trợ kỹ sư và nhân viên tra cứu thiết bị kỹ thuật, kiểm tra tính khả dụng, lập yêu cầu mượn/trả qua giao diện hội thoại tự nhiên, đồng thời cung cấp Dashboard cho Quản lý (Manager) xem xét và phê duyệt với mức độ ưu tiên do AI gợi ý.

Hệ thống sử dụng trực tiếp cơ sở dữ liệu Excel cục bộ ([backend/data/equipment_agent.xlsx](backend/data/equipment_agent.xlsx)) kết hợp cơ chế khóa ghi an toàn (`filelock`) và bộ định tuyến AI có cấu trúc (Google Gemini).

---

## 1. Tính năng nổi bật

- **Tra cứu thiết bị bằng ngôn ngữ tự nhiên:**
  - Hỗ trợ tìm kiếm theo nhiều đặc tính kỹ thuật: tên, loại, kích thước (`4.2mm`, `3mm`), số chân (`16pin`, `24pos`), góc vuông (`R/A`), kiểu chân (`SMD`), màu sắc (`đỏ`, `đen`), vị trí tủ (`Tủ 1`, `Tủ 2`, `EBS_LAB`).
  - Phân biệt rõ ràng giữa thiết bị chính và phụ kiện (ví dụ: cáp banana jumper vs cuộn nhựa PLA).

- **Kiểm tra khả dụng & Tính toán thiếu hụt (Shortage):**
  - Tự động trừ đi số lượng của các đơn đã duyệt/đang mượn thực tế để tính toán số lượng khả dụng.
  - Phản hồi tính toán toán học chính xác và ghi nhớ ngữ cảnh qua nhiều lượt chat (ví dụ: *"Nếu mình cần mượn 30 cái thì sao?"* $\rightarrow$ báo thiếu 7 cái $\rightarrow$ *"Vậy tạo đơn mượn 5 cái"* $\rightarrow$ mở form mượn 5 cái).

- **Hỗ trợ quy trình Mượn & Hoàn trả qua Chat:**
  - Mở biểu mẫu (prefill modal) tự động điền sẵn mã thiết bị, tên, số lượng, dự án và ngày mượn.
  - Hỗ trợ quy trình trả thiết bị: liệt kê các đơn đang mượn, giải quyết tham chiếu thứ tự (*"Tôi muốn trả cái thứ 1"*) hoặc tên thiết bị (*"Mình muốn trả Conn 4.2mm"*), tiếp nhận ghi chú tình trạng hao mòn.

- **Báo cáo tồn kho chuyên biệt:**
  - Phân biệt chính xác giữa thiết bị **đã hết hàng** (`Quantity == 0`) và thiết bị **sắp hết** (mặc định $\le 5$ cái, hoặc theo toán tử nghiêm ngặt như *"dưới 5 cái"*, *"5 cái trở xuống"*).
  - Tự động định dạng bảng Markdown với cơ chế thoát ký tự đặc biệt (`\|`).

- **Phân quyền người dùng (RBAC) & Phê duyệt:**
  - **Người dùng (USER):** Chỉ tra cứu kho và xem các đơn mượn do chính mình tạo.
  - **Quản lý (MANAGER):** Xem toàn bộ đơn kho, lọc theo người mượn, xem đánh giá ưu tiên từ AI (`Critical`, `High`, `Medium`, `Low`, `Needs review`), duyệt/từ chối đơn. Áp dụng quy tắc chống tự duyệt đơn của chính mình.
  - **Quản trị viên (ADMIN):** Quản lý tài khoản và phân quyền người dùng.

---

## 2. Kiến trúc & Công nghệ

```text
Frontend (React + TypeScript + Vite)
   │ (HTTP / REST API : port 5173 ↔ port 8000)
   ▼
Backend API (FastAPI + Python 3.11)
   ├── AI Router: Google Gemini (gemini-3.1-flash-lite) + Deterministic Fallback
   ├── State Manager & Grounded Tools Engine
   └── Data Access Layer (openpyxl + filelock)
         ▼
      Excel Workbook (backend/data/equipment_agent.xlsx)
         ├── Sheet "Equipment" (Danh mục thiết bị)
         ├── Sheet "Equipment_Requests" (Lịch sử & Yêu cầu mượn/trả)
         └── Sheet "Users" (Tài khoản & Phân quyền)
```

---

## 3. Cấu hình môi trường (`.env`)

Tạo file `.env` tại thư mục gốc của dự án:

```env
APP_ENV=development
APP_SECRET_KEY=dev-secret-key-equipment-agent-v1-super-secure
FRONTEND_ORIGIN=http://localhost:5173

# Cấu hình lưu trữ chính: Excel
DATA_BACKEND=excel
EXCEL_DATA_PATH=backend/data/equipment_agent.xlsx

# Định tuyến AI (sử dụng Gemini Flash Lite)
AGENT_ROUTING_MODE=llm_primary
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
ALLOW_INVENTORY_DATA_TO_GEMINI=false

# Phân quyền Quản lý
MANAGER_EMAILS=manager@company.com
```

*(Lưu ý: Nếu không có `GEMINI_API_KEY` hoặc mất kết nối mạng, hệ thống tự động kích hoạt bộ định tuyến nội bộ tất định, ứng dụng vẫn hoạt động 100%).*

---

## 4. Hướng dẫn cài đặt & Khởi chạy

### Bước 1: Cài đặt thư viện

```powershell
# Cài đặt backend
cd backend
python3.11 -m pip install -r requirements.txt

# Cài đặt frontend
cd ..\frontend
npm install
```

### Bước 2: Chạy Backend (Terminal 1)

```powershell
cd backend
python3.11 -m uvicorn app.main:app --reload --port 8000
```

### Bước 3: Chạy Frontend (Terminal 2)

```powershell
cd frontend
npm run dev
```

Truy cập ứng dụng tại: **http://localhost:5173**  
*(Trong môi trường phát triển, màn hình đăng nhập cung cấp sẵn nút đăng nhập nhanh với vai trò **Người dùng** hoặc **Quản lý**).*

---

## 5. Kiểm thử tự động (Automated Tests)

Chạy toàn bộ bộ kiểm thử tự động của backend:

```powershell
cd backend
python3.11 -m pytest tests/ -q
```

Kết quả: **246/246 tests PASSED (100%)**, bao gồm kiểm thử phân loại ý định, hội thoại ngữ cảnh, thuật toán khả dụng, phân quyền RBAC, kiểm tra toàn vẹn dữ liệu Excel và các kịch bản hồi quy.
