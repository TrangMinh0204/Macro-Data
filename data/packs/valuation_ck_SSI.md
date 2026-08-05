# VALUATION PACK — SSI (Ngành chứng khoán)

- Kỳ báo cáo: **Q2/2026** | Sinh lúc: 05/08/2026 13:09
- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/SSI/`, đọc qua `fund_pack.py` — không cần input thủ công.
- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.
- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.

## 1. Giá tham chiếu suy ra từ bội số

| Cách tính | Công thức | Kết quả (đồng/cp) |
|---|---|---:|
| Theo P/E | 2.166,17 × 12,35 | **26.752** |
| Theo P/B | 16.347,80 × 1,64 | **26.810** |
| Tham chiếu (trung bình) | — | **26.781** |

## 2. Cấu trúc tài chính

Số dư cuối kỳ Q2/2026, tỷ đồng (kỳ trước Q1/2026 dùng để tính bình quân):

| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |
|---|---:|---:|
| Tổng tài sản | 96.461 | 100,0% |
| FVTPL | 44.114 | 45,7% |
| Các khoản cho vay | 40.473 | 42,0% |
| HTM (ngắn + dài hạn) | 7.581 | 7,9% |
| Tiền và tương đương | 532 | 0,6% |
| Tổng nợ phải trả | 55.737 | 57,8% |
| Vay và nợ thuê TC ngắn hạn | 54.038 | 56,0% |
| Vốn chủ sở hữu | 40.724 | 42,2% |

- FVTPL + Cho vay / Tổng tài sản = **87,7%**
- Đòn bẩy Nợ/VCSH = **136,87%**

## 3. Kiểm tra nhanh hiệu quả (Q2/2026)

- Lợi nhuận gộp môi giới = 462 − 341 = **121 tỷ** → biên gộp **26,2%**
- Thu nhập lãi thuần đại diện = 1.091 + 129 − 812 = **408 tỷ**
- Suất sinh lời cho vay quy năm (dư nợ bình quân Q1/2026→Q2/2026, ×4) = **11,28%**
- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **6,13%**
- ROE trailing TTM (Q3/2025, Q4/2025, Q1/2026, Q2/2026) = 4.801/34.665 = **13,85%** so với ROE quý Vietstock **3,06%**

## 4. Định giá P/B hợp lý theo kịch bản

Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.

| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thận trọng | 12,5% | 4,0% | 13,0% | 25% | 0,94x | 7,6x | **15.440** |
| Cơ sở | 15,0% | 5,0% | 12,0% | 50% | 1,43x | 9,5x | **23.354** |
| Lạc quan | 16,5% | 5,5% | 11,5% | 25% | 1,83x | 11,1x | **29.971** |

- **Giá trị kỳ vọng có trọng số ≈ 23.030 đồng/cp**
- So với giá tham chiếu 26.781 đồng/cp: **thấp hơn khoảng 14,0%**

## 5. ROE mà thị giá đang kỳ vọng

- Với Ke = 12,0%, g = 5,0%, P/B = 1,64x: **ROE hàm ý = 16,48%**
- ROE hàm ý CAO hơn ROE trailing (13,85%) → chênh lệch phản ánh kỳ vọng thị trường về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.

## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = 5,0%)

| ROE \ Ke | 11,5% | 12,0% | 12,5% | 13,0% |
|---|---:|---:|---:|---:|
| 12,5% | 18.863 | 17.516 | 16.348 | 15.326 |
| 13,5% | 21.378 | 19.851 | 18.528 | 17.370 |
| 14,5% | 23.893 | 22.186 | 20.707 | 19.413 |
| 15,0% | 25.150 | 23.354 | 21.797 | 20.435 |
| 15,5% | 26.408 | 24.522 | 22.887 | 21.456 |
| 16,5% | 28.923 | 26.857 | 25.067 | 23.500 |

## 7. Residual Income & DDM

- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.SSI.residual_income` trong config/valuation_ck.yml để kích hoạt.
- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.SSI.ddm` để kích hoạt.

---
*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*

*This is research and analysis only, not personalized financial advice.*