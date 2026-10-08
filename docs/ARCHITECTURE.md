# Architecture

## 1. Stack đề xuất

- Frontend: React + TypeScript + Vite.
- Backend: Python + FastAPI + Pydantic.
- Cơ sở dữ liệu local: SQLite.
- Truy cập dữ liệu: repository/service layer; không truy vấn SQLite hoặc Microsoft Lists trực tiếp từ giao diện.
- AI: provider interface với đầu ra có cấu trúc; Gemini có thể là provider đầu tiên nếu người dùng có API key. Không ghi API key vào source code.
- Thông báo: `ConsoleNotificationProvider` cho demo; Microsoft Graph/email adapter khi đã cấu hình.

Không dùng framework tác tử lớn chỉ để điều phối một vài hàm. Hãy triển khai tool calling có kiểm soát, hoặc một lớp điều phối nhỏ phù hợp với thư viện LLM đã chọn.

## 2. Các lớp

```text
React Web UI
  ├── Chat + inline request form
  ├── My Requests
  └── Manager Dashboard
           │ HTTP/JSON
           ▼
FastAPI routes
           ▼
Application services
  ├── EquipmentService
  ├── RequestService
  ├── AvailabilityService
  ├── PriorityAssessmentService
  ├── ApprovalService
  └── NotificationService
           │
           ├── Repository interfaces
           │    ├── SQLite implementation (default)
           │    └── Microsoft Lists / Graph implementation (optional)
           │
           ├── AI provider interface
           │    ├── Configured LLM provider
           │    └── Clearly labelled demo fallback
           │
           └── Notification provider
                ├── Console (default in local mode)
                └── Email/Graph (optional)
```

## 3. Cấu trúc thư mục code mong muốn

```text
frontend/
  src/
    app/
    components/
    features/chat/
    features/equipment/
    features/requests/
    features/manager/
    lib/api.ts
    types/
backend/
  app/
    main.py
    api/
    core/config.py
    schemas/
    models/
    repositories/
    services/
    ai/
    notifications/
  tests/
data/
  sample/
  private/   # không commit
```

Có thể điều chỉnh nếu kiến trúc repo có lý do tốt hơn, nhưng không gộp toàn bộ code vào một file.

## 4. API tối thiểu

- `GET /api/health` — kiểm tra dịch vụ.
- `GET /api/equipment?q=` — tìm thiết bị.
- `GET /api/equipment/{equipment_id}` — chi tiết thiết bị.
- `POST /api/agent/message` — xử lý câu chat; trả về text và hành động giao diện có cấu trúc, ví dụ `show_borrow_form`.
- `POST /api/requests` — xác thực và tạo request.
- `GET /api/requests/mine` — danh sách request của người dùng hiện tại.
- `POST /api/requests/{request_id}/cancel` — người yêu cầu hủy request Pending của mình.
- `GET /api/manager/requests?status=Pending` — danh sách cho quản lý.
- `GET /api/manager/summary` — số yêu cầu theo trạng thái và xung đột cần xem.
- `POST /api/manager/requests/{request_id}/approve` — duyệt.
- `POST /api/manager/requests/{request_id}/reject` — từ chối.
- `POST /api/manager/requests/{request_id}/mark-borrowed` — ghi nhận bàn giao.
- `POST /api/requests/{request_id}/mark-returned` — ghi nhận hoàn trả theo quyền đã định nghĩa.

Tên endpoint có thể tinh chỉnh, nhưng phải giữ cùng chức năng và bảo vệ quyền ở backend.

## 5. Chế độ dữ liệu

### Local mode — bắt buộc chạy được
- SQLite là nguồn lưu request và demo equipment.
- Seed từ `data/sample/equipment.csv`.
- Dữ liệu demo phải được ghi nhãn trong UI.
- Không cần tài khoản Microsoft hoặc API key để khởi động và kiểm thử các luồng nghiệp vụ chính.

### Microsoft Lists mode — tùy chọn, cần xác minh
- Dùng một adapter repository riêng.
- Cấu hình ID site/list qua environment variables; không hardcode.
- Xác thực qua cơ chế Microsoft được hỗ trợ cho loại tài khoản và danh sách thực tế.
- Kiểm tra đọc `Equipment` và tạo một request thử nghiệm trước khi bật chế độ này.
- Không được giả định rằng My Lists cá nhân luôn khả dụng qua cùng API/quyền như SharePoint team site. Nếu kết nối chưa khả thi, báo rõ blocker và giữ local mode hoạt động.

## 6. Quản lý lỗi

- Lỗi validation trả về thông báo thân thiện, field-specific.
- Lỗi AI không được làm mất request đã gửi. Nếu request đã được lưu nhưng đánh giá ưu tiên lỗi, gán `Needs review`, lưu thông báo an toàn và cho quản lý xem xét.
- Lỗi email không được rollback quyết định duyệt. Lưu/ghi log trạng thái gửi thông báo và cho phép thử gửi lại.
- Không log API key, access token, toàn bộ nội dung nhạy cảm hoặc dữ liệu nội bộ không cần thiết.
