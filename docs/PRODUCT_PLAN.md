# Product plan — Trợ lý AI hỗ trợ tra cứu và quản lý thiết bị kỹ thuật

## 1. Mục tiêu sản phẩm

Xây dựng một ứng dụng web cho phép người dùng tra cứu danh mục thiết bị kỹ thuật và gửi yêu cầu mượn qua một biểu mẫu xuất hiện ngay trong giao diện chat. AI hỗ trợ tìm thông tin, đọc bối cảnh của yêu cầu và đề xuất mức ưu tiên. Người quản lý xem các yêu cầu đang chờ trên dashboard, kiểm tra thông tin rồi tự quyết định duyệt hoặc từ chối.

Đây là prototype V1 phục vụ kiểm chứng ý tưởng, không phải hệ thống vận hành chính thức của Bosch.

## 2. Người dùng và quyền hạn

### Người sử dụng thiết bị
- Tìm kiếm thiết bị bằng tên, mô tả hoặc nhu cầu.
- Xem thông tin thiết bị có trong nguồn dữ liệu.
- Gửi yêu cầu mượn thông qua form trong chat.
- Xem trạng thái các yêu cầu của mình.
- Hủy yêu cầu còn ở trạng thái `Pending`.
- Sau khi được duyệt, xem hướng dẫn/ trạng thái nhận thiết bị và trả thiết bị theo luồng V1.

### Người quản lý
- Xem danh sách yêu cầu đang `Pending`.
- Xem đề xuất ưu tiên, lý do, dữ liệu liên quan và xung đột lịch.
- Duyệt hoặc từ chối yêu cầu.
- Cập nhật trạng thái `Borrowed` khi bàn giao và `Returned` khi nhận lại.
- Quyết định cuối cùng vẫn thuộc về người quản lý.

## 3. Luồng chính

### 3.1 Tra cứu
1. Người dùng nhập câu hỏi vào khung chat.
2. Agent xác định ý định tra cứu và gọi chức năng tìm kiếm.
3. Backend truy vấn `Equipment`.
4. UI hiển thị kết quả theo dữ liệu thật; không tự thêm thông tin không có trong nguồn.

### 3.2 Gửi yêu cầu mượn
1. Người dùng nói muốn mượn thiết bị.
2. Agent nhận diện ý định và mở một form ngay trong cuộc trò chuyện, không hỏi từng trường theo chuỗi nếu có thể thu thập cùng lúc.
3. Nếu câu chat đã nêu thiết bị/dự án thì điền sẵn những trường tương ứng.
4. Người dùng điền các trường còn thiếu và gửi.
5. Backend xác thực dữ liệu, kiểm tra thiết bị và khoảng thời gian, tạo request với `Status = Pending`.
6. Dịch vụ ưu tiên đánh giá yêu cầu và lưu mức đề xuất cùng lý do.
7. Người dùng nhận xác nhận đã gửi yêu cầu.

### 3.3 Quản lý duyệt
1. Dashboard tải các yêu cầu `Pending`, hiển thị đề xuất ưu tiên và lý do.
2. Quản lý xem thông tin thiết bị, thời gian, mục đích và các yêu cầu có lịch trùng.
3. Quản lý nhấn duyệt hoặc từ chối.
4. Backend kiểm tra quyền và trạng thái hiện tại trước khi đổi trạng thái.
5. Hệ thống phát thông báo. Ở local/demo, thông báo được ghi vào log/console và giao diện báo đây là mô phỏng; khi kết nối được email thật mới gửi thư thật.

### 3.4 Bàn giao và hoàn trả
- Sau khi duyệt, trạng thái là `Approved`.
- Khi thiết bị được giao cho người dùng, quản lý cập nhật thành `Borrowed`.
- Khi thiết bị được hoàn trả, trạng thái thành `Returned`.
- `Pending` không được tính là thiết bị đã cấp phát; nhưng cần được hiển thị khi phân tích xung đột giữa các yêu cầu.

## 4. Form mượn thiết bị

Các trường hiển thị cho người dùng:
- Dự án (`Project`): văn bản; có thể gợi ý tên từng dùng trước đó nhưng vẫn cho nhập tên mới.
- Thiết bị (`EquipmentID`): chọn từ danh mục.
- Số lượng (`Quantity`): số nguyên dương.
- Ngày bắt đầu (`NeededFrom`).
- Ngày dự kiến trả (`NeededTo`), phải sau hoặc bằng ngày bắt đầu theo quy tắc đã thống nhất của sản phẩm.
- Mục đích sử dụng (`Purpose`).

Người yêu cầu lấy từ phiên đăng nhập hoặc context demo; không bắt điền tên nếu đã có danh tính đáng tin cậy.

Không hỏi người dùng tự chọn `PriorityLevel`. V1 cũng không bắt người dùng đánh giá “dự án quan trọng đến đâu” hoặc trả lời một câu hỏi dài về tác động kinh doanh. Nếu thiếu thông tin để xếp ưu tiên có căn cứ, AI báo chưa đủ thông tin và để quản lý xem xét.

## 5. Phạm vi V1

Bao gồm:
- Tra cứu danh mục thiết bị.
- Form yêu cầu mượn xuất hiện trong chat.
- Lưu yêu cầu và xem trạng thái.
- Tính khả dụng theo lịch và số lượng đang được giữ/sử dụng.
- Đánh giá ưu tiên có giải thích và bằng chứng.
- Dashboard quản lý, duyệt/từ chối.
- Chuyển trạng thái bàn giao/hoàn trả.
- Thông báo qua nhà cung cấp email được cấu hình; có console adapter cho demo.
- SQLite local để app chạy ngay; repository adapter cho Microsoft Lists nếu cấu hình API khả thi.

Không bao gồm ở V1:
- Tự động phê duyệt bằng AI.
- Tự suy đoán dự án nào quan trọng hơn dựa trên tên dự án.
- Tích hợp bắt buộc với hệ thống quản lý dự án nội bộ.
- Tự động mua sắm hoặc tự động cấp phát.
- Nhận diện tình trạng thiết bị bằng hình ảnh.
- Vector database, RAG cho tài liệu dài, multi-agent hoặc tối ưu lịch phức tạp khi chưa có nhu cầu chứng minh.
- Triển khai production hoặc xử lý dữ liệu nội bộ thật khi chưa có phê duyệt và cấu hình bảo mật.

## 6. Nguyên tắc về dữ liệu

- `Equipment.Quantity` là tổng số lượng kiểm kê, không phải số lượng khả dụng.
- Không tự điền `Target`; trường này không dùng trong V1.
- `Description` được giữ nguyên từ dữ liệu nguồn.
- `Category` có thể là giá trị suy luận; không xem là thông tin xác nhận chính thức.
- Tên dự án ở V1 là thông tin do người dùng cung cấp trong từng request. Không giả định có một danh mục dự án đầy đủ hoặc luôn cập nhật.
- Không ghi request vào `Equipment`.
- Chỉ request `Approved` hoặc `Borrowed` mới làm giảm số lượng có thể phân bổ cho khoảng thời gian trùng lặp; `Pending` là xung đột đang chờ xem xét nhưng chưa phải cấp phát được xác nhận.

## 7. Nguyên tắc UI

- Giao diện tiếng Việt.
- Tông sáng, tối giản và dễ đọc; không dùng dark theme mặc định.
- Dùng icon có chọn lọc, không gắn icon vào mọi tiêu đề/nút.
- Ưu tiên bảng, nhãn trạng thái chữ, biểu mẫu có label rõ ràng và thông báo ngắn.
- Phân biệt trực quan dữ liệu thật, dữ liệu mẫu và chức năng chưa kết nối.
