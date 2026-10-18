# Trợ lý Thiết bị Kỹ thuật — AI Equipment Agent V1

Ứng dụng web Trợ lý AI thông minh hỗ trợ kỹ sư và nhân viên kỹ thuật tra cứu linh kiện/thiết bị trong kho, kiểm tra số lượng tồn khả dụng theo thời gian thực, lập yêu cầu mượn/trả qua giao diện hội thoại tự nhiên, đồng thời cung cấp Dashboard chuyên dụng cho Quản lý (Manager) xem xét, phê duyệt yêu cầu với mức độ ưu tiên và bằng chứng khách quan do AI đề xuất.

Dự án được xây dựng theo kiến trúc kết hợp **Hybrid AI - Deterministic Architecture** (kết hợp suy luận ngôn ngữ tự nhiên của LLM với thuật toán toán học tất định), sử dụng trực tiếp cơ sở dữ liệu Excel nội bộ ([`backend/data/equipment_agent.xlsx`](backend/data/equipment_agent.xlsx)) kết hợp cơ chế khóa ghi an toàn (`filelock`) và bộ định tuyến Google Gemini (`gemini-3.1-flash-lite`).

---

## 1. Kiến trúc Tổng thể & Công nghệ

```text
┌────────────────────────────────────────────────────────────────────────┐
│               FRONTEND: React 18 + TypeScript + Vite                   │
│   • Chat Assistant UI (Hội thoại tự nhiên, Prefill Modal, Form mượn)  │
│   • Trang Đơn của tôi (Theo dõi trạng thái, lý do từ chối, nút Hủy)    │
│   • Manager Dashboard (Duyệt đơn, Từ chối kèm lý do, Hoàn trả một phần)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST API (Port 5173 ↔ 8000)
┌───────────────────────────────────▼────────────────────────────────────┐
│                  BACKEND: FastAPI + Python 3.11                        │
│   ├── AI Router: Google Gemini (gemini-3.1-flash-lite)                 │
│   │   └── Fallback: Rule-Based Keyword Router (chạy khi offline)       │
│   ├── AI Priority Provider: Thẩm định mức ưu tiên & Bằng chứng khách quan│
│   ├── State Manager: Quản lý ngữ cảnh hội thoại đa lượt               │
│   ├── Availability Service: Thuật toán tính tồn kho giao cắt thời gian│
│   └── Approval Service: Quản lý State Machine & Xử lý Hoàn trả 1 phần │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ openpyxl + filelock (Đồng bộ an toàn)
┌───────────────────────────────────▼────────────────────────────────────┐
│         DATABASE: Excel Workbook (backend/data/equipment_agent.xlsx)    │
│   • Sheet "Equipment": 117 dòng linh kiện & thông số kỹ thuật          │
│   • Sheet "Equipment_Requests": 42 dòng đơn mượn/trả & lịch sử duyệt   │
│   • Sheet "Users": 13 tài khoản người dùng & quản lý phân quyền        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tính năng Cốt lõi & Điểm nổi bật

1. **Tra cứu đa thuộc tính kỹ thuật bằng ngôn ngữ tự nhiên:**
   - Tìm kiếm kết hợp: mã thiết bị (`TU1-001`), chủng loại, kích thước (`4.2mm`, `3mm`), số chân (`10 chân`, `16pin`, `24pos`), góc cắm (`R/A`, `bẻ góc`), kiểu chân (`SMD`, `DIP`), màu sắc (`đỏ`, `đen`), vị trí tủ (`Tủ 1`, `Tủ 2`, `EBS_LAB`).
   - Phân biệt chính xác giữa thiết bị chính và phụ kiện (ví dụ: dây cắm banana jumper vs cuộn nhựa in 3D).

2. **Kiểm tra khả dụng & Tính toán thiếu hụt (Shortage Calculation):**
   - Không lấy tồn tổng để trả lời; tự động trừ các đơn đã duyệt (`Approved`) hoặc đang mượn (`Borrowed`) giao cắt theo khoảng thời gian yêu cầu.
   - Tính toán thiếu hụt toán học chính xác: Nếu yêu cầu 30 cái mà chỉ còn 23 cái khả dụng, Agent sẽ báo thiếu chính xác 7 cái và gợi ý số lượng hợp lệ.

3. **Hội thoại kế thừa ngữ cảnh đa lượt (Multi-turn Context):**
   - Kế thừa đại từ thay thế (*"cái đó"*, *"nó"*, *"thiết bị này"*) và tham chiếu số thứ tự (*"cái thứ 1"*, *"món thứ 2"*).
   - Tự động nhớ thiết bị đang hỏi ở lượt trước để mở form mượn ở lượt sau mà người dùng không cần gõ lại mã.

4. **Báo cáo tồn kho chuyên biệt:**
   - Phân biệt rõ ràng giữa thiết bị **đã hết hàng** (`Quantity == 0`) và thiết bị **sắp hết** (mặc định $\le 5$ cái, hoặc theo toán tử nghiêm ngặt như *"dưới 5 cái"*, *"5 cái trở xuống"*).
   - Định dạng bảng Markdown trực quan, tự động xử lý ký tự đặc biệt.

5. **Tìm nguồn cung ứng ngoài thị trường (External Sourcing):**
   - Khi thiết bị hết hàng hoặc người dùng muốn mua mới, Agent tự động tổng hợp bảng danh sách nhà phân phối chính hãng (DigiKey, Mouser, LCSC, Thế Giới IC, Hshop), cung cấp link tra cứu trực tiếp và khung giá tham khảo.

6. **Quy trình Quản lý & Phê duyệt (Human-in-the-loop):**
   - AI chỉ giữ vai trò hỗ trợ thẩm định (đề xuất `Critical`, `High`, `Medium`, `Low`, `Needs review` kèm bằng chứng). Quản lý là người duy nhất có quyền quyết định.
   - **Lưu lý do từ chối độc lập (`rejection_reason`):** Quản lý từ chối đơn bắt buộc nhập lý do; lý do này được lưu vào cột riêng biệt trong Excel và hiển thị rõ ràng cho kỹ sư, không ghi đè lên lý do đánh giá ưu tiên của AI.
   - **Hoàn trả một phần (Partial Return):** Cho phép mượn 5 trả 2; hệ thống tự động tách đơn gốc còn 3 (`Borrowed`) và tạo đơn mới ghi nhận 2 (`Returned`), đồng thời cập nhật tức thời số lượng khả dụng của kho.

---

## 3. Dữ liệu Sẵn có (Out-of-the-Box)

Dự án đã đính kèm sẵn tệp cơ sở dữ liệu Excel [`backend/data/equipment_agent.xlsx`](backend/data/equipment_agent.xlsx) trong repository Git:

| Tên Sheet | Số dòng dữ liệu | Mục đích sử dụng |
| :--- | :---: | :--- |
| **`Equipment`** | **117 dòng** | Danh mục thiết bị kỹ thuật mẫu: đầu cắm, cảm biến, bo mạch ECU, cáp đo... |
| **`Equipment_Requests`** | **42 dòng** | Lịch sử đơn mượn/trả mẫu ở các trạng thái `Pending`, `Approved`, `Borrowed`, `Returned`, `Rejected` |
| **`Users`** | **13 dòng** | Danh sách tài khoản kỹ sư, quản lý phòng lab và admin để thử nghiệm phân quyền |

> [!TIP]
> **Không cần cài đặt Database:** Người dùng clone project về có thể khởi chạy và thử nghiệm ngay lập tức mà không cần cài đặt PostgreSQL, MySQL hay chạy migration. Cơ chế `filelock` bảo đảm an toàn khi đọc/ghi đồng thời trên file Excel.

---

## 4. Hướng dẫn Cài đặt & Khởi chạy Chi tiết

### Yêu cầu môi trường
- **Python:** Phiên bản `3.11` (khuyến nghị `3.11.9`)
- **Node.js:** Phiên bản `18.x` hoặc `20.x` (kèm `npm`)
- **Hệ điều hành:** Windows, macOS hoặc Linux

---

### Bước 1: Clone Repository
```powershell
git clone <repository-url>
cd ai-equipment-agent-v1
```

---

### Bước 2: Thiết lập Biến môi trường (`.env`)
Sao chép tệp mẫu `.env.example` thành `.env` tại thư mục gốc của dự án:
```powershell
cp .env.example .env
```

Nội dung file `.env` cơ bản:
```env
APP_ENV=development
APP_SECRET_KEY=dev-secret-key-equipment-agent-v1-super-secure
FRONTEND_ORIGIN=http://localhost:5173

# Cấu hình lưu trữ chính: Excel
DATA_BACKEND=excel
EXCEL_DATA_PATH=backend/data/equipment_agent.xlsx

# Định tuyến AI (sử dụng Gemini Flash-Lite)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
AGENT_ROUTING_MODE=llm_primary
ALLOW_INVENTORY_DATA_TO_GEMINI=false

# Phân quyền Quản lý
MANAGER_EMAILS=manager.lab@bosch.com,manager@company.com
```

> [!NOTE]
> **Chạy không cần API Key (Offline Fallback):** Nếu bạn để trống `GEMINI_API_KEY`, ứng dụng vẫn khởi động và hoạt động bình thường 100%. Hệ thống sẽ tự động kích hoạt **Rule-based Keyword Router** nội bộ và **Demo AI Provider** mà không phát sinh bất kỳ lỗi nào.

---

### Bước 3: Cài đặt và Khởi chạy Backend

Mở một cửa sổ Terminal (Terminal 1):
```powershell
# Di chuyển vào thư mục backend
cd backend

# Cài đặt thư viện Python
python3.11 -m pip install -r requirements.txt

# Khởi chạy server FastAPI
python3.11 -m uvicorn app.main:app --reload --port 8000
```
Backend API sẽ hoạt động tại: **`http://localhost:8000`**  
Tài liệu Swagger API: **`http://localhost:8000/docs`**

---

### Bước 4: Cài đặt và Khởi chạy Frontend

Mở cửa sổ Terminal thứ hai (Terminal 2):
```powershell
# Di chuyển vào thư mục frontend
cd frontend

# Cài đặt thư viện npm
npm install

# Khởi chạy giao diện phát triển Vite
npm run dev
```
Giao diện ứng dụng sẽ hoạt động tại: **`http://localhost:5173`**

---

### Bước 5: Đăng nhập Trải nghiệm Ứng dụng
Truy cập **`http://localhost:5173`**. Trên màn hình đăng nhập, hệ thống cung cấp sẵn các nút đăng nhập nhanh (**Quick Login**):
- **Vai trò Kỹ sư (User):** `engineer.qa@bosch.com` (Được tra cứu kho, chat với trợ lý, tạo đơn mượn, xem và hủy đơn của chính mình).
- **Vai trò Quản lý (Manager):** `manager.lab@bosch.com` (Xem toàn bộ danh sách đơn kho, xem đánh giá ưu tiên của AI, duyệt đơn, từ chối kèm lý do, hoàn trả một phần).

---

## 5. Danh mục Kịch bản & Câu hỏi Mẫu Đã Được Kiểm Thử

Bạn có thể copy trực tiếp các câu lệnh mẫu dưới đây vào khung Chatbot để trải nghiệm khả năng xử lý của Agent:

| STT | Nhóm chức năng | Câu lệnh / Tình huống mẫu | Kết quả phản hồi của Agent |
| :---: | :--- | :--- | :--- |
| **1** | **Tra cứu theo mã cụ thể** | `"Cho mình xem thông tin thiết bị TU1-001 với"` | Trích xuất chính xác mã `TU1-001`, hiển thị tên, danh mục, thông số, vị trí tủ và số lượng tồn. |
| **2** | **Tra cứu đa thuộc tính kỹ thuật** | `"Tìm cho mình đầu cắm loại bẻ góc R/A, 10 chân, kích thước 4.2mm trong tủ 1"` | Lọc chính xác 4 điều kiện cùng lúc: `4.2mm` + `10 chân` + `R/A` + `Tủ 1` và hiển thị kết quả tương ứng. |
| **3** | **Hỏi tồn kho khả dụng** | `"Thiết bị TU1-001 hiện tại còn bao nhiêu cái trong kho để mượn?"` | Tính toán số lượng tồn trừ đi các đơn đang mượn/đã duyệt giao cắt thời gian và trả lời số lượng khả dụng. |
| **4** | **Báo cáo hết hàng (Quantity = 0)** | `"Có thiết bị nào đã hết hàng trong kho không?"` | Trả về bảng Markdown danh sách các thiết bị có số lượng ghi nhận bằng đúng 0 (như `TU2-007`, `TU2-017`...). |
| **5** | **Báo cáo sắp hết hàng (Low-stock)** | `"Tìm các món còn dưới 5 cái trong kho"` | Nhận diện toán tử nghiêm ngặt `dưới 5` và hiển thị các thiết bị có tồn kho từ 1 đến 4 cái. |
| **6** | **Hội thoại kế thừa ngữ cảnh** | **Lượt 1:** `"Cho mình xem thông tin thiết bị TU1-001"`<br>**Lượt 2:** `"Cái đó còn mượn được bao nhiêu cái từ ngày 20/11 đến 25/11?"`<br>**Lượt 3:** `"Nếu mượn 2 cái cho dự án Radar V2 thì sao?"` | Kế thừa đại từ *"Cái đó"*, ghi nhớ mã `TU1-001`, kiểm tra tồn theo khoảng ngày và tự động hướng dẫn mở form mượn cho dự án Radar V2. |
| **7** | **Tính toán thiếu hụt (Shortage)** | `"Nếu mình cần mượn 30 cái TU1-001 thì sao?"` | Phản hồi thông minh: Kho chỉ còn 23 cái khả dụng, thiếu chính xác 7 cái; gợi ý kỹ sư mượn số lượng tối đa hiện có. |
| **8** | **Mở form mượn tự động qua Chat** | `"Mình cần mượn 2 cái đầu cắm TU1-001 cho dự án Radar gấp trong tuần tới"` | Bật Modal biểu mẫu mượn thiết bị và điền sẵn mã, tên thiết bị, số lượng = 2 và dự án = Radar. |
| **9** | **Quy trình trả thiết bị qua Chat** | **Lượt 1:** `"Mình muốn trả thiết bị"`<br>**Lượt 2:** `"Tôi muốn trả cái thứ 1"` | Liệt kê các thiết bị kỹ sư đang mượn; giải quyết số thứ tự ở lượt tiếp theo và mở form xác nhận hoàn trả. |
| **10** | **Tìm nguồn ngoài thị trường** | `"Tìm nơi bán ngoài thị trường cho linh kiện CAN Interface và tham khảo khoảng giá"` | Phân loại intent `external_sourcing`, kích hoạt công cụ tra cứu và tổng hợp bảng nhà phân phối (DigiKey, Mouser, LCSC...) kèm mức giá tham khảo. |
| **11** | **Quản lý từ chối đơn có lý do** | Quản lý bấm nút **Từ chối** trên Dashboard $\rightarrow$ nhập: *"Trùng lịch bảo trì thiết bị phòng lab"* | Lưu lý do vào cột `rejection_reason` trong Excel. Màn hình của kỹ sư hiển thị rõ ràng lý do từ chối. |
| **12** | **Quản lý hoàn trả một phần** | Đơn đang mượn 5 cái $\rightarrow$ Quản lý bấm **Hoàn trả một phần** $\rightarrow$ chọn trả 2 cái | Đơn gốc cập nhật thành 3 cái (`Borrowed`), tạo dòng mới ghi nhận 2 cái (`Returned`), tồn khả dụng tăng đúng 2. |

---

## 6. Kiểm thử Tự động & Đo lường Chi phí

### 6.1. Chạy Bộ Kiểm thử Backend (Pytest Suite)
Hệ thống sở hữu bộ kiểm thử tự động toàn diện bao quát 100% các luồng chức năng, phân quyền, xử lý xung đột, máy trạng thái và các kịch bản hồi quy sau sửa lỗi:

```powershell
cd backend
python3.11 -m pytest tests/ -v
```
**Kết quả kiểm thử:**
- **274/274 tests PASSED (100%)**
- Bao gồm đầy đủ các bài test phân loại ý định, thuật toán giao cắt thời gian, phân quyền RBAC, kiểm tra toàn vẹn dữ liệu Excel, kiểm thử hồi quy cho lỗi hoàn trả một phần và lưu lý do từ chối.

### 6.2. Kiểm tra Build Frontend
```powershell
cd frontend
npm run build
```
**Kết quả:** Build thành công 100% không có lỗi TypeScript (`tsc && vite build`).

### 6.3. Đo lường Token & Chi phí Gemini API Thực tế
Hệ thống cung cấp sẵn công cụ đo lường thực nghiệm lượng token tiêu thụ và chi phí API trực tiếp:

```powershell
cd backend
python3.11 "C:\Users\Nam Phạm\.gemini\antigravity\brain\cef18841-418c-4175-b072-2abb69dc62e1\scratch\token_cost_benchmark.py"
```

Dữ liệu đo lường theo biểu giá chính thức của Google AI for Developers (**Gemini 3.1 Flash-Lite Standard Paid Tier**):
- **Tra cứu đơn thiết bị:** ~2,263 tokens $\rightarrow$ **~24.51 VNĐ**
- **Tra cứu kỹ thuật đa điều kiện:** ~2,331 tokens $\rightarrow$ **~26.60 VNĐ**
- **Đánh giá mức độ ưu tiên:** ~897 tokens $\rightarrow$ **~13.31 VNĐ**
- **Tìm nguồn ngoài thị trường (2 lần gọi):** ~4,137 tokens $\rightarrow$ **~73.12 VNĐ**
- **Chu trình mượn trọn gói E2E (Chat + Nộp đơn):** ~3,200 tokens $\rightarrow$ **~38.86 VNĐ đến 39.55 VNĐ**
- **Thao tác Quản lý duyệt/từ chối/trả:** **0 tokens $\rightarrow$ 0.00 VNĐ**

*(Xem chi tiết phân tích kinh tế và bảng dự phóng cho 10.000 lượt tương tác tại file [`GEMINI_TOKEN_AND_COST_REPORT.md`](GEMINI_TOKEN_AND_COST_REPORT.md)).*

---

## 7. Bảo mật & Tính Toàn vẹn Dữ liệu

- **Bảo mật bí mật và API Keys:** Tệp cấu hình chứa API key thật (`.env`) được đặt nghiêm ngặt trong [`.gitignore`](.gitignore), tuyệt đối không đẩy lên Git.
- **Tính năng độc lập dữ liệu:** Toàn bộ dữ liệu trong [`equipment_agent.xlsx`](backend/data/equipment_agent.xlsx) là dữ liệu kỹ thuật giả định phục vụ nghiên cứu và kiểm thử, không chứa thông tin nội bộ hay bí mật kinh doanh.
- **Nguyên tắc an toàn AI (AI Governance):** Mô hình AI không được cấp quyền tự động duyệt hoặc từ chối đơn mượn. AI chỉ đóng vai trò phân tích và đề xuất bằng chứng khách quan hỗ trợ người quản lý ra quyết định.
