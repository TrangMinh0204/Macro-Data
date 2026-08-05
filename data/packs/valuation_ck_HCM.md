# VALUATION PACK — HCM (Ngành chứng khoán)

- Kỳ báo cáo: **Q2/2026** | Sinh lúc: 05/08/2026 15:49
- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/HCM/`, đọc qua `fund_pack.py` — không cần input thủ công.
- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.
- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.

## 1. Giá tham chiếu suy ra từ bội số

| Cách tính | Công thức | Kết quả (đồng/cp) |
|---|---|---:|
| Theo P/E | 1.358,17 × 20,03 | **27.204** |
| Theo P/B | 13.555,91 × 2,01 | **27.247** |
| Tham chiếu (trung bình) | — | **27.226** |

## 2. Cấu trúc tài chính

Số dư cuối kỳ Q2/2026, tỷ đồng (kỳ trước Q1/2026 dùng để tính bình quân):

| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |
|---|---:|---:|
| Tổng tài sản | 41.259 | 100,0% |
| FVTPL | 9.133 | 22,1% |
| Các khoản cho vay | 29.024 | 70,3% |
| HTM (ngắn + dài hạn) | 382 | 0,9% |
| Tiền và tương đương | 2.202 | 5,3% |
| Tổng nợ phải trả | 26.619 | 64,5% |
| Vay và nợ thuê TC ngắn hạn | 26.093 | 63,2% |
| Vốn chủ sở hữu | 14.640 | 35,5% |

- FVTPL + Cho vay / Tổng tài sản = **92,5%**
- Đòn bẩy Nợ/VCSH = **181,82%**

## 3. Kiểm tra nhanh hiệu quả (Q2/2026)

- Lợi nhuận gộp môi giới = 197 − 170 = **27 tỷ** → biên gộp **13,7%**
- Thu nhập lãi thuần đại diện = 766 + 9 − — = **— tỷ**
- Suất sinh lời cho vay quy năm (dư nợ bình quân Q1/2026→Q2/2026, ×4) = **10,72%**
- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **—**
- ROE trailing TTM (Q3/2025, Q4/2025, Q1/2026, Q2/2026) = 1.324/12.412 = **10,67%** so với ROE quý Vietstock **1,88%**

## 4. Định giá P/B hợp lý theo kịch bản

Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.

| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thận trọng | 12,5% | 4,0% | 13,0% | 25% | 0,94x | 7,6x | **12.803** |
| Cơ sở | 15,0% | 5,0% | 12,0% | 50% | 1,43x | 9,5x | **19.366** |
| Lạc quan | 16,5% | 5,5% | 11,5% | 25% | 1,83x | 11,1x | **24.853** |

- **Giá trị kỳ vọng có trọng số ≈ 19.097 đồng/cp**
- So với giá tham chiếu 27.226 đồng/cp: **thấp hơn khoảng 29,9%**

## 5. ROE mà thị giá đang kỳ vọng

- Với Ke = 12,0%, g = 5,0%, P/B = 2,01x: **ROE hàm ý = 19,07%**
- ROE hàm ý CAO hơn ROE trailing (10,67%) → chênh lệch phản ánh kỳ vọng thị trường về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.

## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = 5,0%)

| ROE \ Ke | 11,5% | 12,0% | 12,5% | 13,0% |
|---|---:|---:|---:|---:|
| 12,5% | 15.641 | 14.524 | 13.556 | 12.709 |
| 13,5% | 17.727 | 16.461 | 15.363 | 14.403 |
| 14,5% | 19.812 | 18.397 | 17.171 | 16.098 |
| 15,0% | 20.855 | 19.366 | 18.075 | 16.945 |
| 15,5% | 21.898 | 20.334 | 18.978 | 17.792 |
| 16,5% | 23.984 | 22.270 | 20.786 | 19.487 |

## 7. Residual Income & DDM

- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.HCM.residual_income` trong config/valuation_ck.yml để kích hoạt.
- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.HCM.ddm` để kích hoạt.

---
*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*

*This is research and analysis only, not personalized financial advice.*