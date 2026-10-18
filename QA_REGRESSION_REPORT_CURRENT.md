# BÁO CÁO KIỂM THỬ HỒI QUY VÀ ĐÁNH GIÁ CHẤT LƯỢNG HỆ THỐNG
## AI EQUIPMENT AGENT V1 (POST-UPGRADE REGRESSION AUDIT)

**Người thực hiện:** Senior QA Engineer & Software Test Engineer  
**Ngày thực hiện:** 15/10/2026  
**Mục đích tài liệu:** Bằng chứng thực nghiệm kỹ thuật độc lập phục vụ bảo trì hệ thống và viết Báo cáo Thực tập / Khóa luận tốt nghiệp.

---

## 1. THÔNG TIN PHIÊN BẢN VÀ MÔI TRƯỜNG KIỂM THỬ

### 1.1. Thông tin phiên bản mã nguồn
- **Git Branch:** `feat/full-agent-architecture-upgrade`
- **Commit SHA:** `dbfe813` (`fix(agent): resolve equipment context bleed and person overdue loan tracking`)
- **Trạng thái Git Working Tree:** Clean (Không có thay đổi chưa commit).
- **Cấu hình biến môi trường chính (`.env`):**
  - `DATA_BACKEND=excel`
  - `EXCEL_DATA_PATH=backend/data/equipment_agent.xlsx`
  - `GEMINI_MODEL=gemini-3.1-flash-lite`
  - `AGENT_ROUTING_MODE=llm_primary` (Môi trường test tự động cô lập: `legacy_only`)
  - `ENABLE_EXTERNAL_SOURCING=True`

### 1.2. Môi trường và phần mềm thực thi
- **Hệ điều hành:** Windows 11 Pro (x86_64)
- **Runtime Backend:** Python 3.11.9 (`C:\Users\Nam Phạm\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe`)
- **Test Runner Backend:** `pytest` v8.2.0, `pluggy` v1.6.0, `anyio` v4.15.1
- **Runtime Frontend:** Node.js v20+, Vite v8.3.2, TypeScript v6.0.2, React v19.3.0
- **Lệnh kiểm thử đã chạy:**
  1. Backend Full Suite: `python3.11 -m pytest tests -q` (Thực thi tại thư mục `backend/`)
  2. Frontend Compilation & Typecheck: `npm run build` (Thực thi tại thư mục `frontend/`)
  3. Bổ sung kịch bản độc lập: `python3.11 scratch/regression_verifier.py` (Môi trường test cô lập tại thư mục tạm `%TEMP%`).

---

## 2. TÓM TẮT KẾT QUẢ KIỂM THỬ

### 2.1. Số liệu tổng hợp bộ kiểm thử hiện có (Backend Test Suite)

| Hạng mục | Kết quả | Ghi chú kỹ thuật |
| :--- | :---: | :--- |
| **Tổng số test case** | **271** | Bao gồm 27 file kiểm thử trong `backend/tests/` |
| **PASSED** | **271** | Tỷ lệ thành công **100%** khi chạy với Working Directory `backend/` |
| **FAILED** | **0** | Đạt chuẩn (0 lỗi khi chạy đúng root directory cấu hình) |
| **SKIPPED** | **0** | Không có test nào bị bỏ qua |
| **Thời gian thực thi** | **117.28 giây** (~1 phút 57 giây) | Đo bằng pytest runner |
| **Cảnh báo (Warnings)** | **5** | 1 deprecation `on_event` của FastAPI, 1 `python-multipart`, 1 Pydantic V2 config |

> [!NOTE]
> **Lưu ý về thư mục chạy test:** Khi chạy lệnh `pytest backend/tests` từ thư mục gốc của repository thay vì `cd backend`, có 1 test case `test_area_13_excel_isolation_active` bị fail do kiểm tra đường dẫn tương đối `Path("data/equipment_agent.xlsx")`. Khi chạy đúng với `Cwd=backend/` theo quy chuẩn `pytest.ini`, test này PASS 100%.

### 2.2. Kiểm tra biên dịch và kiểu dữ liệu Frontend
- **Lệnh thực thi:** `npm run build` (`tsc && vite build`)
- **Kết quả:** **Thành công (Exit code 0)**.
- **Chi tiết:** 93 module được chuyển đổi, 0 lỗi kiểu dữ liệu TypeScript, thời gian build: **214ms**.

---

## 3. KẾT QUẢ KIỂM THỬ HỒI QUY CHI TIẾT THEO 8 NHÓM NGHIỆP VỤ (B1 – B8)

Bảng dưới đây tổng hợp kết quả kiểm thử thực nghiệm trên dữ liệu thật `equipment_agent.xlsx` (116 bản ghi thiết bị, 98 bản ghi yêu cầu, 6 người dùng hệ thống):

| Mã Test | Nhóm nghiệp vụ | Điều kiện & Dữ liệu kiểm thử | Kết quả mong đợi (Expected) | Kết quả thực tế (Actual) | Trạng thái | Bằng chứng kiểm thử |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| **REG-B1-01** | B1. Tra cứu | Mã `TU1-001`, Tên `Conn header SMD 24pos 3mm female` | Trả về chính xác 1 bản ghi duy nhất, khớp ID và Tên | Khớp chính xác 1 bản ghi `TU1-001`, tổng tồn 37 cái | **PASS** | `test_agent_orchestrator.py`<br/>`retrieval.py:44` |
| **REG-B1-02** | B1. Tra cứu | Câu hỏi nhiều thuộc tính: `đầu nối góc vuông 10 chân 4.2mm` | Nhận diện R/A (`geometry`), 10 chân (`pins`), 4.2mm (`size_mm`) | Trả về đúng `TU1-002` (Conn header R/A 10pos 4.2mm) | **PASS** | `retrieval.py:158-184`<br/>`test_agent_orchestrator.py` |
| **REG-B1-03** | B1. Tra cứu | Phân biệt màu sắc: `Banana jumper đỏ` vs `Banana jumper đen` | Phân tách rõ ràng: Đỏ ra `TU1-010`, Đen ra `TU1-011` | Đỏ ra đúng `TU1-010` (116 cái), Đen ra đúng `TU1-011` (89 cái) | **PASS** | `retrieval.py:186-200`<br/>`test_consolidated_regression.py` |
| **REG-B1-04** | B1. Tra cứu | Thiết bị không tồn tại: `CANInterface XYZ` | Thông báo không tìm thấy trong kho, gợi ý thiết bị tương tự | Báo không tìm thấy và đưa ra danh mục gợi ý thay thế | **PASS** | `orchestrator.py:1450`<br/>`test_auto_alternative_suggestion.py` |
| **REG-B1-05** | B1. Tra cứu | Hỏi vị trí: `TU1-001 nằm ở đâu` | Trả về vị trí có căn cứ trong Excel (`Tủ 1`) | Trả về `Vị trí: Tủ 1`, không bịa đặt vị trí khác | **PASS** | `test_agent_conversation.py`<br/>`orchestrator.py:920` |
| **REG-B1-06** | B1. Tra cứu | Regression: Hỏi `TU1-001`, sau đó hỏi `TU2-007 Wheelspeed sensor` | Xóa `active_equipment` cũ, không bị nhiễm chéo context | Trả về chính xác `TU2-007` (Tủ 2), không lẫn lộn với `TU1-001` | **PASS** | `orchestrator.py:311`<br/>`test_reported_bugs_regression.py` |
| **REG-B2-01** | B2. Tồn kho | Tính khả dụng thiết bị `TU1-001` ngày 01/11/2026 - 05/11/2026 | `Available = Total - (Approved + Borrowed)` | Tổng 37, Đã giữ 14, Khả dụng chính xác là 23 cái | **PASS** | `availability_service.py:35`<br/>`numeric.py:15` |
| **REG-B2-02** | B2. Tồn kho | Nhu cầu lớn hơn khả dụng: hỏi 30 cái khi khả dụng chỉ có 23 | Báo không đủ số lượng và tính ra chính xác số thiếu (thiếu 7 cái) | Phản hồi: "Kho hiện chỉ còn 23 cái khả dụng... thiếu 7 cái" | **PASS** | `numeric.py:48-52`<br/>`test_agent_orchestrator.py` |
| **REG-B2-03** | B2. Tồn kho | Xử lý các đơn ở trạng thái `Pending` trong khoảng ngày kiểm tra | Hiển thị trong danh sách xung đột cạnh tranh, **không** trừ vào khả dụng | Đơn Pending được liệt kê cảnh báo, khả dụng không bị trừ sai | **PASS** | `availability_service.py:48`<br/>`test_availability.py` |
| **REG-B3-01** | B3. Ngữ cảnh | Câu hỏi tiếp nối: `Cái đó còn bao nhiêu cái` sau khi hỏi `TU1-001` | Đại từ `cái đó` được phân giải thành `TU1-001` từ State RAM | Trả lời số lượng tồn kho của đúng `TU1-001` (37 cái) | **PASS** | `orchestrator.py:410`<br/>`test_agent_orchestrator.py` |
| **REG-B3-02** | B3. Ngữ cảnh | Chuyển chủ đề: đang hỏi `TU1-001` chuyển sang `Có module CAN nào không` | Entity Guard phát hiện đối tượng mới, reset `active_equipment` | Tìm kiếm module CAN trong kho, không bị kẹt ở `TU1-001` | **PASS** | `orchestrator.py:270`<br/>`test_p0_return_and_security_fixes.py` |
| **REG-B3-03** | B3. Ngữ cảnh | Regression: Hỏi `Còn của Nam Phạm thì sao` | User Nam Phạm xem được đơn mình; User khác bị từ chối bởi RBAC | Nam Phạm xem được 5 đơn (11 cái); User khác nhận cảnh báo quyền | **PASS** | `orchestrator.py:1210`<br/>`test_consolidated_regression.py` |
| **REG-B3-04** | B3. Ngữ cảnh | LLM Gemini router trả về lỗi / không có API key | Tự động chuyển đổi an toàn sang RuleRouter (28 bộ luật) | Hệ thống phản hồi bình thường dựa trên luật Regex | **PASS** | `gemini_router.py:165`<br/>`test_agent_architecture_upgrade.py` |
| **REG-B4-01** | B4. Lập đơn | Gửi thông tin mượn qua API: `TU1-001`, SL: 2, từ 10/11 đến 15/11 | Ghi thành công vào Sheet `Equipment_Requests`, mã `REQ-`, status `Pending` | Đơn được tạo với mã tự tăng `REQ-YYYYMMDD-NNNNNN`, status `Pending` | **PASS** | `excel_request.py:355`<br/>`test_api_requests.py` |
| **REG-B4-02** | B4. Lập đơn | Dữ liệu sai: SL <= 0 hoặc `needed_to < needed_from` | Schema `RequestCreate` chặn tại API Gateway với HTTP 422 | Pydantic chặn bằng `ValidationError`, trả về mã lỗi 422 | **PASS** | `schemas/requests.py:53`<br/>`test_api_requests.py` |
| **REG-B4-03** | B4. Lập đơn | AI đánh giá ưu tiên bị lỗi hoặc chưa cấu hình API Key | Gán nhãn dự phòng an toàn `Needs review` và ghi lý do giải thích | Đơn lưu thành công với `priority_level="Needs review"` | **PASS** | `priority_service.py:18`<br/>`test_priority_validation.py` |
| **REG-B5-01** | B5. Phê duyệt | Quản lý phê duyệt đơn Pending và xác nhận mượn | Đơn chuyển sang `Approved`, sau đó chuyển sang `Borrowed` | Trạng thái chuyển đổi chính xác theo State Machine | **PASS** | `approval_service.py:105-136`<br/>`test_state_transitions.py` |
| **REG-B5-02** | B5. Phê duyệt | Quản lý từ chối đơn mượn kèm lý do | Đơn chuyển sang `Rejected`, lý do từ chối được lưu trữ | Trạng thái đổi sang `Rejected`. **Phát hiện lỗi không lưu lý do vào Excel** | **FAIL (Partial)** | `approval_service.py:124`<br/>*(Xem chi tiết mục 4)* |
| **REG-B5-03** | B5. Phê duyệt | Quản lý tự duyệt đơn do chính mình tạo (Trùng email) | Chốt chặn `Self-Approval Guard` ngăn cấm với HTTP 403 | Bị chặn với HTTP 403: "không thể tự phê duyệt... của chính mình" | **PASS** | `approval_service.py:107`<br/>`test_role_authorization.py` |
| **REG-B5-04** | B5. Phê duyệt | Kiểm tra xung đột lịch các đơn giao thoa ngày | `ConflictService` phát hiện các cặp đơn trùng khoảng ngày | Phát hiện chính xác các cặp xung đột `start_a <= end_b` | **PASS** | `conflict_service.py:30-45`<br/>`test_conflict_engine.py` |
| **REG-B6-01** | B6. Hoàn trả | Hoàn trả toàn bộ số lượng đang mượn (Ví dụ mượn 4 trả 4) | Đơn chuyển sang `Returned`, tồn kho khả dụng được phục hồi | Đơn đổi trạng thái `Returned`, ghi nhận tình trạng thiết bị | **PASS** | `approval_service.py:154`<br/>`test_return_flow.py` |
| **REG-B6-02** | B6. Hoàn trả | Hoàn trả một phần (Mượn 5 cái, hoàn trả 2 cái) | Tách đơn: Đơn gốc còn 3 cái (`Borrowed`), Đơn mới 2 cái (`Returned`) | Đơn mới tạo 2 cái, **nhưng đơn gốc không giảm số lượng trong Excel** | **FAIL (Critical)** | `excel_request.py:474`<br/>*(Xem chi tiết mục 4)* |
| **REG-B6-03** | B6. Hoàn trả | Nhập số lượng hoàn trả sai: SL = 0 hoặc SL > đang giữ | Chặn ngay với HTTP 400 Bad Request kèm thông báo rõ ràng | Bị từ chối với HTTP 400: "Số lượng hoàn trả phải lớn hơn 0" | **PASS** | `approval_service.py:174-183`<br/>`test_p0_return_and_security_fixes.py` |
| **REG-B7-01** | B7. Nguồn ngoài | Gọi External Sourcing khi chưa cấu hình Key hoặc tắt dịch vụ | Trả về trạng thái trung thực `disabled` / `not_configured`, không sinh ảo | Trả về thông báo dịch vụ chưa khả dụng, không bịa đặt link mua | **PASS** | `services/external_sourcing.py:53`<br/>`test_post_audit_delta.py` |
| **REG-B8-01** | B8. Quản trị | Admin tạo tài khoản mới và kiểm tra email trùng lặp | Tạo thành công; nếu email đã tồn tại thì báo lỗi HTTP 400 | Tạo thành công user mới; chặn email trùng lặp với `ValueError` | **PASS** | `excel_user.py:90`<br/>`test_role_authorization.py` |
| **REG-B8-02** | B8. Quản trị | Thao tác hạ quyền hoặc khóa tài khoản Admin duy nhất | `Last Admin Guard` chặn thao tác với HTTP 400 | Bị chặn với lỗi: "Không thể hạ quyền/vô hiệu hóa Admin duy nhất" | **PASS** | `excel_user.py:218, 255`<br/>`test_role_authorization.py` |

---

## 4. NHẬT KÝ LỖI VÀ VẤN ĐỀ PHÁT HIỆN (DEFECTS LOG)

Trong quá trình kiểm thử hồi quy chuyên sâu trên tầng tích hợp dữ liệu thực tế, đội ngũ QA phát hiện **2 lỗi nghiệp vụ quan trọng** cần lưu ý:

### DEFECT-01: Lỗi bất biến số lượng khi Hoàn trả một phần (Critical)
- **Mức độ nghiêm trọng:** `Critical` (Gây sai lệch dữ liệu tồn kho nghiêm trọng).
- **Vị trí mã nguồn:** [`backend/app/repositories/excel_request.py:474`](file:///d:/UEH%20YEAR%204/HKTT/ke%20hoach%20fixed-term/ai-equipment-agent-v1-antigravity/ai-equipment-agent-v1/backend/app/repositories/excel_request.py#L474).
- **Mô tả hiện tượng:**
  Khi người dùng thực hiện hoàn trả một phần (ví dụ đang mượn 5 cái, chỉ trả 2 cái):
  1. `ApprovalService.mark_returned()` khởi tạo bản ghi mới với số lượng = 2 và trạng thái = `Returned` $\rightarrow$ ghi thành công vào Excel.
  2. `ApprovalService` giảm biến `r.quantity = r.quantity - 2` (còn 3 cái) và gọi `self._repo.update(r)`.
  3. Tuy nhiên, trong hàm `ExcelRequestRepository.update()`, dòng 474 đang gán cứng:
     ```python
     quantity = existing.quantity,  # Cố định số lượng ban đầu, bỏ qua giá trị cập nhật
     ```
- **Hậu quả:** Đơn gốc trong Excel vẫn giữ nguyên số lượng là 5 cái (không giảm về 3). Khi hệ thống quét tính tồn kho khả dụng (`Available = Total - Borrowed`), 2 cái đã trả vẫn tiếp tục bị trừ khỏi kho, làm kho bị thiếu ảo 2 cái.
- **Phương án khắc phục đề xuất:**
  Tại file `excel_request.py`, sửa dòng 474 thành:
  ```python
  quantity = getattr(request, "quantity", existing.quantity),
  ```

---

### DEFECT-02: Lý do từ chối của Quản lý không được lưu vào Excel (Medium)
- **Mức độ nghiêm trọng:** `Medium` (Mất mát thông tin giải trình của người quản lý).
- **Vị trí mã nguồn:** [`backend/app/repositories/excel_request.py:479-480`](file:///d:/UEH%20YEAR%204/HKTT/ke%20hoach%20fixed-term/ai-equipment-agent-v1-antigravity/ai-equipment-agent-v1/backend/app/repositories/excel_request.py#L479-L480) và [`backend/app/services/approval_service.py:124`](file:///d:/UEH%20YEAR%204/HKTT/ke%20hoach%20fixed-term/ai-equipment-agent-v1-antigravity/ai-equipment-agent-v1/backend/app/services/approval_service.py#L124).
- **Mô tả hiện tượng:**
  Khi Quản lý từ chối đơn với một lý do cụ thể (ví dụ: *"Hết thiết bị dự phòng"*), `ApprovalService.reject()` nối chuỗi `[Từ chối: Hết thiết bị dự phòng]` vào trường `r.priority_reason`. Nhưng `ExcelRequestRepository.update()` có quy tắc bảo vệ:
  ```python
  # AI assessment never modified after creation
  priority_level = existing.priority_level,
  priority_reason = existing.priority_reason,
  ```
- **Hậu quả:** Lý do từ chối chỉ hiển thị trong response ngay lúc đó, nhưng khi tải lại từ file Excel thì bị mất, chỉ còn nguyên lý do ban đầu của AI.
- **Phương án khắc phục đề xuất:**
  Cho phép `update()` cập nhật `priority_reason` nếu trạng thái mới là `Rejected`, hoặc bổ sung cột `RejectionReason` trong Sheet `Equipment_Requests`.

---

## 5. SO SÁNH VỚI CÁC BẢN KIỂM THỬ TRƯỚC (REGRESSION COMPARISON)

| Vấn đề trước đây | Trạng thái hiện tại | Bằng chứng xác minh |
| :--- | :---: | :--- |
| **Nhiễm chéo context giữa `TU1-001` và `TU2-007`** | **ĐÃ KHẮC PHỤC TRIỆT ĐỂ** | `Entity Guard` trong `_map_gemini_to_plan` nhận diện thực thể mới và dọn dẹp `active_equipment` cũ sạch sẽ. Test `test_reported_bugs_regression.py` pass. |
| **Tra cứu người mượn "Hải Nam" / "Nam Phạm"** | **ĐÃ KHẮC PHỤC TRIỆT ĐỂ** | Đã hỗ trợ `Token-set Matcher` không dấu/có dấu tiếng Việt, phân biệt chính xác giữa Nam Phạm và các user khác. |
| **Lỗi định dạng Markdown Table có ký tự pipe `\|`** | **ĐÃ KHẮC PHỤC TRIỆT ĐỂ** | Hàm `escape_markdown_cell` escape an toàn các ký tự `\|` và xuống dòng, bảng hiển thị chuẩn xác trên UI. |
| **Lọc Banana Jumper theo màu Đỏ / Đen** | **ĐÃ KHẮC PHỤC TRIỆT ĐỂ** | Bộ lọc `c.color` trong `retrieval.py` nhận diện chính xác từ khóa màu và trả đúng ID `TU1-010` và `TU1-011`. |
| **Form hoàn trả mặc định số lượng trả = 1** | **ĐÃ KHẮC PHỤC TRIỆT ĐỂ** | Mặc định điền toàn bộ số lượng đang mượn của đơn được chọn; cho phép người dùng sửa đổi linh hoạt. |

---

## 6. ĐỐI CHIẾU HỆ THỐNG THỰC TẾ VỚI 7 SƠ ĐỒ THIẾT KẾ

Bảng đối chiếu giữa các bước trong tài liệu [docs/SYSTEM_FLOWCHARTS_AND_BUSINESS_PROCESSES.md](file:///d:/UEH%20YEAR%204/HKTT/ke%20hoach%20fixed-term/ai-equipment-agent-v1-antigravity/ai-equipment-agent-v1/docs/SYSTEM_FLOWCHARTS_AND_BUSINESS_PROCESSES.md) và triển khai thực tế trong source code:

1. **Sơ đồ 1 - Kiến trúc Hệ thống:** **Khớp 100%**. Hệ thống phân định rõ 5 tầng: React Client, FastAPI Gateway (HMAC Cookie Session), Agent Orchestrator, Tools/Gemini 3.1 Flash-Lite, và Excel Datastore (FileLock bảo vệ).
2. **Sơ đồ 2 - Luồng Quyết định AI Agent:** **Khớp 100%**. Đủ 8 bước từ State Manager, Text Normalizer, Routing Switch (LLM/Rule), Entity Guard, Tool Dispatcher, Markdown Formatter, State Persistence và Client Response.
3. **Sơ đồ 3 - Tra cứu & Kiểm tra Tồn kho:** **Khớp 95%**. 
   - *Điểm cần lưu ý trong báo cáo:* Sơ đồ ghi công thức `Available = Total - Borrowed`. Nhưng trong code thực tế (`availability_service.py:35`), công thức chính xác và an toàn hơn là: `Available = Total - (Approved + Borrowed)` (tính cả các đơn đã duyệt nhưng chưa lấy đồ).
4. **Sơ đồ 4 - Lập đơn mượn & AI thẩm định:** **Khớp 100%**. Form nhúng prefill thông tin, kiểm tra tính hợp lệ ngày tháng và số lượng tại API Gateway, gọi Gemini thẩm định, nếu lỗi thì gán `Needs review`.
5. **Sơ đồ 5 - Phê duyệt & Xung đột lịch:** **Khớp 90%**.
   - *Đã triển khai:* Chốt chặn `Self-Approval Guard` chặn quản lý tự duyệt đơn mình (HTTP 403); phát hiện xung đột lịch giao thoa ngày.
   - *Hạn chế thực tế:* Xung đột lịch trong code mới chỉ so sánh theo khoảng ngày (`YYYY-MM-DD`), chưa hỗ trợ chi tiết theo khung giờ trong ngày (`HH:MM`).
   - *Lệch pha với sơ đồ:* Lý do từ chối của Quản lý chưa được ghi bền vững vào Excel như sơ đồ mô tả (do `DEFECT-02`).
6. **Sơ đồ 6 - Hoàn trả thiết bị:** **Khớp 85%**.
   - Logic tách đơn và phục hồi tồn kho trên lý thuyết đã được viết trong `ApprovalService`, nhưng đang bị chặn lại bởi `DEFECT-01` tại tầng Repository khi ghi xuống file `.xlsx`.
7. **Sơ đồ 7 - Quản trị tài khoản Admin RBAC:** **Khớp 100%**. Có đủ tính năng thêm user, kiểm tra email trùng, đổi role, bật tắt kích hoạt, và bảo vệ `Last Admin Guard` (chặn hạ quyền/khóa Admin cuối cùng).

---

## 7. GIỚI HẠN KIỂM THỬ (TEST LIMITATIONS)

1. **Môi trường Test tự động không gọi Gemini API thật:** Bộ test tự động sử dụng `DemoAIProvider` hoặc mock để đảm bảo tính độc lập, không phụ thuộc vào kết nối mạng, chi phí token và quota rate-limit của Google Cloud. Chức năng gọi Gemini 3.1 Flash-Lite chỉ được kích hoạt khi chạy runtime thực tế với `GEMINI_API_KEY` hợp lệ.
2. **Tích hợp Microsoft Graph:** Mã nguồn có sẵn các module `graph_client.py`, `graph_equipment.py`, `graph_request.py`. Tuy nhiên do không có tài khoản doanh nghiệp Microsoft 365 Work/School Account kèm quyền Admin Consent, phạm vi kiểm thử hiện tại tập trung 100% vào backend mặc định `DATA_BACKEND=excel`.
3. **Kiểm thử E2E giao diện tự động:** Hiện chưa cài đặt framework trình duyệt nặng như Playwright hay Cypress trong repository; việc kiểm thử giao diện dựa trên kiểm tra kiểu tĩnh (TypeScript Build Check) và kiểm thử tích hợp API endpoints qua `TestClient`.

---

## 8. KHUYẾN NGHỊ ƯU TIÊN CHO ĐỘI NGŨ PHÁT TRIỂN

Trước khi tiến hành báo cáo khóa luận hoặc đóng gói sản phẩm cuối cùng, khuyến nghị ưu tiên xử lý:

1. **Ưu tiên 1 (Critical): Sửa dòng 474 trong `excel_request.py`:**
   Cho phép cập nhật số lượng yêu cầu `quantity = getattr(request, "quantity", existing.quantity)` để chức năng Hoàn trả một phần (Partial Return) hoạt động chính xác và phục hồi đúng tồn kho.
2. **Ưu tiên 2 (Medium): Bổ sung lưu lý do từ chối trong `excel_request.py`:**
   Cho phép cập nhật `priority_reason` khi đơn bị `Rejected` để người dùng và quản lý xem lại được lý do từ chối.
3. **Ưu tiên 3 (Documentation): Đồng bộ công thức tồn kho trong tài liệu:**
   Cập nhật mô tả trong báo cáo thành `Available = Total - (Approved + Borrowed)` để đồng nhất tuyệt đối với source code thực tế.
