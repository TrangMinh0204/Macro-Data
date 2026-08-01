# State — AI Investment Team

Cập nhật lần cuối: (chưa có — file khởi tạo 01/08/2026, chờ phiên phân tích đầu tiên)

---

## 1. Regime hiện hành

- (chưa xác lập)

## 2. Bảng score đang theo dõi

- (chưa có dữ liệu — BS/P score, checklist đỉnh x/10, BCS... sẽ điền khi có phiên phân tích đầu tiên)

## 3. Kết luận EOD gần nhất

- (chưa có)

## 4. Điều kiện vô hiệu hóa đang mở

- (không có)

## 5. Watchlist

Mỗi mã một dòng, bắt đầu bằng "- " theo sau là mã 3-4 ký tự viết hoa.
Job B (price-data.yml) đọc đúng mục này mỗi lần chạy để biết cần cache
thêm mã nào ngoài VN30 + HNX30.

- (chưa có mã nào)

---

## Định dạng STATE_UPDATE

Claude dán khối này vào cuối mỗi báo cáo Morning Prep / EOD. User copy
nguyên khối, dán đè vào các mục tương ứng ở trên, rồi commit file này.

```
STATE_UPDATE
Ngày: YYYY-MM-DD
Regime: ...
Score: ...
Kết luận: ...
Invalidation mở: ...
Watchlist: MÃ1, MÃ2, ...
```
