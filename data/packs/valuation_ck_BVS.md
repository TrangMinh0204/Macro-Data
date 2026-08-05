# VALUATION PACK — BVS (Ngành chứng khoán)

- Kỳ báo cáo: **Q2/2026** | Sinh lúc: 05/08/2026 22:25
- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/BVS/`, đọc qua `fund_pack.py` — không cần input thủ công.
- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.
- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.

## 1. Giá tham chiếu suy ra từ bội số

| Cách tính | Công thức | Kết quả (đồng/cp) |
|---|---|---:|
| Theo P/E | 2.436,44 × 11,08 | **26.996** |
| Theo P/B | 37.423,21 × 0,72 | **26.945** |
| Tham chiếu (trung bình) | — | **26.970** |

## 2. Cấu trúc tài chính

Số dư cuối kỳ Q2/2026, tỷ đồng (kỳ trước Q1/2026 dùng để tính bình quân):

| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |
|---|---:|---:|
| Tổng tài sản | 6.424 | 100,0% |
| FVTPL | 569 | 8,9% |
| Các khoản cho vay | 4.406 | 68,6% |
| HTM (ngắn + dài hạn) | 985 | 15,3% |
| Tiền và tương đương | 30 | 0,5% |
| Tổng nợ phải trả | 3.722 | 57,9% |
| Vay và nợ thuê TC ngắn hạn | 3.449 | 53,7% |
| Vốn chủ sở hữu | 2.702 | 42,1% |

- FVTPL + Cho vay / Tổng tài sản = **77,4%**
- Đòn bẩy Nợ/VCSH = **137,75%**

## 3. Kiểm tra nhanh hiệu quả (Q2/2026)

- Lợi nhuận gộp môi giới = 82 − 83 = **-1 tỷ** → biên gộp **-1,2%**
- Thu nhập lãi thuần đại diện = 131 + 14 − 61 = **84 tỷ**
- Suất sinh lời cho vay quy năm (dư nợ bình quân Q1/2026→Q2/2026, ×4) = **11,37%**
- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **6,51%**
- ROE trailing TTM (Q3/2025, Q4/2025, Q1/2026, Q2/2026) = 175/2.642 = **6,63%** so với ROE quý Vietstock **1,58%**

## 4. Định giá P/B hợp lý theo kịch bản

Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.

| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thận trọng | 12,5% | 4,0% | 13,0% | 25% | 0,94x | 7,6x | **35.344** |
| Cơ sở | 15,0% | 5,0% | 12,0% | 50% | 1,43x | 9,5x | **53.462** |
| Lạc quan | 16,5% | 5,5% | 11,5% | 25% | 1,83x | 11,1x | **68.609** |

- **Giá trị kỳ vọng có trọng số ≈ 52.719 đồng/cp**
- So với giá tham chiếu 26.970 đồng/cp: **cao hơn khoảng 95,5%**

## 5. ROE mà thị giá đang kỳ vọng

- Với Ke = 12,0%, g = 5,0%, P/B = 0,72x: **ROE hàm ý = 10,04%**
- ROE hàm ý CAO hơn ROE trailing (6,63%) → chênh lệch phản ánh kỳ vọng thị trường về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.

## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = 5,0%)

| ROE \ Ke | 11,5% | 12,0% | 12,5% | 13,0% |
|---|---:|---:|---:|---:|
| 12,5% | 43.181 | 40.096 | 37.423 | 35.084 |
| 13,5% | 48.938 | 45.442 | 42.413 | 39.762 |
| 14,5% | 54.695 | 50.789 | 47.403 | 44.440 |
| 15,0% | 57.574 | 53.462 | 49.898 | 46.779 |
| 15,5% | 60.453 | 56.135 | 52.392 | 49.118 |
| 16,5% | 66.210 | 61.481 | 57.382 | 53.796 |

## 7. Residual Income & DDM

- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.BVS.residual_income` trong config/valuation_ck.yml để kích hoạt.
- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.BVS.ddm` để kích hoạt.

---
*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*

*This is research and analysis only, not personalized financial advice.*