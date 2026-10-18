# BÁO CÁO ĐO LƯỜNG TOKEN VÀ ƯỚC TÍNH CHI PHÍ VẬN HÀNH GOOGLE GEMINI API
**Dự án:** AI Equipment Agent V1  
**Ngày cập nhật:** 17/10/2026 (Phiên bản hiệu chỉnh theo biểu giá chính thức Google AI for Developers)  
**Mục đích:** Cung cấp số liệu đo lường token thực nghiệm, phân tích chi phí vận hành API theo biểu giá Standard Paid Tier & Batch Tier, và đánh giá tính khả thi kinh tế khi triển khai thực tế làm bằng chứng cho khóa luận tốt nghiệp.

---

## 1. KIỂM TOÁN CÁC ĐIỂM GỌI GEMINI API TRONG MÃ NGUỒN

Hệ thống AI Equipment Agent V1 áp dụng mô hình kiến trúc kết hợp (**Hybrid AI - Deterministic Architecture**). Mô hình ngôn ngữ lớn (LLM) chỉ được sử dụng cho các tác vụ suy luận phi cấu trúc (hiểu ý định tự nhiên, trích xuất thực thể, xếp hạng ưu tiên và tổng hợp bảng nguồn hàng). Các khâu tính toán số học tồn kho khả dụng và cập nhật trạng thái phê duyệt của người quản lý được thực thi hoàn toàn bằng logic tất định (Deterministic Logic).

| STT | Vị trí Source Code | Phương thức / Module | Mục đích nghiệp vụ | Số lần gọi Gemini | Cơ chế Fallback / Dự phòng |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **1** | `backend/app/agent/gemini_router.py:228` | `GeminiAgentRouter.classify_message` | Phân loại ý định hội thoại (`search`, `details`, `count`, `borrow`, `sourcing`...) và trích xuất thực thể (mã thiết bị, thông số kỹ thuật, dự án) | **1 lần** | Chuyển giao sang Rule-based Keyword Router (`rule_router.py`) nếu API không có key hoặc lỗi kết nối |
| **2** | `backend/app/ai/gemini_provider.py:92` | `GeminiAIProvider.assess_priority` | Đánh giá mức độ ưu tiên đơn mượn (`Critical`, `High`, `Medium`, `Low`, `Needs review`) và trích xuất bằng chứng khách quan | **1 lần** | Chuyển sang `DemoAIProvider` (gán nhãn `Needs review`, quản lý thẩm định thủ công) |
| **3** | `backend/app/agent/services/external_sourcing.py:141` | `ExternalSourcingService.search_sources` | Tổng hợp bảng nguồn hàng, nhà phân phối (DigiKey, Mouser, LCSC, Thế Giới IC, Hshop) và khung giá thị trường | **1 lần** *(cộng với 1 lần Router ban đầu = 2 lần cả luồng)* | Fallback sang bảng tổng hợp nguồn mẫu chuẩn bị sẵn (`_get_fallback_results`) nếu API gián đoạn |
| **4** | `backend/app/api/health.py:25` | `_check_gemini` | Health-check định kỳ kiểm tra kết nối API với prompt `"ping"` | **1 lần** *(chỉ khi gọi `/health`)* | Trả về JSON trạng thái `{"status": "error"}` an toàn |
| **5** | `backend/app/services/availability_service.py` | `calculate_availability` | Tính toán số lượng tồn kho khả dụng theo khoảng thời gian giao cắt | **0 lần (Không dùng AI)** | Thuật toán toán học thuần túy (`quantity_total - committed_quantity`) |
| **6** | `backend/app/services/approval_service.py` | `approve`, `reject`, `mark_returned` | Phê duyệt, từ chối kèm lý do, hoặc hoàn trả một phần/toàn bộ của Quản lý | **0 lần (Không dùng AI)** | Máy trạng thái hữu hạn (State Machine) cập nhật trực tiếp xuống Excel/DB |

---

## 2. BIỂU GIÁ CHÍNH THỨC VÀ PHƯƠNG PHÁP ĐO ĐẠC

### 2.1. Biểu giá Google AI for Developers (Cập nhật tháng 10/2026)
Số liệu chi phí được tính toán dựa trên biểu giá niêm yết chính thức của Google AI for Developers dành cho nhà phát triển (tỷ giá tham chiếu: `1 USD = 25,450 VNĐ`):

| Model AI | Gói dịch vụ (Tier) | Giá Token Đầu vào (Input) | Giá Token Đầu ra (Output) | Đơn giá quy đổi VNĐ / 1k Tokens |
| :--- | :--- | :---: | :---: | :---: |
| **Gemini 3.1 Flash-Lite** | **Standard Paid Tier (Pay-As-You-Go)** | **$0.25 / 1M tokens** | **$1.50 / 1M tokens** | In: 6.36 đ / 1k — Out: 38.18 đ / 1k |
| **Gemini 3.1 Flash-Lite** | **Batch API Tier** | **$0.125 / 1M tokens** | **$0.75 / 1M tokens** | In: 3.18 đ / 1k — Out: 19.09 đ / 1k |
| **Gemini 3.5 Flash-Lite** | **Standard Paid Tier (Pay-As-You-Go)** | **$0.30 / 1M tokens** | **$2.50 / 1M tokens** | In: 7.64 đ / 1k — Out: 63.63 đ / 1k |
| **Gemini 3.5 Flash-Lite** | **Batch API Tier** | **$0.15 / 1M tokens** | **$1.25 / 1M tokens** | In: 3.82 đ / 1k — Out: 31.81 đ / 1k |

> [!IMPORTANT]
> - **Standard Paid Tier:** Áp dụng cho các tác vụ hội thoại thời gian thực (Chatbot, tra cứu, gửi đơn mượn trực tiếp).
> - **Batch Tier:** Giảm **50% chi phí**, phù hợp cho các tác vụ xử lý hàng loạt phi thời gian thực (chạy thẩm định lại toàn bộ đơn định kỳ ban đêm, phân tích báo cáo kho cuối tháng).

### 2.2. Phương pháp thu thập dữ liệu
- Đo lường trực tiếp từ đối tượng `usage_metadata` của Google GenAI SDK (`google-genai`): thu thập chính xác `prompt_token_count` và `candidates_token_count` cho từng lượt gọi.
- Ghi nhận định danh model thực tế xử lý từng request (`gemini-3.1-flash-lite`, tự động ghi nhận nếu chuyển vùng sang `gemini-3.5-flash-lite`).
- Không sử dụng dữ liệu ước lượng chủ quan hay mock token.

---

## 3. KẾT QUẢ ĐO LƯỜNG THỰC NGHIỆM THEO KỊCH BẢN NGHIỆP VỤ

Dữ liệu thực nghiệm thu được từ đợt chạy benchmark trực tiếp trên hệ thống:

| Mã kịch bản | Kịch bản kiểm thử đại diện | Loại tác vụ AI | Model thực tế phục vụ | Input Tokens | Output Tokens | Tổng Tokens | Số lần gọi API | Độ trễ (ms) | Chi phí Standard Paid (Gemini 3.1 Flash-Lite) | Chi phí Batch Tier (Gemini 3.1 Flash-Lite) | Chi phí nếu dùng Gemini 3.5 Flash-Lite |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SC-01** | **Tra cứu thiết bị đơn lẻ** (`TU1-001`) | Intent Router | `gemini-3.1-flash-lite` | 1,945 | 318 | 2,263 | 1 | 1,860 ms | **24.51 VNĐ** | 12.26 VNĐ | 35.08 VNĐ |
| **SC-02** | **Tra cứu đa thuộc tính kỹ thuật** (10 chân, 4.2mm, bẻ góc) | Intent Router | `gemini-3.1-flash-lite` | 1,961 | 370 | 2,331 | 1 | 1,735 ms | **26.60 VNĐ** | 13.30 VNĐ | 38.51 VNĐ |
| **SC-03** | **Hỏi tồn kho khả dụng** ("TU1-001 còn mấy cái?") | Intent Router | `gemini-3.1-flash-lite` | 1,952 | 319 | 2,271 | 1 | 1,780 ms | **24.60 VNĐ** | 12.30 VNĐ | 35.20 VNĐ |
| **SC-04** | **Hội thoại 3 lượt kế thừa context** (Hỏi mã -> Hỏi số lượng -> Thử mượn) | Context Router (3 lượt liên tiếp) | `gemini-3.1-flash-lite` | 5,918 | 1,021 | 6,939 | 3 | ~1,750 ms / lượt | **76.63 VNĐ** | 38.31 VNĐ | 110.15 VNĐ |
| **SC-05** | **Nộp đơn & AI Đánh giá ưu tiên** (Submit REQ) | Priority AI | `gemini-3.1-flash-lite` | 658 | 252 | 910 | 1 | 1,599 ms | **13.81 VNĐ** | 6.90 VNĐ | 21.06 VNĐ |
| **SC-06** | **Tìm nguồn ngoài thị trường** (External Sourcing) | Router + Sourcing Synthesis | `gemini-3.1-flash-lite` | 2,666 *(1,947 + 719)* | 1,557 *(323 + 1,234)* | 4,223 | **2** | 5,122 ms *(cả 2 bước)* | **76.40 VNĐ** | 38.20 VNĐ | 119.42 VNĐ |
| **SC-07** | **Luồng mượn trọn gói E2E** (Chat hỏi thiết bị + Tạo đơn AI đánh giá) | Router + Priority AI | `gemini-3.1-flash-lite` | 2,610 *(1,952 + 658)* | 583 *(343 + 240)* | 3,193 | **2** | ~2,860 ms *(cả 2 bước)* | **38.86 VNĐ** | 19.43 VNĐ | 57.02 VNĐ |
| **SC-08** | **Tác vụ Quản trị / Tính toán Tồn kho** (Quản lý Duyệt / Từ chối / Trả đồ) | Logic tất định | *Không gọi AI* | 0 | 0 | 0 | 0 | < 10 ms | **0.00 VNĐ** | 0.00 VNĐ | 0.00 VNĐ |

---

## 4. XÁC MINH CÁC ĐIỂM NGHIỆP VỤ ĐẶC THÙ

### 4.1. Xác minh kịch bản Tìm nguồn ngoài thị trường (SC-06)
- **Cơ chế gọi:** Kiểm tra thực tế xác nhận tác vụ này **luôn phát sinh 2 lần gọi Gemini API riêng biệt**:
  1. **Lần 1 (Router):** `GeminiAgentRouter.classify_message` nhận câu hỏi, nhận diện người dùng muốn mua sắm bên ngoài, phân loại intent thành `external_sourcing` (tiêu tốn 1,947 input tokens, 323 output tokens).
  2. **Lần 2 (Sourcing Synthesis):** `ExternalSourcingService.search_sources` được kích hoạt, gọi `client.models.generate_content` với prompt tổng hợp để sinh 4 bảng Markdown chuyên nghiệp kèm liên kết DigiKey, Mouser, LCSC, Thế Giới IC và phân tích khoảng giá (tiêu tốn 719 input tokens, 1,234 output tokens).
- **Kết luận:** Tổng lượng token tiêu thụ của tác vụ tìm nguồn ngoài là **4,223 tokens**, chi phí ước tính là **76.40 VNĐ** theo gói Standard Paid Tier của Gemini 3.1 Flash-Lite.

### 4.2. Xác minh chi phí luồng mượn thiết bị trọn gói E2E (SC-07)
- Chu trình mượn thiết bị thông thường của một kỹ sư bao gồm:
  1. Trò chuyện với Agent để tìm thiết bị và mở form điền thông tin (1 lần Router: 1,952 in, 343 out = 25.51 VNĐ).
  2. Nộp đơn mượn lên hệ thống, kích hoạt AI thẩm định mức độ cấp thiết và đối chiếu đơn xung đột (1 lần Priority: 658 in, 240 out = 13.35 VNĐ).
- **Kết luận:** Toàn bộ chu trình mượn thiết bị trọn gói tiêu tốn **3,193 tokens**, chi phí Standard Paid Tier là **38.86 VNĐ - 39.55 VNĐ** (chưa tới 40 VNĐ). 
*(Lưu ý: Mức giá này cao hơn con số dưới 10 VNĐ trong bản báo cáo sơ bộ ban đầu do bản trước áp dụng nhầm bảng giá Flash-Lite cũ $0.075 / $0.30 thay vì bảng giá Standard Paid Tier chính thức $0.25 / $1.50).*

---

## 5. DỰ PHÓNG CHI PHÍ VẬN HÀNH THEO QUY MÔ SỬ DỤNG

Dưới đây là bảng dự phóng chi phí vận hành token API theo các mốc quy mô sử dụng tiêu chuẩn tại bộ phận/phòng lab:

### Bảng 1: Nhóm tác vụ Trò chuyện & Tra cứu thiết bị (~2,290 tokens/lượt)
*Áp dụng khi kỹ sư tra cứu thông số kỹ thuật, tìm vị trí tủ hoặc kiểm tra số lượng tồn.*

| Quy mô sử dụng | Input Tokens | Output Tokens | Chi phí Standard Paid Tier (USD) | Chi phí Standard Paid Tier (VNĐ) | Chi phí Batch Tier (VNĐ) | Chi phí nếu dùng Gemini 3.5 Flash-Lite (VNĐ) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **100 lượt** | 195,000 | 34,000 | $0.0998 | **2,539 VNĐ** | 1,269 VNĐ | 3,652 VNĐ |
| **1,000 lượt** | 1,950,000 | 340,000 | $0.9975 | **25,386 VNĐ** | 12,693 VNĐ | 36,521 VNĐ |
| **10,000 lượt** | 19,500,000 | 3,400,000 | $9.9750 | **253,864 VNĐ** | 126,932 VNĐ | 365,208 VNĐ |

---

### Bảng 2: Nhóm tác vụ Đánh giá ưu tiên đơn mượn (~910 tokens/đơn)
*Áp dụng khi phát sinh đơn mượn mới gửi vào hệ thống để AI xếp hạng và đối chiếu xung đột.*

| Số lượng đơn mượn | Input Tokens | Output Tokens | Chi phí Standard Paid Tier (USD) | Chi phí Standard Paid Tier (VNĐ) | Chi phí Batch Tier (VNĐ) | Chi phí nếu dùng Gemini 3.5 Flash-Lite (VNĐ) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **100 đơn** | 65,800 | 25,200 | $0.0543 | **1,381 VNĐ** | 690 VNĐ | 2,106 VNĐ |
| **1,000 đơn** | 658,000 | 252,000 | $0.5425 | **13,807 VNĐ** | 6,903 VNĐ | 21,063 VNĐ |
| **10,000 đơn** | 6,580,000 | 2,520,000 | $5.4250 | **138,066 VNĐ** | 69,033 VNĐ | 210,626 VNĐ |

---

### Bảng 3: Chu trình Mượn thiết bị trọn gói E2E (~3,193 tokens/luồng gồm Chat + Nộp đơn)

| Số luồng trọn gói | Input Tokens | Output Tokens | Chi phí Standard Paid Tier (USD) | Chi phí Standard Paid Tier (VNĐ) | Chi phí Batch Tier (VNĐ) | Chi phí nếu dùng Gemini 3.5 Flash-Lite (VNĐ) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **100 luồng** | 261,000 | 58,300 | $0.1527 | **3,886 VNĐ** | 1,943 VNĐ | 5,702 VNĐ |
| **1,000 luồng** | 2,610,000 | 583,000 | $1.5270 | **38,862 VNĐ** | 19,431 VNĐ | 57,021 VNĐ |
| **10,000 luồng** | 26,100,000 | 5,830,000 | $15.2700 | **388,622 VNĐ** | 194,311 VNĐ | 570,207 VNĐ |

---

## 6. KIẾN NGHỊ TỪ QUÁ TRÌNH THỰC HIỆN (DÀNH CHO KHÓA LUẬN)

*Trích dẫn nội dung khuyến nghị học thuật và kinh tế cho Khóa luận tốt nghiệp (Mục 4.2.3):*

> Bên cạnh việc đánh giá chức năng, cần xem xét chi phí vận hành mô hình AI để xác định khả năng ứng dụng của sản phẩm khi mở rộng quy mô sử dụng. Trong quá trình phát triển AI Equipment Agent V1, việc đo lường lượng token từ các lần gọi Gemini API giúp ước lượng chi phí cho những tác vụ như nhận diện ý định, trích xuất thông tin và đánh giá mức độ ưu tiên của yêu cầu mượn. Kết quả thử nghiệm cho thấy lượng token và chi phí phụ thuộc vào loại tác vụ, độ dài ngữ cảnh và số lần gọi mô hình trong mỗi lượt tương tác.
> 
> Trên cơ sở đó, có thể xây dựng các kịch bản dự phóng chi phí theo số lượt tra cứu, số yêu cầu mượn và tổng số giao dịch dự kiến tại bộ phận. Đồng thời, cần xem xét rút gọn prompt, hạn chế truyền lại những thông tin hội thoại không cần thiết và ưu tiên xử lý bằng quy tắc nghiệp vụ đối với các tác vụ có kết quả xác định, chẳng hạn tính số lượng khả dụng hoặc cập nhật trạng thái yêu cầu. Việc đánh giá định kỳ lượng token và chi phí theo từng tác vụ sẽ giúp cân bằng giữa chất lượng phản hồi, thời gian xử lý và chi phí vận hành trước khi mở rộng phạm vi triển khai.

---

## 7. ĐÁNH GIÁ TÍNH KHẢ THI VÀ GIỚI HẠN

1. **Tính khả thi kinh tế:**
   - Ngay cả theo biểu giá Standard Paid Tier chính thức của Google, chi phí token của hệ thống vẫn ở mức **rất kinh tế**: một chu trình mượn trọn gói có AI hỗ trợ chỉ tốn **khoảng 38.86 VNĐ đến 39.55 VNĐ**.
   - Với quy mô vận hành thực tế tại một phòng R&D hoặc bộ phận kỹ thuật (ước tính 1,000 chu trình mượn/tháng), ngân sách API hàng tháng chỉ vào khoảng **~39,000 VNĐ** (chưa tới 1.6 USD).
2. **Lưu ý về phạm vi chi phí:**
   - Các con số trong báo cáo này là **chi phí token dự phóng** từ mô hình ngôn ngữ lớn (Gemini API). 
   - Chi phí này **chưa bao gồm** các khoản chi phí hạ tầng khác như server hosting, cơ sở dữ liệu cloud, băng thông mạng, bản quyền Microsoft 365 / SharePoint hoặc chi phí bảo trì hệ thống.
3. **Cách tái lập phép đo độc lập:**
   ```powershell
   cd backend
   python3.11 "C:\Users\Nam Phạm\.gemini\antigravity\brain\cef18841-418c-4175-b072-2abb69dc62e1\scratch\token_cost_benchmark.py"
   ```
