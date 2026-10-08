# Data model and Microsoft Lists mapping

## 1. Equipment — danh mục thiết bị

Nguồn: Microsoft List `Equipment` hiện có hoặc CSV export từ List.

| Field | Type | Notes |
|---|---|---|
| `equipment_id` | string | Mã ổn định, lấy từ `EquipmentID` |
| `equipment_name` | string | `EquipmentName` |
| `category` | string, nullable | `Category`; giá trị suy luận, nên có thể rà soát |
| `description` | string, nullable | `Description`; giữ nguyên nguồn |
| `quantity_total` | integer | `Quantity`; tổng số lượng, không phải khả dụng |
| `unit` | string, nullable | `Unit` |
| `location` | string, nullable | `Location` |

Không dùng `Target` trong V1. Không tự dựng trường `available_quantity` trong danh mục nguồn.

## 2. EquipmentRequest — yêu cầu mượn

V1 xử lý **một loại thiết bị cho mỗi request** để form và nghiệp vụ đơn giản. Nếu sau này một yêu cầu phải chứa nhiều loại thiết bị, hãy chuẩn hóa thành Request + RequestItems ở phiên bản sau.

| Field | Type | Who/why |
|---|---|---|
| `id` | internal ID | Tự sinh; có thể hiển thị dạng `REQ-000123` |
| `requester_name` | string | Từ user context; trong demo có thể chọn người dùng mẫu |
| `requester_email` | string, nullable | Dùng cho thông báo khi có danh tính/địa chỉ thật |
| `project` | string | Tên dự án do người dùng nhập/chọn; V1 không yêu cầu Project List đáng tin cậy |
| `equipment_id` | string | Mã thiết bị đã chọn từ danh mục |
| `quantity` | integer > 0 | Người dùng nhập |
| `needed_from` | date | Người dùng nhập |
| `needed_to` | date | Ngày dự kiến trả; phải không sớm hơn `needed_from` |
| `purpose` | string | Mục đích sử dụng do người dùng mô tả |
| `priority_level` | enum | AI đề xuất: `Critical`, `High`, `Medium`, `Low`, `Needs review` |
| `priority_reason` | string | Lý do kèm dữ kiện liên quan; AI tạo, backend xác thực/giới hạn độ dài |
| `status` | enum | `Pending`, `Approved`, `Rejected`, `Borrowed`, `Returned`, `Cancelled` |
| `created_at` | datetime | Hệ thống ghi nhận, tương ứng gần với cột hệ thống `Created` |
| `modified_at` | datetime | Hệ thống cập nhật, tương ứng gần với cột hệ thống `Modified` |

Không thêm `ManagerComment`, `ApprovedAt` hoặc `RejectedAt` trong V1. Không yêu cầu người dùng tự nhập `PriorityLevel` hoặc `PriorityReason`. Không cần tạo trường `RequestID` riêng nếu dùng ID hệ thống; UI có thể định dạng ID thành `REQ-000123`.

Nếu dùng Microsoft Lists, ánh xạ các trường nghiệp vụ sang cột có tên tương ứng. `ID`, `Created` và `Modified` là cột hệ thống của List; không cố tạo trùng các cột đó.

## 3. State machine

```text
Pending ──► Approved ──► Borrowed ──► Returned
   │             │
   ├──► Rejected  └──► Cancelled (chỉ khi chưa bàn giao)
   └──► Cancelled
```

- AI không được thực hiện chuyển trạng thái `Pending` sang `Approved` hoặc `Rejected`.
- Chỉ quản lý mới được duyệt/từ chối.
- Không cho phép chuyển `Rejected`, `Returned` hoặc `Cancelled` trở lại trạng thái hoạt động bằng thao tác thông thường.
- Kiểm tra trạng thái hiện tại ở backend để ngăn thao tác lặp hoặc chuyển trạng thái sai.

## 4. Tính khả dụng theo thời gian

Với thiết bị có tổng số lượng `Q`, khi kiểm tra một khoảng thời gian, tính số lượng đã cam kết bởi các yêu cầu khác có khoảng thời gian giao nhau và trạng thái `Approved` hoặc `Borrowed`:

`available = quantity_total - sum(quantity of overlapping Approved/Borrowed requests)`

Giới hạn kết quả tối thiểu là 0; nếu số lượng cam kết vượt tổng kiểm kê, phải báo xung đột dữ liệu thay vì âm thầm coi là bình thường.

- `Pending` không được tính là cấp phát đã xác nhận, nhưng phải hiển thị như yêu cầu cạnh tranh khi đánh giá ưu tiên.
- `Rejected`, `Cancelled` và `Returned` không còn giữ chỗ.
- Loại trừ chính request đang được đánh giá khỏi phép tính xung đột.
- Dùng quy tắc khoảng ngày nhất quán: hai khoảng ngày giao nhau nếu `start_a <= end_b` và `start_b <= end_a`.
- Không thể tính khả dụng chính xác nếu các giao dịch mượn hiện tại không được ghi nhận. Khi đó phải hiển thị rằng dữ liệu chưa đủ.

## 5. Projects

Một Microsoft List `Projects` có thể đã được tạo trong môi trường của người dùng. V1 không được phụ thuộc vào danh sách này để quyết định dự án quan trọng hay không, vì người dùng chưa có nguồn cập nhật đáng tin cậy. Có thể giữ List đó để phát triển sau, nhưng form V1 vẫn phải cho nhập tên dự án và AI không được lấy tên dự án làm bằng chứng về tầm quan trọng.
