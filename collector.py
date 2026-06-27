"""
Vietnam Intelligence Collector
================================
Thu thập 14 nhóm thông tin mỗi 1 tiếng, output ra file .md.
Chạy tự động qua GitHub Actions — không cần bật máy.

Nguồn: Jina Reader (free, không cần API key)
Output: output/YYYY-MM-DD/HH-MM.md
"""

import os
import json
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error
import re
from pathlib import Path

# ── Cấu hình ──────────────────────────────────────────────────────────────────

TIMEZONE_OFFSET = 7  # ICT = UTC+7

# Jina Reader: chuyển URL bất kỳ → markdown sạch (miễn phí)
JINA_BASE = "https://r.jina.ai/"

# Timeout mỗi request (giây)
REQUEST_TIMEOUT = 20

# Số ký tự tối đa lấy từ mỗi nguồn (tránh file quá nặng)
MAX_CHARS_PER_SOURCE = 3000

# ── Định nghĩa 14 nhóm thông tin ─────────────────────────────────────────────

GROUPS = [
    {
        "id": 1,
        "name": "Dịch bệnh & Thiên tai Thế giới và Việt Nam",
        "icon": "🏥",
        "sources": [
            {"name": "WHO Disease Outbreak News", "url": "https://www.who.int/emergencies/disease-outbreak-news"},
            {"name": "ReliefWeb Disasters VN", "url": "https://reliefweb.int/country/vnm"},
            {"name": "VnExpress Sức khỏe", "url": "https://vnexpress.net/suc-khoe"},
        ],
    },
    {
        "id": 2,
        "name": "Địa chính trị Thế giới",
        "icon": "🌍",
        "sources": [
            {"name": "Reuters World News", "url": "https://www.reuters.com/world/"},
            {"name": "Al Jazeera", "url": "https://www.aljazeera.com/"},
            {"name": "BBC World", "url": "https://www.bbc.com/news/world"},
        ],
    },
    {
        "id": 3,
        "name": "Kinh tế & Tài chính Thế giới",
        "icon": "💹",
        "sources": [
            {"name": "Reuters Business", "url": "https://www.reuters.com/business/"},
            {"name": "Trading Economics World", "url": "https://tradingeconomics.com/"},
            {"name": "CafeF Thế giới", "url": "https://cafef.vn/kinh-te-the-gioi.chn"},
        ],
    },
    {
        "id": 4,
        "name": "Thị trường Hàng hóa Thế giới và Việt Nam",
        "icon": "📦",
        "sources": [
            {"name": "Trading Economics Commodities", "url": "https://tradingeconomics.com/commodity"},
            {"name": "CafeF Hàng hóa", "url": "https://cafef.vn/hang-hoa.chn"},
            {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/kinh-doanh"},
        ],
    },
    {
        "id": 5,
        "name": "Vàng & Bạc Thế giới và Việt Nam",
        "icon": "🥇",
        "sources": [
            {"name": "Kitco Gold Silver", "url": "https://www.kitco.com/"},
            {"name": "Giá vàng SJC", "url": "https://sjc.com.vn/"},
            {"name": "DOJI giá vàng", "url": "https://doji.vn/gia-vang/"},
        ],
    },
    {
        "id": 6,
        "name": "Lãi suất Mỹ — Fed",
        "icon": "🏦",
        "sources": [
            {"name": "Federal Reserve News", "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm"},
            {"name": "CME FedWatch Tool", "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"},
            {"name": "Trading Economics Fed Rate", "url": "https://tradingeconomics.com/united-states/interest-rate"},
        ],
    },
    {
        "id": 7,
        "name": "Lao động Mỹ — NFP & Thất nghiệp",
        "icon": "👷",
        "sources": [
            {"name": "BLS News Releases", "url": "https://www.bls.gov/news.release/"},
            {"name": "Trading Economics US Labor", "url": "https://tradingeconomics.com/united-states/unemployment-rate"},
        ],
    },
    {
        "id": 8,
        "name": "Lạm phát & CPI Mỹ",
        "icon": "📈",
        "sources": [
            {"name": "BLS CPI Summary", "url": "https://www.bls.gov/cpi/"},
            {"name": "Trading Economics US CPI", "url": "https://tradingeconomics.com/united-states/inflation-cpi"},
        ],
    },
    {
        "id": 9,
        "name": "Giá dầu Thế giới và Việt Nam",
        "icon": "🛢️",
        "sources": [
            {"name": "EIA Oil Price", "url": "https://www.eia.gov/petroleum/"},
            {"name": "Trading Economics Crude Oil", "url": "https://tradingeconomics.com/commodity/crude-oil"},
            {"name": "CafeF Dầu khí", "url": "https://cafef.vn/dau-khi.chn"},
        ],
    },
    {
        "id": 10,
        "name": "Văn bản pháp luật Việt Nam",
        "icon": "📜",
        "sources": [
            {"name": "Thư viện Pháp luật", "url": "https://thuvienphapluat.vn/van-ban/moi-nhat"},
            {"name": "Cổng Chính phủ - Văn bản", "url": "https://vanban.chinhphu.vn/"},
        ],
    },
    {
        "id": 11,
        "name": "Chính sách Tài chính – Ngân hàng Việt Nam",
        "icon": "🏛️",
        "sources": [
            {"name": "NHNN - Ngân hàng Nhà nước", "url": "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu"},
            {"name": "Bộ Tài chính", "url": "https://www.mof.gov.vn/webcenter/portal/vclvcstc"},
            {"name": "CafeF Ngân hàng", "url": "https://cafef.vn/ngan-hang.chn"},
        ],
    },
    {
        "id": 12,
        "name": "Tỷ giá VND/USD",
        "icon": "💱",
        "sources": [
            {"name": "Vietcombank Tỷ giá", "url": "https://vietcombank.com.vn/ExchangeRates"},
            {"name": "Trading Economics USD/VND", "url": "https://tradingeconomics.com/usdt-vnd:cur"},
            {"name": "NHNN Tỷ giá trung tâm", "url": "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/tkttnh/tghtnnh"},
        ],
    },
    {
        "id": 13,
        "name": "Phát biểu & Ý chí lãnh đạo Việt Nam",
        "icon": "🎙️",
        "note": "Theo dõi: Tô Lâm (TBT kiêm CTN), Trần Thanh Mẫn (CT QH), Lê Minh Hưng (Thủ tướng), Nguyễn Tấn Dũng, các Phó Thủ tướng",
        "sources": [
            {"name": "Cổng Chính phủ", "url": "https://chinhphu.vn/"},
            {"name": "Quốc hội Việt Nam", "url": "https://quochoi.vn/"},
            {"name": "Nhân dân - Lãnh đạo", "url": "https://nhandan.vn/chinh-tri"},
            {"name": "VnExpress Chính trị", "url": "https://vnexpress.net/chinh-tri"},
        ],
    },
    {
        "id": 14,
        "name": "Trump & Chính sách Hưng Yên / HCM / Hà Nội",
        "icon": "🏛️",
        "note": "Theo dõi: Phát biểu Donald Trump + Nghị quyết phát triển 3 địa phương",
        "sources": [
            {"name": "White House News", "url": "https://www.whitehouse.gov/news/"},
            {"name": "Hưng Yên Portal", "url": "https://hungyen.gov.vn/"},
            {"name": "HCMC Portal", "url": "https://www.hochiminhcity.gov.vn/"},
            {"name": "Hà Nội Portal", "url": "https://hanoi.gov.vn/"},
        ],
    },
]

# ── Hàm thu thập dữ liệu ──────────────────────────────────────────────────────

def fetch_via_jina(url: str) -> str:
    """Lấy nội dung URL qua Jina Reader (free, không cần API key)."""
    jina_url = JINA_BASE + url
    req = urllib.request.Request(
        jina_url,
        headers={
            "User-Agent": "Mozilla/5.0 Vietnam-Intelligence-Collector/1.0",
            "Accept": "text/plain, text/markdown, */*",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            # Cắt bớt nếu quá dài
            return content[:MAX_CHARS_PER_SOURCE]
    except urllib.error.HTTPError as e:
        return f"[Lỗi HTTP {e.code}: {e.reason}]"
    except urllib.error.URLError as e:
        return f"[Lỗi kết nối: {e.reason}]"
    except Exception as e:
        return f"[Lỗi: {str(e)[:100]}]"


def clean_content(raw: str) -> str:
    """Làm sạch nội dung crawl — bỏ noise, giữ lại phần có giá trị."""
    if raw.startswith("[Lỗi"):
        return raw

    # Bỏ các dòng quá ngắn (menu, navigation)
    lines = raw.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 15:
            continue
        # Bỏ dòng chỉ toàn URL
        if stripped.startswith("http") and " " not in stripped:
            continue
        # Bỏ dòng markdown toàn dấu ===, ---
        if re.match(r'^[=\-_*]{3,}$', stripped):
            continue
        cleaned.append(stripped)

    result = "\n".join(cleaned[:80])  # Giữ tối đa 80 dòng đầu có nội dung
    return result[:MAX_CHARS_PER_SOURCE]


def collect_group(group: dict) -> dict:
    """Thu thập toàn bộ nguồn trong một nhóm."""
    results = []
    for source in group["sources"]:
        print(f"  → Fetching: {source['name']}...")
        raw = fetch_via_jina(source["url"])
        content = clean_content(raw)
        results.append({
            "source": source["name"],
            "url": source["url"],
            "content": content,
            "ok": not content.startswith("[Lỗi"),
        })
        time.sleep(1.5)  # Tránh rate limit
    return results


# ── Hàm tạo file Markdown output ─────────────────────────────────────────────

def build_markdown(all_data: list, run_time: datetime.datetime) -> str:
    """Tạo nội dung file .md từ dữ liệu đã thu thập."""

    time_str = run_time.strftime("%Y-%m-%d %H:%M ICT")
    date_str = run_time.strftime("%Y-%m-%d")
    hour_str = run_time.strftime("%H:%M")

    lines = [
        f"# 🇻🇳 Vietnam Intelligence Report",
        f"",
        f"> **Thời gian thu thập:** {time_str}  ",
        f"> **Chu kỳ:** Tự động mỗi 1 tiếng — GitHub Actions  ",
        f"> **Nguồn:** Jina Reader (free crawl)  ",
        f"> **Dùng cho:** AI Investment Team — paste vào Claude khi cần",
        f"",
        f"---",
        f"",
    ]

    for group_data in all_data:
        group = group_data["group"]
        sources_data = group_data["sources"]

        lines.append(f"## {group['icon']} Nhóm {group['id']}: {group['name']}")
        lines.append("")

        if "note" in group:
            lines.append(f"*{group['note']}*")
            lines.append("")

        ok_count = sum(1 for s in sources_data if s["ok"])
        lines.append(f"*Thu thập từ {len(sources_data)} nguồn — {ok_count} thành công*")
        lines.append("")

        for src in sources_data:
            status = "✅" if src["ok"] else "❌"
            lines.append(f"### {status} {src['source']}")
            lines.append(f"*Nguồn: {src['url']}*")
            lines.append("")
            if src["ok"] and src["content"]:
                # Chỉ lấy 60 dòng đầu mỗi nguồn trong file tổng hợp
                content_lines = src["content"].split("\n")[:60]
                lines.append("\n".join(content_lines))
            else:
                lines.append(f"_{src['content']}_")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Footer tóm tắt
    total_sources = sum(len(g["sources"]) for g in all_data)
    total_ok = sum(sum(1 for s in g["sources"] if s["ok"]) for g in all_data)

    lines.append(f"## 📊 Tóm tắt thu thập")
    lines.append("")
    lines.append(f"| Chỉ tiêu | Kết quả |")
    lines.append(f"|---|---|")
    lines.append(f"| Tổng số nguồn | {total_sources} |")
    lines.append(f"| Thu thập thành công | {total_ok} |")
    lines.append(f"| Thất bại | {total_sources - total_ok} |")
    lines.append(f"| Thời gian | {time_str} |")
    lines.append("")
    lines.append(f"*Report tự động tạo bởi Vietnam Intelligence Collector — github.com/TrangMinh0204/Macro-Data*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Tính giờ Việt Nam (ICT = UTC+7)
    utc_now = datetime.datetime.utcnow()
    vn_now = utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)

    date_str = vn_now.strftime("%Y-%m-%d")
    hour_str = vn_now.strftime("%H-%M")

    print(f"\n{'='*60}")
    print(f"Vietnam Intelligence Collector")
    print(f"Thời gian: {vn_now.strftime('%Y-%m-%d %H:%M ICT')}")
    print(f"{'='*60}\n")

    # Tạo thư mục output
    output_dir = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{hour_str}.md"

    # Thu thập từng nhóm
    all_data = []
    for group in GROUPS:
        print(f"\n[Nhóm {group['id']}] {group['icon']} {group['name']}")
        sources_data = collect_group(group)
        all_data.append({"group": group, "sources": sources_data})

    # Tạo file markdown
    print(f"\n{'='*60}")
    print(f"Tạo file: {output_file}")
    md_content = build_markdown(all_data, vn_now)
    output_file.write_text(md_content, encoding="utf-8")

    # Tạo file index (danh sách các report theo ngày)
    index_file = Path("output") / "INDEX.md"
    update_index(index_file, date_str, hour_str, vn_now)

    print(f"✅ Hoàn thành! File: {output_file}")
    print(f"   Kích thước: {len(md_content):,} ký tự")


def update_index(index_file: Path, date_str: str, hour_str: str, vn_now: datetime.datetime):
    """Cập nhật file INDEX.md — danh sách toàn bộ report."""
    time_str = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    entry = f"- [{time_str}](output/{date_str}/{hour_str}.md)"

    if index_file.exists():
        existing = index_file.read_text(encoding="utf-8")
        # Thêm entry mới vào đầu (sau header)
        lines = existing.split("\n")
        # Tìm vị trí sau header (dòng đầu tiên bắt đầu bằng -)
        insert_at = 5  # Sau header ~5 dòng
        for i, line in enumerate(lines):
            if line.startswith("- ["):
                insert_at = i
                break
        lines.insert(insert_at, entry)
        index_file.write_text("\n".join(lines), encoding="utf-8")
    else:
        content = f"""# Vietnam Intelligence — Index

Danh sách toàn bộ report tự động theo giờ.

{entry}
"""
        index_file.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
