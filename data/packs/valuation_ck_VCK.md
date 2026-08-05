# VALUATION PACK — VCK (Ngành chứng khoán)

- Kỳ báo cáo: **Q2/2026** | Sinh lúc: 05/08/2026 15:49
- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/VCK/`, đọc qua `fund_pack.py` — không cần input thủ công.
- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.
- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.

## 1. Giá tham chiếu suy ra từ bội số

| Cách tính | Công thức | Kết quả (đồng/cp) |
|---|---|---:|
| Theo P/E | 2.511,38 × 13,18 | **33.100** |
| Theo P/B | 12.816,14 × 2,58 | **33.066** |
| Tham chiếu (trung bình) | — | **33.083** |

## 2. Cấu trúc tài chính

Số dư cuối kỳ Q2/2026, tỷ đồng (kỳ trước Q1/2026 dùng để tính bình quân):

| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |
|---|---:|---:|
| Tổng tài sản | 47.889 | 100,0% |
| FVTPL | 6.464 | 13,5% |
| Các khoản cho vay | 31.311 | 65,4% |
| HTM (ngắn + dài hạn) | 2.056 | 4,3% |
| Tiền và tương đương | 3.360 | 7,0% |
| Tổng nợ phải trả | 16.683 | 34,8% |
| Vay và nợ thuê TC ngắn hạn | 10.639 | 22,2% |
| Vốn chủ sở hữu | 31.206 | 65,2% |

- FVTPL + Cho vay / Tổng tài sản = **78,9%**
- Đòn bẩy Nợ/VCSH = **53,46%**

## 3. Kiểm tra nhanh hiệu quả (Q2/2026)

- Lợi nhuận gộp môi giới = 634 − 578 = **56 tỷ** → biên gộp **8,8%**
- Thu nhập lãi thuần đại diện = 1.031 + 66 − 241 = **856 tỷ**
- Suất sinh lời cho vay quy năm (dư nợ bình quân Q1/2026→Q2/2026, ×4) = **13,36%**
- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **7,02%**
- ROE trailing TTM (Q3/2025, Q4/2025, Q1/2026, Q2/2026) = 4.480/22.004 = **20,36%** so với ROE quý Vietstock **3,60%**

## 4. Định giá P/B hợp lý theo kịch bản

Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.

| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thận trọng | 12,5% | 4,0% | 13,0% | 25% | 0,94x | 7,6x | **12.104** |
| Cơ sở | 15,0% | 5,0% | 12,0% | 50% | 1,43x | 9,5x | **18.309** |
| Lạc quan | 16,5% | 5,5% | 11,5% | 25% | 1,83x | 11,1x | **23.496** |

- **Giá trị kỳ vọng có trọng số ≈ 18.054 đồng/cp**
- So với giá tham chiếu 33.083 đồng/cp: **thấp hơn khoảng 45,4%**

## 5. ROE mà thị giá đang kỳ vọng

- Với Ke = 12,0%, g = 5,0%, P/B = 2,58x: **ROE hàm ý = 23,06%**
- ROE hàm ý CAO hơn ROE trailing (20,36%) → chênh lệch phản ánh kỳ vọng thị trường về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.

## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = 5,0%)

| ROE \ Ke | 11,5% | 12,0% | 12,5% | 13,0% |
|---|---:|---:|---:|---:|
| 12,5% | 14.788 | 13.732 | 12.816 | 12.015 |
| 13,5% | 16.760 | 15.562 | 14.525 | 13.617 |
| 14,5% | 18.731 | 17.393 | 16.234 | 15.219 |
| 15,0% | 19.717 | 18.309 | 17.088 | 16.020 |
| 15,5% | 20.703 | 19.224 | 17.943 | 16.821 |
| 16,5% | 22.675 | 21.055 | 19.651 | 18.423 |

## 7. Residual Income & DDM

- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.VCK.residual_income` trong config/valuation_ck.yml để kích hoạt.
- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.VCK.ddm` để kích hoạt.

---
*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*

*This is research and analysis only, not personalized financial advice.*