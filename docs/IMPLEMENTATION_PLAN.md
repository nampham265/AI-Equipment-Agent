# End-to-end implementation plan

Đích cuối là một V1 chạy được từ đầu đến cuối. Các bước dưới đây là thứ tự triển khai kỹ thuật, không phải lý do để dừng sau từng phần dang dở.

## Step 0 — Kiểm tra workspace và cấu hình
- Kiểm tra phiên bản Python/Node và cấu trúc thư mục.
- Tạo `.env.example`, `.gitignore`, frontend/backend và hướng dẫn chạy Windows PowerShell.
- Không yêu cầu credentials ngay để bắt đầu.

## Step 1 — Dữ liệu và backend local
- Tạo model/schema `Equipment` và `EquipmentRequest`.
- SQLite và seed từ `data/sample/equipment.csv`.
- Viết repository interface và SQLite implementation.
- Tạo API tra cứu thiết bị, tạo yêu cầu, xem yêu cầu, dashboard quản lý, approve/reject, mark borrowed/returned/cancel.
- Xác thực field, kiểu dữ liệu, khoảng ngày, quantity và chuyển trạng thái.
- Viết test service cho khả dụng và state transitions.

## Step 2 — Giao diện người dùng
- Trang chat tiếng Việt với lịch sử hội thoại rõ ràng.
- Khi user có ý định mượn, hiển thị một form ngay trong cuộc trò chuyện.
- Các trường form: dự án, thiết bị, số lượng, ngày bắt đầu, ngày dự kiến trả, mục đích.
- Điền sẵn trường đã biết từ câu chat; không hỏi người dùng priority.
- Khi submit, gọi backend, hiển thị mã request và trạng thái Pending.
- Trang “Yêu cầu của tôi” để xem trạng thái.
- Có loading, empty state, lỗi validation, lỗi hệ thống và trạng thái demo.

## Step 3 — Dashboard quản lý
- Trang riêng liệt kê request Pending.
- Hiển thị thiết bị, dự án, người gửi, số lượng, thời gian, mục đích, trạng thái, mức ưu tiên đề xuất, lý do và xung đột dữ liệu.
- Cho phép xem chi tiết, approve/reject; không cho AI tự quyết định.
- Cho phép quản lý đánh dấu Borrowed và ghi nhận Returned theo quyền được cấu hình.
- Chặn endpoint quản lý nếu request không có quyền manager. Demo auth chỉ dùng local, không coi là bảo mật production.

## Step 4 — AI Agent và ưu tiên
- Tạo interface `LLMProvider` và service nhận diện ý định.
- Nếu user muốn mượn, agent trả hành động `show_borrow_form` kèm các trường có thể điền sẵn.
- Tạo `PriorityAssessmentService` nhận request + dữ liệu liên quan, yêu cầu output có cấu trúc và xác thực bằng schema.
- Không đánh giá criticality của project nếu không có dữ liệu xác minh.
- Khi model lỗi/timeout/JSON không hợp lệ, request đã gửi vẫn được lưu; priority chuyển `Needs review` và dashboard nêu rõ cần kiểm tra.
- Có fallback demo rõ ràng nếu chưa có API key.

## Step 5 — Thông báo
- Sau approve/reject, gọi `NotificationService`.
- Console provider mặc định ghi thông báo demo.
- Email provider là adapter riêng, cấu hình qua environment.
- Lỗi gửi mail không được làm mất quyết định đã lưu; log trạng thái lỗi và cho phép thử lại.
- Không ghi log hoặc hiển thị rằng email đã gửi thật nếu chỉ mới log ở console.

## Step 6 — Tích hợp Microsoft Lists
- Viết adapter riêng, không để frontend gọi Microsoft Graph trực tiếp.
- Trước tiên xác minh tài khoản thực tế có thể đọc List `Equipment` và tạo/cập nhật `Equipment_Requests` qua API bằng quyền được cấp.
- Lấy site/list IDs từ cấu hình, không hardcode.
- Test đọc danh mục và tạo request thử trong môi trường thử nghiệm.
- Nếu quyền/API của My Lists cá nhân không phù hợp, giữ SQLite hoạt động và mô tả chính xác bước cần chuyển sang SharePoint site/API được hỗ trợ. Không giả lập thành công.
- Không ghi credentials hoặc token vào repo.

## Step 7 — Kiểm thử và hoàn thiện
- Chạy unit tests và API tests.
- Kiểm tra luồng: search → open form → submit → Pending → priority → manager approve/reject → status update → notification.
- Kiểm thử cạnh: thiếu thiết bị, số lượng vượt tổng, ngày không hợp lệ, request trùng, model lỗi, người không phải manager gọi endpoint quản lý.
- Kiểm tra UI không có icon trang trí dư thừa, form có nhãn, layout dùng được trên màn hình laptop và hẹp.
- Viết README hoàn chỉnh với lệnh cài đặt/chạy và biến môi trường.

## Definition of done

Không kết thúc chỉ vì code đã được tạo. V1 chỉ coi là hoàn thành khi local mode chạy được, luồng end-to-end hoạt động, test chính chạy qua, có dữ liệu demo được gắn nhãn rõ, và tài liệu phân biệt phần thực sự chạy được với các phần còn chờ credentials.
