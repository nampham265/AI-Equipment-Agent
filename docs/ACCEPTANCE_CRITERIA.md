# Acceptance criteria

## A. Chạy ứng dụng
- Có một lệnh rõ ràng để chạy backend và một lệnh để chạy frontend trên Windows PowerShell.
- Có health endpoint.
- Không cần API key hoặc Microsoft credentials để mở local demo.
- README giải thích cách cấu hình LLM thật và Microsoft Lists sau này.

## B. Thiết bị
- Tìm theo mã, tên, category hoặc description.
- Chi tiết hiển thị đúng dữ liệu nguồn.
- Không hiển thị `Target`.
- Không biến `Quantity` thành số lượng khả dụng.
- Dữ liệu mẫu được nhận diện rõ là giả lập.

## C. Form yêu cầu
- Câu như “Mình muốn mượn [tên thiết bị] cho [dự án]” có thể mở form trong khung chat.
- Form có Project, Equipment, Quantity, NeededFrom, NeededTo, Purpose.
- Trường đã biết từ câu chat được điền sẵn nếu confidence đủ; nếu không, để người dùng chọn.
- Không có trường PriorityLevel/PriorityReason cho người dùng nhập.
- Backend kiểm tra equipment tồn tại, quantity dương, ngày hợp lệ và ngày dự kiến trả không trước ngày bắt đầu.
- Submit tạo đúng một request Pending và trả mã yêu cầu.

## D. Ưu tiên
- AI trả mức đề xuất và lý do có căn cứ.
- Không suy diễn dự án quan trọng hơn chỉ từ tên.
- Khi có xung đột nhưng không đủ dữ kiện so sánh, trả `Needs review`.
- Request vẫn được tạo nếu provider AI thất bại; dashboard cho thấy cần đánh giá thủ công.
- AI không có công cụ approve/reject.

## E. Quản lý
- Dashboard hiển thị request Pending và chi tiết cần để ra quyết định.
- Manager có thể approve/reject.
- Người dùng thường không thể gọi endpoint quản lý thành công.
- Chuyển trạng thái hợp lệ; request đã Returned/Rejected/Cancelled không được cấp phát lại bằng thao tác thông thường.
- Các hành động quản lý được xác nhận trước khi thực hiện.

## F. Khả dụng
- Chỉ các request Approved/Borrowed có khoảng thời gian giao nhau mới được tính vào số lượng đã cam kết.
- Pending requests được hiển thị như xung đột đang chờ, không phải thiết bị đã cấp phát.
- Không tính khả dụng khi trạng thái sử dụng quan trọng chưa có dữ liệu mà vẫn tuyên bố chắc chắn.

## G. Thông báo
- Approve/reject gọi notification provider.
- Local mode ghi thông báo mô phỏng và nói rõ chưa gửi email thật.
- Email lỗi không rollback trạng thái request.

## H. Chất lượng code/UI
- Business logic không nằm trong React components hoặc route handlers.
- Có tests cho availability, state transitions, request validation và priority output validation.
- Không commit `.env`, token, API key hoặc dữ liệu inventory nội bộ.
- Giao diện tiếng Việt, gọn, ít icon, không trang trí quá mức.
