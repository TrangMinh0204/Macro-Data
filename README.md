# 🇻🇳 Vietnam Intelligence Collector

> **Thu thập tự động 14 nhóm thông tin mỗi 1 tiếng — không cần bật máy**

Hệ thống chạy hoàn toàn trên **GitHub Actions (free)** + **Jina Reader (free)**.  
Output: file `.md` theo giờ → paste vào AI Investment Team khi cần.

---

## 14 Nhóm thông tin

| # | Nhóm | Nguồn |
|---|------|-------|
| 1 | 🏥 Dịch bệnh & Thiên tai TG + VN | WHO, ReliefWeb, VnExpress |
| 2 | 🌍 Địa chính trị Thế giới | Reuters, Al Jazeera, BBC |
| 3 | 💹 Kinh tế & Tài chính TG | Reuters, Trading Economics, CafeF |
| 4 | 📦 Hàng hóa TG + VN | Trading Economics, CafeF |
| 5 | 🥇 Vàng & Bạc TG + VN | Kitco, SJC, DOJI |
| 6 | 🏦 Lãi suất Mỹ — Fed | FederalReserve.gov, CME FedWatch |
| 7 | 👷 Lao động Mỹ — NFP & Thất nghiệp | BLS.gov |
| 8 | 📈 Lạm phát & CPI Mỹ | BLS.gov, Trading Economics |
| 9 | 🛢️ Giá dầu TG + VN | EIA, Trading Economics, CafeF |
| 10 | 📜 Văn bản pháp luật VN | ThuvienPhapluat, ChinhPhu.vn |
| 11 | 🏛️ Chính sách Tài chính – Ngân hàng VN | NHNN, Bộ Tài chính, CafeF |
| 12 | 💱 Tỷ giá VND/USD | Vietcombank, NHNN, Trading Economics |
| 13 | 🎙️ Phát biểu lãnh đạo VN | ChinhPhu.vn, QH, Nhân dân, VnExpress |
| 14 | 🏛️ Trump + Hưng Yên / HCM / Hà Nội | WhiteHouse.gov, các cổng địa phương |

---

## Cấu trúc thư mục

```
output/
├── INDEX.md              ← Danh sách toàn bộ report
├── 2026-06-27/
│   ├── 08-00.md          ← Report 8:00 ICT
│   ├── 09-00.md
│   └── ...
└── 2026-06-28/
    └── ...
```

---

## Cách dùng

1. Xem file report mới nhất trong `output/INDEX.md`
2. Mở file `.md` tương ứng
3. Copy toàn bộ nội dung → paste vào Claude (AI Investment Team)

---

## Kỹ thuật

- **Scheduler:** GitHub Actions cron `0 * * * *` (mỗi 1 tiếng)
- **Crawler:** Jina Reader (`r.jina.ai`) — free, không cần API key
- **Runtime:** Python 3.11 — chỉ dùng stdlib, không cần cài thêm gì
- **Chi phí:** $0 — nằm trong giới hạn free của GitHub (2,000 phút/tháng)
- **Dùng thực tế:** ~720 phút/tháng (30 ngày × 24 giờ × ~1 phút/run)

---

*Tự động tạo bởi Vietnam Intelligence Collector*
