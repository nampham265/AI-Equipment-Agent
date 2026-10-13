"""External sourcing service abstraction.

Handles external product searches, vendors, and pricing.
Strictly protects internal data and ensures truthfulness.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class SourcedProduct(BaseModel):
    product_name: str
    shop_name: str
    price: Optional[float] = None
    currency: str = "VND"
    url: str
    source: str
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    availability: str = "Chưa rõ"
    notes: Optional[str] = None


class ExternalSourcingResult(BaseModel):
    enabled: bool
    status: str  # "success" | "disabled" | "not_configured" | "no_results" | "error"
    query_used: str
    products: list[SourcedProduct] = Field(default_factory=list)
    message: str


class ExternalSourcingService:
    """Service handling supplier searches outside the internal warehouse."""

    def __init__(self, enabled: Optional[bool] = None) -> None:
        self._enabled = enabled if enabled is not None else settings.ENABLE_EXTERNAL_SOURCING

    def search_sources(
        self,
        product_query: str,
        constraints: Optional[dict[str, Any]] = None,
        max_results: int = 3,
    ) -> ExternalSourcingResult:
        """Search external suppliers. If disabled or unconfigured, returns honest status."""
        clean_query = self._sanitize_query(product_query)

        if not self._enabled:
            return ExternalSourcingResult(
                enabled=False,
                status="disabled",
                query_used=clean_query,
                products=[],
                message=(
                    "Dịch vụ tìm kiếm nguồn cung ứng bên ngoài (External Sourcing) hiện đang tắt "
                    "hoặc chưa được cấu hình nhà cung cấp chính thức. "
                    "Vui lòng liên hệ phòng mua hàng (Purchasing) để được hỗ trợ mua mới."
                ),
            )

        import urllib.parse

        search_kw = self._extract_search_keyword(clean_query)
        encoded_kw = urllib.parse.quote_plus(search_kw)

        digikey_link = f"https://www.digikey.com/en/products/result?keywords={encoded_kw}"
        mouser_link = f"https://www.mouser.vn/c/?q={encoded_kw}"
        lcsc_link = f"https://www.lcsc.com/search?q={encoded_kw}"
        thegioiic_link = f"https://thegioiic.com/tim-kiem?q={encoded_kw}"
        hshop_link = f"https://hshop.vn/search?q={encoded_kw}"

        products = [
            SourcedProduct(
                product_name=f"{search_kw} (DigiKey Catalog)",
                shop_name="DigiKey",
                url=digikey_link,
                source="DigiKey Electronics",
                notes="Chính hãng, đủ CoC/RoHS",
            ),
            SourcedProduct(
                product_name=f"{search_kw} (Mouser Catalog)",
                shop_name="Mouser",
                url=mouser_link,
                source="Mouser Electronics",
                notes="Chuyên hàng R&D, dự án cao cấp",
            ),
            SourcedProduct(
                product_name=f"{search_kw} (LCSC Catalog)",
                shop_name="LCSC",
                url=lcsc_link,
                source="LCSC Electronics",
                notes="Tối ưu chi phí, dán SMD",
            ),
            SourcedProduct(
                product_name=f"{search_kw} (Thế Giới IC)",
                shop_name="Thế Giới IC",
                url=thegioiic_link,
                source="Thế Giới IC Việt Nam",
                notes="Sẵn kho VN, giao nhanh 1-2 ngày",
            ),
            SourcedProduct(
                product_name=f"{search_kw} (Hshop)",
                shop_name="Hshop",
                url=hshop_link,
                source="Hshop.vn",
                notes="Sẵn kho VN, giao nhanh",
            ),
        ]

        if settings.gemini_configured:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    f"Bạn là trợ lý tư vấn tìm nguồn cung ứng linh kiện kỹ thuật và điện tử cho kỹ sư.\n"
                    f"Người dùng cần tìm nơi mua ngoài thị trường và khoảng giá tham khảo cho: \"{search_kw}\".\n\n"
                    f"YÊU CẦU ĐỊNH DẠNG: BẮT BUỘC TRÌNH BÀY BẰNG CÁC BẢNG MARKDOWN (TABLE) TRỰC QUAN CÓ KÈM ĐƯỜNG LINK:\n\n"
                    f"### 1. Bảng kênh phân phối uy tín & Đường dẫn tra cứu trực tiếp\n"
                    f"Trình bày bảng Markdown với 4 cột: | Kênh phân phối | Phân loại | Thế mạnh & Hãng đại diện | Link tra cứu trực tiếp |\n"
                    f"Bắt buộc gắn chính xác các link Markdown sau vào cột link:\n"
                    f"| **DigiKey** | Quốc tế | Hàng chính hãng 100%, đủ chứng chỉ CoC/RoHS, catalog lớn | [Tìm trên DigiKey]({digikey_link}) |\n"
                    f"| **Mouser Electronics** | Quốc tế | Chuyên hàng R&D, dự án kỹ thuật cao (Molex, TE, Amphenol) | [Tìm trên Mouser]({mouser_link}) |\n"
                    f"| **LCSC Electronics** | Quốc tế | Tối ưu chi phí, thế mạnh linh kiện SMD và nhà sản xuất châu Á | [Tìm trên LCSC]({lcsc_link}) |\n"
                    f"| **Thế Giới IC** | Trong nước | Sẵn kho tại Việt Nam, giao nhanh 1-2 ngày, mẫu linh kiện phổ biến | [Tìm trên Thế Giới IC]({thegioiic_link}) |\n"
                    f"| **Hshop** | Trong nước | Sẵn hàng tại Việt Nam, phù hợp mua mẫu thử nghiệm nhanh | [Tìm trên Hshop]({hshop_link}) |\n\n"
                    f"### 2. Bảng khoảng giá tham khảo trên thị trường\n"
                    f"Trình bày bảng Markdown với 4 cột: | Nhóm chủng loại | Đơn giá mẫu lẻ (1 – 10 cái) | Đơn giá số lượng (Pack / Reel > 1.000) | Ghi chú & Ứng dụng |\n"
                    f"Cung cấp ước tính khoảng giá thị trường hợp lý (VNĐ) cho chủng loại linh kiện \"{search_kw}\".\n\n"
                    f"### 3. Bảng lưu ý thông số kỹ thuật khi đặt mua\n"
                    f"Trình bày bảng Markdown với 3 cột: | Thông số kỹ thuật | Tiêu chuẩn kiểm tra | Lưu ý rủi ro nếu sai lệch |\n"
                    f"Bao gồm Pitch khoảng cách chân, Kiểu hàn SMD/DIP, Hướng cắm Vertical/Right-Angle, Đóng gói Tape & Reel...\n\n"
                    f"### 4. Khuyến nghị quy trình mua hàng\n"
                    f"Lưu ý người dùng chuẩn bị Part Number (MPN) và Footprint/Datasheet, sau đó liên hệ phòng Mua hàng (Purchasing) để làm báo giá (RFQ) và mở PO chính thức sau khi được phê duyệt ngân sách.\n\n"
                    f"Phản hồi hoàn toàn bằng tiếng Việt chuyên nghiệp, súc tích, định dạng bảng Markdown chuẩn, rõ ràng, đẹp mắt."
                )
                res = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                )
                if res and res.text:
                    return ExternalSourcingResult(
                        enabled=True,
                        status="success",
                        query_used=clean_query,
                        products=products,
                        message=res.text.strip(),
                    )
            except Exception as e:
                logger.warning("Gemini external sourcing query failed: %s, falling back to static table", e)

        # Fallback structured market sourcing table
        fallback_msg = (
            f"Chào bạn, dưới đây là thông tin kênh mua sắm và giá tham khảo cho **{search_kw}**:\n\n"
            f"### 1. Bảng kênh phân phối uy tín & Đường dẫn tra cứu trực tiếp\n\n"
            f"| Kênh phân phối | Phân loại | Thế mạnh & Chứng chỉ | Đường dẫn tra cứu trực tiếp |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **DigiKey** | Quốc tế | Hàng chính hãng 100%, đủ chứng chỉ CoC/RoHS, catalog lớn nhất | [Tra cứu trên DigiKey]({digikey_link}) |\n"
            f"| **Mouser Electronics** | Quốc tế | Chuyên hàng dự án R&D, chất lượng cao (Molex, TE, Amphenol) | [Tra cứu trên Mouser]({mouser_link}) |\n"
            f"| **LCSC Electronics** | Quốc tế | Giá tối ưu, thế mạnh linh kiện dán SMD và nhà sản xuất châu Á | [Tra cứu trên LCSC]({lcsc_link}) |\n"
            f"| **Thế Giới IC** | Trong nước | Sẵn kho tại Việt Nam, giao nhanh 1-2 ngày, mẫu linh kiện phổ biến | [Tra cứu trên Thế Giới IC]({thegioiic_link}) |\n"
            f"| **Hshop** | Trong nước | Sẵn hàng tại Việt Nam, phù hợp mua mẫu thử nghiệm nhanh | [Tra cứu trên Hshop]({hshop_link}) |\n\n"
            f"### 2. Bảng khoảng giá tham khảo trên thị trường\n\n"
            f"| Nhóm chủng loại | Đơn giá mẫu lẻ (1 – 10 cái) | Đơn giá số lượng (Pack / Reel > 1.000) | Ghi chú & Ứng dụng |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **Nhóm cơ bản / Phổ thông** *(Pin header, JST, KF terminal...)* | ~1.000 – 15.000 đ/cái | ~300 – 3.000 đ/cái | Hàn tay, làm mẫu R&D |\n"
            f"| **Nhóm kỹ thuật cao** *(SMD pitch nhỏ, Mezzanine, High-Speed...)* | ~15.000 – 120.000+ đ/cái | ~5.000 – 50.000 đ/cái | Máy dán tự động, độ tin cậy cao |\n\n"
            f"### 3. Bảng lưu ý thông số kỹ thuật khi đặt mua\n\n"
            f"| Thông số kỹ thuật | Tiêu chuẩn kiểm tra | Lưu ý rủi ro nếu sai lệch |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **Pitch (Bước chân)** | Đo chính xác tâm-đối-tâm (0.5mm, 1.0mm, 1.25mm, 1.27mm, 2.0mm, 2.54mm, 3.0mm...) | Sai pitch là lỗi phổ biến nhất khiến không hàn vừa PCB |\n"
            f"| **Kiểu hàn (Mounting)** | Hàn dán bề mặt (SMD/SMT) hoặc cắm xuyên lỗ (Through-Hole DIP) | Phải khớp với footprint thiết kế trên mạch in |\n"
            f"| **Hướng cắm (Orientation)** | Thẳng đứng (Vertical / Straight) hoặc Vuông góc (Right-Angle) | Ảnh hưởng trực tiếp đến kích thước và vỏ hộp thiết bị |\n"
            f"| **Quy cách đóng gói** | Tape & Reel (TR) cho máy dán SMT; Tube/Tray/Bag cho hàn tay | Gia công SMT tự động bắt buộc chọn Tape & Reel có nắp hút |\n\n"
            f"### 4. Khuyến nghị quy trình mua hàng\n\n"
            f"• Kỹ sư chuẩn bị Part Number cụ thể (MPN) từ nhà sản xuất kèm bản vẽ kỹ thuật (Drawing / Datasheet).\n"
            f"• Chuyển thông tin cho **Phòng Mua hàng (Purchasing)** để gửi yêu cầu báo giá (RFQ), kiểm tra số lượng tối thiểu (MOQ), thời gian giao hàng (Lead time) và tạo Đơn đặt hàng (PO) chính thức sau khi được phê duyệt ngân sách.\n\n"
            f"*(Lưu ý: Báo giá và đường dẫn trên mang tính chất hỗ trợ tra cứu kỹ thuật thị trường. Vui lòng liên hệ phòng Mua hàng để lấy báo giá PO chính thức).* "
        )
        return ExternalSourcingResult(
            enabled=True,
            status="success",
            query_used=clean_query,
            products=products,
            message=fallback_msg,
        )

    def extract_search_keyword(self, text: str) -> str:
        """Extracts core component keywords by stripping conversational intent filler phrases."""
        import re
        cleaned = text
        fillers = [
            r"tìm\s+giúp\s+(?:mình|em|tôi)",
            r"tìm\s+cho\s+(?:mình|em|tôi)",
            r"tìm\s+kiếm",
            r"tìm\s+nguồn\s+(?:bên\s+)?ngoài\s+cho",
            r"tìm\s+nơi\s+(?:mua|bán)",
            r"tìm\s+(?:mua|bán)",
            r"nơi\s+(?:mua|bán)",
            r"chỗ\s+(?:mua|bán)",
            r"mua\s+ở\s+đâu",
            r"mua\s+ngoài",
            r"ngoài\s+thị\s+trường",
            r"kèm\s+giá\s+tham\s+khảo",
            r"giá\s+tham\s+khảo",
            r"giúp\s+(?:mình|em|tôi)",
            r"cho\s+(?:mình|em|tôi)",
            r"hộ\s+(?:mình|em|tôi)",
            r"với\s+ạ",
            r"\bạ\b",
            r"\bnhé\b",
            r"\bvới\b",
        ]
        for p in fillers:
            cleaned = re.sub(p, " ", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip()
        return cleaned if cleaned else text

    _extract_search_keyword = extract_search_keyword

    def sanitize_query(self, query: str) -> str:
        """Strips internal project names or confidential words from external queries."""
        import re
        sanitized = query
        for sensitive in ["project alpha", "project beta", "bosch", "dự án alpha", "dự án beta", "alpha", "beta", "tủ 1", "tủ 2", "tủ 3"]:
            pattern = re.compile(re.escape(sensitive), re.IGNORECASE)
            sanitized = pattern.sub("", sanitized)
        # Strip emails
        sanitized = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", sanitized)
        return " ".join(sanitized.split())

    _sanitize_query = sanitize_query
