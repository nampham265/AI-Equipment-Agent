# Prompt mở đầu cho Antigravity

Hãy đọc toàn bộ `AGENTS.md` và các tài liệu trong `docs/` trước khi triển khai. Đây là yêu cầu xây dựng sản phẩm, không phải chỉ viết kế hoạch.

Mục tiêu là tạo một ứng dụng web Trợ lý AI quản lý thiết bị V1 chạy được từ đầu đến cuối. Hãy kiểm tra workspace hiện có, sau đó tự triển khai ứng dụng theo `docs/IMPLEMENTATION_PLAN.md` và `docs/ACCEPTANCE_CRITERIA.md`.

Yêu cầu quan trọng:

1. Hoàn thành một luồng end-to-end hoạt động ở chế độ local trước: tra cứu thiết bị → người dùng yêu cầu mượn → biểu mẫu xuất hiện ngay trong giao diện chat → gửi yêu cầu → lưu `Pending` → AI/logic đánh giá ưu tiên → quản lý xem dashboard → duyệt hoặc từ chối → đổi trạng thái → tạo thông báo/email ở chế độ phù hợp.
2. Không dừng ở giao diện tĩnh hoặc dữ liệu hardcode trong component. Dùng backend và cơ sở dữ liệu local thật cho chế độ demo.
3. Dùng React + TypeScript + Vite cho frontend; FastAPI + Python cho backend; SQLite cho lưu trữ local. Giữ lớp repository để có thể thay bằng Microsoft Lists/Graph sau khi xác minh quyền truy cập.
4. Dùng Gemini hoặc nhà cung cấp LLM qua một interface cấu hình được. Nếu chưa có API key, ứng dụng vẫn phải chạy bằng chế độ demo được ghi nhãn rõ; không giả vờ đó là phản hồi từ mô hình thật.
5. Không làm form dài. Các trường người dùng cần nhập: dự án, thiết bị, số lượng, ngày bắt đầu, ngày dự kiến trả, mục đích. Người yêu cầu được lấy từ phiên đăng nhập/demo context nếu có. Có thể điền sẵn dự án và thiết bị khi đã được nêu trong câu chat.
6. Không yêu cầu người dùng tự khai mức ưu tiên. AI tạo `PriorityLevel` và `PriorityReason` dựa trên thông tin có thật. Nếu thiếu bằng chứng để so sánh mức quan trọng giữa các dự án, trả về trạng thái cần quản lý xem xét; tuyệt đối không tự bịa mức độ quan trọng.
7. Quản lý phải xác nhận cuối cùng. Không cho AI tự duyệt/từ chối. Không có trường ghi chú quản lý trong V1.
8. Không dùng dữ liệu inventory nội bộ thật làm dữ liệu mẫu, không commit `.env`, token, API key hoặc dữ liệu cá nhân. Dùng `data/sample/equipment.csv` cho demo. Để dữ liệu riêng trong `data/private/` và không đưa lên Git.
9. UI tiếng Việt, gọn, chuyên nghiệp, không lạm dụng icon, emoji, gradient hoặc animation.
10. Viết code có cấu trúc, type hints, kiểm tra đầu vào, xử lý lỗi và test. Không nhồi mọi thứ vào một file; không thêm framework lớn nếu không cần.

Trước tiên, hãy trình bày ngắn gọn kiến trúc và các việc sẽ làm dựa trên tài liệu. Sau đó tiếp tục triển khai toàn bộ V1, chạy test và sửa lỗi. Chỉ dừng để hỏi mình khi gặp blocker thật sự cần thông tin/credential mà không thể thay thế bằng chế độ local. Cuối cùng, đưa hướng dẫn chạy chính xác cho Windows PowerShell và báo rõ phần nào đã kiểm thử, phần nào vẫn cần cấu hình Microsoft/AI/email.
