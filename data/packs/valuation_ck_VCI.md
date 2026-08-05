# VALUATION PACK — VCI (Ngành chứng khoán)

- Kỳ báo cáo: **Q2/2026** | Sinh lúc: 05/08/2026 15:37
- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/VCI/`, đọc qua `fund_pack.py` — không cần input thủ công.
- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.
- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.

## 1. Giá tham chiếu suy ra từ bội số

| Cách tính | Công thức | Kết quả (đồng/cp) |
|---|---|---:|
| Theo P/E | 1.724,47 × 14,12 | **24.350** |
| Theo P/B | 14.933,27 × 1,63 | **24.341** |
| Tham chiếu (trung bình) | — | **24.345** |

## 2. Cấu trúc tài chính

Số dư cuối kỳ Q2/2026, tỷ đồng (kỳ trước Q1/2026 dùng để tính bình quân):

| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |
|---|---:|---:|
| Tổng tài sản | 39.727 | 100,0% |
| FVTPL | 2.463 | 6,2% |
| Các khoản cho vay | 17.146 | 43,2% |
| HTM (ngắn + dài hạn) | 300 | 0,8% |
| Tiền và tương đương | 3.649 | 9,2% |
| Tổng nợ phải trả | 22.589 | 56,9% |
| Vay và nợ thuê TC ngắn hạn | 21.704 | 54,6% |
| Vốn chủ sở hữu | 17.138 | 43,1% |

- FVTPL + Cho vay / Tổng tài sản = **49,4%**
- Đòn bẩy Nợ/VCSH = **131,81%**

## 3. Kiểm tra nhanh hiệu quả (Q2/2026)

- Lợi nhuận gộp môi giới = 226 − 186 = **40 tỷ** → biên gộp **17,7%**
- Thu nhập lãi thuần đại diện = 463 + 6 − 319 = **150 tỷ**
- Suất sinh lời cho vay quy năm (dư nợ bình quân Q1/2026→Q2/2026, ×4) = **10,97%**
- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **6,39%**
- ROE trailing TTM (Q3/2025, Q4/2025, Q1/2026, Q2/2026) = 1.455/14.788 = **9,84%** so với ROE quý Vietstock **1,45%**

## 4. Định giá P/B hợp lý theo kịch bản

Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.

| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thận trọng | 12,5% | 4,0% | 13,0% | 25% | 0,94x | 7,6x | **14.104** |
| Cơ sở | 15,0% | 5,0% | 12,0% | 50% | 1,43x | 9,5x | **21.333** |
| Lạc quan | 16,5% | 5,5% | 11,5% | 25% | 1,83x | 11,1x | **27.378** |

- **Giá trị kỳ vọng có trọng số ≈ 21.037 đồng/cp**
- So với giá tham chiếu 24.345 đồng/cp: **thấp hơn khoảng 13,6%**

## 5. ROE mà thị giá đang kỳ vọng

- Với Ke = 12,0%, g = 5,0%, P/B = 1,63x: **ROE hàm ý = 16,41%**
- ROE hàm ý CAO hơn ROE trailing (9,84%) → chênh lệch phản ánh kỳ vọng thị trường về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.

## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = 5,0%)

| ROE \ Ke | 11,5% | 12,0% | 12,5% | 13,0% |
|---|---:|---:|---:|---:|
| 12,5% | 17.231 | 16.000 | 14.933 | 14.000 |
| 13,5% | 19.528 | 18.133 | 16.924 | 15.867 |
| 14,5% | 21.826 | 20.267 | 18.915 | 17.733 |
| 15,0% | 22.974 | 21.333 | 19.911 | 18.667 |
| 15,5% | 24.123 | 22.400 | 20.907 | 19.600 |
| 16,5% | 26.420 | 24.533 | 22.898 | 21.467 |

## 7. Residual Income & DDM

- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.VCI.residual_income` trong config/valuation_ck.yml để kích hoạt.
- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.VCI.ddm` để kích hoạt.

---
*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*

*This is research and analysis only, not personalized financial advice.*