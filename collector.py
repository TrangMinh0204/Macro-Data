"""
Vietnam Intelligence Collector v2
===================================
Nâng cấp: RSS Feed + Jina Reader + Full article cho tin quan trọng
- RSS khi có → headline + link + summary sạch
- Jina fallback → nguồn không có RSS
- Auto-detect tin quan trọng → fetch full nội dung bài đó

Output: output/YYYY-MM-DD/HH-MM.md (mỗi 1 tiếng)
"""

import time
import datetime
import urllib.request
import urllib.error
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Cấu hình ──────────────────────────────────────────────────────────────────

TIMEZONE_OFFSET  = 7        # ICT = UTC+7
REQUEST_TIMEOUT  = 25       # giây mỗi request
MAX_ITEMS_PER_RSS = 8       # số tin tối đa lấy từ mỗi RSS feed
MAX_CHARS_JINA   = 4000     # ký tự tối đa từ Jina fallback
MAX_CHARS_FULL   = 6000     # ký tự tối đa khi đọc full bài
JINA_BASE        = "https://r.jina.ai/"

# Keyword nhận diện tin quan trọng → fetch full nội dung
IMPORTANT_KEYWORDS = [
    # Lãnh đạo VN
    "tô lâm", "lê minh hưng", "trần thanh mẫn", "nguyễn tấn dũng",
    "thủ tướng", "tổng bí thư", "chủ tịch nước", "chủ tịch quốc hội",
    "phó thủ tướng", "bộ trưởng",
    # Lãnh đạo Mỹ
    "trump", "donald trump", "white house", "nhà trắng",
    # Chính sách VN
    "nghị quyết", "nghị định", "thông tư", "luật", "quyết định",
    "nhnn", "ngân hàng nhà nước", "bộ tài chính", "lãi suất",
    "tỷ giá", "tín dụng", "room",
    # Địa phương
    "hưng yên", "hồ chí minh", "hà nội",
    # Kinh tế
    "fed", "federal reserve", "cpi", "lạm phát", "nfp", "gdp",
    "vàng tăng", "vàng giảm", "dầu tăng", "dầu giảm",
    # Địa chính trị
    "chiến tranh", "xung đột", "trừng phạt", "thuế quan", "tariff",
    "dịch bệnh", "bùng phát", "thiên tai", "bão",
]

# ── Định nghĩa 14 nhóm với RSS + Jina ────────────────────────────────────────

GROUPS = [
    {
        "id": 1, "icon": "🏥",
        "name": "Dịch bệnh & Thiên tai Thế giới và Việt Nam",
        "sources": [
            {"name": "WHO Outbreaks",        "rss": "https://www.who.int/feeds/entity/emergencies/disease-outbreak-news/en/rss.xml"},
            {"name": "ReliefWeb Vietnam",    "rss": "https://reliefweb.int/country/vnm/rss.xml"},
            {"name": "VnExpress Sức khỏe",   "rss": "https://vnexpress.net/rss/suc-khoe.rss"},
        ],
    },
    {
        "id": 2, "icon": "🌍",
        "name": "Địa chính trị Thế giới",
        "sources": [
            {"name": "Reuters World",        "rss": "https://feeds.reuters.com/reuters/worldNews"},
            {"name": "Al Jazeera",           "rss": "https://www.aljazeera.com/xml/rss/all.xml"},
            {"name": "BBC World",            "rss": "http://feeds.bbci.co.uk/news/world/rss.xml"},
        ],
    },
    {
        "id": 3, "icon": "💹",
        "name": "Kinh tế & Tài chính Thế giới",
        "sources": [
            {"name": "Reuters Business",     "rss": "https://feeds.reuters.com/reuters/businessNews"},
            {"name": "CafeF Thế giới",       "rss": "https://cafef.vn/kinh-te-the-gioi.rss"},
            {"name": "VnExpress Kinh doanh", "rss": "https://vnexpress.net/rss/kinh-doanh.rss"},
        ],
    },
    {
        "id": 4, "icon": "📦",
        "name": "Thị trường Hàng hóa Thế giới và Việt Nam",
        "sources": [
            {"name": "CafeF Hàng hóa",       "rss": "https://cafef.vn/hang-hoa.rss"},
            {"name": "Trading Economics Commodities", "jina": "https://tradingeconomics.com/commodity"},
        ],
    },
    {
        "id": 5, "icon": "🥇",
        "name": "Vàng & Bạc Thế giới và Việt Nam",
        "sources": [
            {"name": "Kitco Gold News",      "rss": "https://www.kitco.com/rss/NewsRss.xml"},
            {"name": "CafeF Vàng",           "rss": "https://cafef.vn/vang.rss"},
            {"name": "Giá vàng SJC",         "jina": "https://sjc.com.vn/"},
        ],
    },
    {
        "id": 6, "icon": "🏦",
        "name": "Lãi suất Mỹ — Fed",
        "sources": [
            {"name": "Fed Press Releases",   "jina": "https://www.federalreserve.gov/newsevents/pressreleases.htm"},
            {"name": "Trading Economics Fed Rate", "jina": "https://tradingeconomics.com/united-states/interest-rate"},
        ],
    },
    {
        "id": 7, "icon": "👷",
        "name": "Lao động Mỹ — NFP & Thất nghiệp",
        "sources": [
            {"name": "BLS News Releases",    "jina": "https://www.bls.gov/bls/news-release/home.htm"},
            {"name": "Trading Economics US Jobs", "jina": "https://tradingeconomics.com/united-states/unemployment-rate"},
        ],
    },
    {
        "id": 8, "icon": "📈",
        "name": "Lạm phát & CPI Mỹ",
        "sources": [
            {"name": "BLS CPI",              "jina": "https://www.bls.gov/cpi/"},
            {"name": "Trading Economics CPI","jina": "https://tradingeconomics.com/united-states/inflation-cpi"},
        ],
    },
    {
        "id": 9, "icon": "🛢️",
        "name": "Giá dầu Thế giới và Việt Nam",
        "sources": [
            {"name": "EIA Petroleum",        "jina": "https://www.eia.gov/petroleum/"},
            {"name": "CafeF Dầu khí",        "rss": "https://cafef.vn/dau-khi.rss"},
            {"name": "Trading Economics Oil","jina": "https://tradingeconomics.com/commodity/crude-oil"},
        ],
    },
    {
        "id": 10, "icon": "📜",
        "name": "Văn bản pháp luật Việt Nam",
        "sources": [
            {"name": "Thư viện Pháp luật",   "rss": "https://thuvienphapluat.vn/rss/van-ban-moi.aspx"},
            {"name": "Cổng Chính phủ VB",    "jina": "https://vanban.chinhphu.vn/"},
        ],
    },
    {
        "id": 11, "icon": "🏛️",
        "name": "Chính sách Tài chính – Ngân hàng Việt Nam",
        "sources": [
            {"name": "NHNN",                 "jina": "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu"},
            {"name": "Bộ Tài chính",         "rss": "https://mof.gov.vn/webcenter/content/conn/WCRepository/path/Contribution%20Folders/MOF/RSS/rss_mof.xml"},
            {"name": "CafeF Ngân hàng",      "rss": "https://cafef.vn/ngan-hang.rss"},
        ],
    },
    {
        "id": 12, "icon": "💱",
        "name": "Tỷ giá VND/USD",
        "sources": [
            {"name": "Vietcombank Tỷ giá",   "jina": "https://vietcombank.com.vn/ExchangeRates"},
            {"name": "CafeF Tài chính",      "rss": "https://cafef.vn/tai-chinh-chung-khoan.rss"},
        ],
    },
    {
        "id": 13, "icon": "🎙️",
        "name": "Phát biểu & Ý chí lãnh đạo Việt Nam",
        "note": "Tô Lâm · Trần Thanh Mẫn · Lê Minh Hưng · Nguyễn Tấn Dũng · Phó Thủ tướng",
        "sources": [
            {"name": "Cổng Chính phủ",       "rss": "https://chinhphu.vn/tin-tuc-su-kien/rss"},
            {"name": "Quốc hội",             "rss": "https://quochoi.vn/rss/"},
            {"name": "Nhân dân Chính trị",   "rss": "https://nhandan.vn/rss/chinh-tri.rss"},
            {"name": "VnExpress Chính trị",  "rss": "https://vnexpress.net/rss/chinh-tri-xa-hoi.rss"},
        ],
    },
    {
        "id": 14, "icon": "🗺️",
        "name": "Trump & Chính sách Hưng Yên / HCM / Hà Nội",
        "note": "Donald Trump phát biểu + Nghị quyết phát triển 3 địa phương",
        "sources": [
            {"name": "White House",          "rss": "https://www.whitehouse.gov/feed/"},
            {"name": "Hưng Yên Portal",      "jina": "https://hungyen.gov.vn/"},
            {"name": "HCM Portal",           "jina": "https://www.hochiminhcity.gov.vn/"},
            {"name": "Hà Nội Portal",        "jina": "https://hanoi.gov.vn/"},
        ],
    },
]

# ── Hàm RSS ───────────────────────────────────────────────────────────────────

def fetch_rss(url: str) -> list[dict]:
    """Parse RSS feed → list of {title, link, summary, published}"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 VietnamIntelligence/2.0",
                 "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except Exception as e:
        return [{"error": str(e)[:120]}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        summary = (item.findtext("description") or
                   item.findtext("summary") or "").strip()
        pubdate = (item.findtext("pubDate") or
                   item.findtext("published") or "").strip()
        # Bỏ HTML tags trong summary
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()[:400]
        items.append({"title": title, "link": link,
                      "summary": summary, "published": pubdate})
        if len(items) >= MAX_ITEMS_PER_RSS:
            break

    # Atom feed (nếu không có item)
    if not items:
        for entry in root.findall(".//atom:entry", ns):
            title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link    = link_el.get("href", "") if link_el is not None else ""
            summary = (entry.findtext("atom:summary", namespaces=ns) or
                       entry.findtext("atom:content", namespaces=ns) or "").strip()
            pubdate = (entry.findtext("atom:published", namespaces=ns) or "").strip()
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()[:400]
            items.append({"title": title, "link": link,
                          "summary": summary, "published": pubdate})
            if len(items) >= MAX_ITEMS_PER_RSS:
                break

    return items


# ── Hàm Jina ──────────────────────────────────────────────────────────────────

def fetch_jina(url: str, max_chars: int = MAX_CHARS_JINA) -> str:
    """Dùng Jina Reader để lấy nội dung trang web dạng markdown."""
    req = urllib.request.Request(
        JINA_BASE + url,
        headers={"User-Agent": "Mozilla/5.0 VietnamIntelligence/2.0",
                 "Accept": "text/plain, text/markdown, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return clean_jina(raw)[:max_chars]
    except Exception as e:
        return f"[Lỗi Jina: {str(e)[:100]}]"


def clean_jina(text: str) -> str:
    """Lọc noise từ Jina output — giữ lại phần có giá trị."""
    lines = text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if len(s) < 20:
            continue
        if s.startswith("http") and " " not in s:
            continue
        if re.match(r"^[=\-_*#]{3,}$", s):
            continue
        if any(noise in s.lower() for noise in
               ["cookie", "javascript", "subscribe", "sign in", "log in",
                "advertisement", "quảng cáo", "đăng nhập", "đăng ký"]):
            continue
        out.append(s)
    return "\n".join(out[:100])


# ── Nhận diện tin quan trọng → fetch full ─────────────────────────────────────

def is_important(title: str, summary: str) -> bool:
    """Kiểm tra xem tin có đủ quan trọng để fetch full không."""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in IMPORTANT_KEYWORDS)


def fetch_full_article(url: str) -> str:
    """Fetch full nội dung bài báo quan trọng qua Jina."""
    if not url or not url.startswith("http"):
        return ""
    content = fetch_jina(url, max_chars=MAX_CHARS_FULL)
    if content.startswith("[Lỗi"):
        return ""
    return content


# ── Xử lý từng nguồn ─────────────────────────────────────────────────────────

def process_source(source: dict) -> dict:
    """Xử lý 1 nguồn: RSS hoặc Jina, kèm full article nếu quan trọng."""
    result = {"name": source["name"], "mode": "", "items": [],
              "jina_content": "", "ok": False, "important_count": 0}

    # ── RSS mode ──
    if "rss" in source:
        result["mode"] = "RSS"
        items = fetch_rss(source["rss"])

        if items and "error" not in items[0]:
            result["ok"] = True
            for item in items:
                # Fetch full nếu quan trọng
                full = ""
                if is_important(item.get("title",""), item.get("summary","")):
                    full = fetch_full_article(item.get("link",""))
                    if full:
                        result["important_count"] += 1
                        time.sleep(1)
                item["full"] = full
            result["items"] = items
        else:
            err = items[0].get("error","") if items else "Không có data"
            result["items"] = [{"error": err}]

    # ── Jina mode ──
    elif "jina" in source:
        result["mode"] = "Jina"
        content = fetch_jina(source["jina"])
        if not content.startswith("[Lỗi"):
            result["ok"] = True
        result["jina_content"] = content

    return result


def collect_group(group: dict) -> dict:
    """Thu thập toàn bộ nguồn trong một nhóm."""
    sources_data = []
    for source in group["sources"]:
        mode = "RSS" if "rss" in source else "Jina"
        print(f"  [{mode}] {source['name']}...")
        data = process_source(source)
        sources_data.append(data)
        time.sleep(1.2)
    return {"group": group, "sources": sources_data}


# ── Build Markdown ─────────────────────────────────────────────────────────────

def build_markdown(all_data: list, vn_now: datetime.datetime) -> str:
    time_str = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    lines = [
        "# 🇻🇳 Vietnam Intelligence Report",
        "",
        f"> **Thời gian:** {time_str}  ",
        "> **Chu kỳ:** Tự động mỗi 1 tiếng — GitHub Actions  ",
        "> **Format:** RSS headline + tóm tắt + full article nếu tin quan trọng",
        "> **Dùng cho:** AI Investment Team",
        "",
        "---", "",
    ]

    total_items = 0
    total_important = 0

    for gd in all_data:
        group = gd["group"]
        sources = gd["sources"]

        lines.append(f"## {group['icon']} Nhóm {group['id']}: {group['name']}")
        lines.append("")
        if "note" in group:
            lines.append(f"*{group['note']}*")
            lines.append("")

        ok_count = sum(1 for s in sources if s["ok"])
        lines.append(f"*{len(sources)} nguồn — {ok_count} thành công*")
        lines.append("")

        for src in sources:
            status = "✅" if src["ok"] else "❌"
            lines.append(f"### {status} {src['name']} `[{src['mode']}]`")
            lines.append("")

            # RSS items
            if src["mode"] == "RSS":
                if src["items"] and "error" not in src["items"][0]:
                    n_imp = src.get("important_count", 0)
                    total_items += len(src["items"])
                    total_important += n_imp
                    if n_imp:
                        lines.append(f"*{len(src['items'])} tin — {n_imp} tin quan trọng (đã đọc full)*")
                    else:
                        lines.append(f"*{len(src['items'])} tin mới nhất*")
                    lines.append("")

                    for i, item in enumerate(src["items"], 1):
                        title = item.get("title", "No title")
                        link  = item.get("link", "")
                        summ  = item.get("summary", "")
                        pub   = item.get("published", "")
                        full  = item.get("full", "")

                        # Headline
                        if link:
                            lines.append(f"**{i}. [{title}]({link})**")
                        else:
                            lines.append(f"**{i}. {title}**")

                        # Thời gian
                        if pub:
                            lines.append(f"*{pub[:50]}*")

                        # Tóm tắt 2-3 dòng
                        if summ:
                            lines.append(f"> {summ[:300]}")

                        # Full content nếu quan trọng
                        if full:
                            lines.append("")
                            lines.append("📌 **Nội dung đầy đủ (tin quan trọng):**")
                            lines.append("")
                            lines.append(full[:MAX_CHARS_FULL])

                        lines.append("")

                elif src["items"] and "error" in src["items"][0]:
                    lines.append(f"*Lỗi RSS: {src['items'][0]['error']}*")
                    lines.append("")
                else:
                    lines.append("*Không có tin mới*")
                    lines.append("")

            # Jina content
            elif src["mode"] == "Jina":
                content = src.get("jina_content", "")
                if content and not content.startswith("[Lỗi"):
                    lines.append(content)
                else:
                    lines.append(f"*{content}*")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Footer
    lines += [
        "## 📊 Tóm tắt",
        "",
        f"| Chỉ tiêu | Kết quả |",
        f"|---|---|",
        f"| Tổng tin RSS thu thập | {total_items} |",
        f"| Tin quan trọng (đọc full) | {total_important} |",
        f"| Thời gian | {time_str} |",
        "",
        "*Report tự động — github.com/TrangMinh0204/Macro-Data*",
    ]

    return "\n".join(lines)


# ── Index ──────────────────────────────────────────────────────────────────────

def update_index(index_file: Path, date_str: str,
                 hour_str: str, vn_now: datetime.datetime):
    time_str = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    entry = f"- [{time_str}](output/{date_str}/{hour_str}.md)"
    if index_file.exists():
        existing = index_file.read_text(encoding="utf-8")
        lines = existing.split("\n")
        insert_at = next(
            (i for i, l in enumerate(lines) if l.startswith("- [")), 5)
        lines.insert(insert_at, entry)
        index_file.write_text("\n".join(lines), encoding="utf-8")
    else:
        index_file.write_text(
            f"# Vietnam Intelligence — Index\n\n"
            f"Danh sách report tự động theo giờ.\n\n{entry}\n",
            encoding="utf-8"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    utc_now = datetime.datetime.utcnow()
    vn_now  = utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)
    date_str = vn_now.strftime("%Y-%m-%d")
    hour_str = vn_now.strftime("%H-%M")

    print(f"\n{'='*60}")
    print(f"Vietnam Intelligence Collector v2")
    print(f"Thời gian: {vn_now.strftime('%Y-%m-%d %H:%M ICT')}")
    print(f"Mode: RSS + Jina + Full article cho tin quan trọng")
    print(f"{'='*60}\n")

    output_dir  = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{hour_str}.md"

    all_data = []
    for group in GROUPS:
        print(f"\n[Nhóm {group['id']}] {group['icon']} {group['name']}")
        gd = collect_group(group)
        all_data.append(gd)

    print(f"\n{'='*60}")
    print(f"Tạo file: {output_file}")
    md = build_markdown(all_data, vn_now)
    output_file.write_text(md, encoding="utf-8")

    update_index(Path("output") / "INDEX.md", date_str, hour_str, vn_now)

    print(f"✅ Xong! Kích thước: {len(md):,} ký tự")


if __name__ == "__main__":
    main()
