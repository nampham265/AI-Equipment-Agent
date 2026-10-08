# Privacy and security

- Dữ liệu kiểm kê thiết bị của Bosch có thể là thông tin nội bộ. Chỉ dùng trong môi trường/công cụ được phép theo quy định của công ty.
- Không chép inventory thật vào thư mục demo, repo Git, prompt dùng chung hoặc gửi lên nhà cung cấp AI nếu chưa có quyền.
- File inventory thật nên nằm tại `data/private/` trên máy local; thư mục này đã được Git ignore. Không tự động đọc file private nếu chưa được người dùng cấu hình đường dẫn.
- Không commit `.env`, access token, refresh token, app secret, mật khẩu hoặc email/tên người dùng thật.
- Không để frontend giữ client secret hoặc gọi Microsoft Graph bằng secret nhúng trong bundle.
- Dùng backend làm lớp trung gian để xác thực, kiểm tra quyền và ghi dữ liệu.
- Chế độ demo role-switch không phải cơ chế đăng nhập an toàn; không mở ứng dụng demo ra Internet hoặc dùng với dữ liệu thật.
- Khi triển khai cho nhiều người dùng, cần xác thực phù hợp (ví dụ Microsoft identity khi được hỗ trợ/cấp quyền) và kiểm tra vai trò ở backend.
- AI chỉ nhận trường dữ liệu cần thiết cho nhiệm vụ. Không gửi mô tả nội bộ không liên quan vào prompt.
- Chuẩn hóa và giới hạn đầu ra AI; xem nội dung từ dữ liệu và LLM là dữ liệu không đáng tin cậy cho đến khi xác thực.
- Quản lý giữ quyền quyết định phê duyệt.
