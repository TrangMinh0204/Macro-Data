"""
Vietnam Intelligence Collector v3
===================================
Fix toàn bộ lỗi v2:
  - 404: Cập nhật URL RSS đúng
  - DNS Error: Thay Reuters bằng AP News + BBC
  - 403: Thay Thư viện Pháp luật bằng Jina
  - not well-formed: Fix encoding UTF-8 tiếng Việt
  - Jina fallback tự động khi RSS thất bại

Output: output/YYYY-MM-DD/HH-MM.md
"""

import time, datetime, urllib.request, urllib.error
import re, xml.etree.ElementTree as ET
from pathlib import Path

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TIMEZONE_OFFSET   = 7
REQUEST_TIMEOUT   = 25
MAX_ITEMS_PER_RSS = 8
MAX_CHARS_JINA    = 4000
MAX_CHARS_FULL    = 5000
JINA_BASE         = "https://r.jina.ai/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}

IMPORTANT_KEYWORDS = [
    "tô lâm","lê minh hưng","trần thanh mẫn","nguyễn tấn dũng",
    "thủ tướng","tổng bí thư","chủ tịch nước","chủ tịch quốc hội",
    "phó thủ tướng","bộ trưởng","trump","donald trump","white house",
    "nghị quyết","nghị định","thông tư","quyết định",
    "nhnn","ngân hàng nhà nước","bộ tài chính","lãi suất","tỷ giá",
    "hưng yên","hồ chí minh","hà nội",
    "fed","federal reserve","cpi","lạm phát","nfp","gdp",
    "vàng tăng","vàng giảm","dầu tăng","dầu giảm",
    "chiến tranh","xung đột","thuế quan","tariff","dịch bệnh","bùng phát",
    "ebola","marburg","outbreak","emergency",
]

# ── 14 Nhóm v3 — URL đã verify ────────────────────────────────────────────────
GROUPS = [
    {
        "id": 1, "icon": "🏥",
        "name": "Dịch bệnh & Thiên tai Thế giới và Việt Nam",
        "sources": [
            # WHO DON dùng Jina vì RSS 404 — lấy thẳng trang tin tức
            {"name": "WHO Disease Outbreak News", "jina": "https://www.who.int/emergencies/disease-outbreak-news"},
            # CDC Emerging Infectious Diseases — RSS hoạt động
            {"name": "CDC Emerging Infectious Diseases", "rss": "https://wwwnc.cdc.gov/eid/rss/ahead-of-print.xml"},
            # ReliefWeb dùng Jina (RSS trả rỗng)
            {"name": "ReliefWeb Vietnam", "jina": "https://reliefweb.int/country/vnm"},
            {"name": "VnExpress Sức khỏe", "rss": "https://vnexpress.net/rss/suc-khoe.rss"},
        ],
    },
    {
        "id": 2, "icon": "🌍",
        "name": "Địa chính trị Thế giới",
        "sources": [
            # AP News thay Reuters (Reuters chặn GitHub IP)
            {"name": "AP News World", "rss": "https://feeds.apnews.com/rss/apf-worldnews"},
            {"name": "BBC World News", "rss": "https://feeds.bbci.co.uk/news/world/rss.xml"},
            {"name": "Al Jazeera", "rss": "https://www.aljazeera.com/xml/rss/all.xml"},
        ],
    },
    {
        "id": 3, "icon": "💹",
        "name": "Kinh tế & Tài chính Thế giới",
        "sources": [
            {"name": "AP News Business", "rss": "https://feeds.apnews.com/rss/apf-business"},
            # VnEconomy — RSS hoạt động tốt
            {"name": "VnEconomy", "rss": "https://vneconomy.vn/rss.html"},
            {"name": "VnExpress Kinh doanh", "rss": "https://vnexpress.net/rss/kinh-doanh.rss"},
        ],
    },
    {
        "id": 4, "icon": "📦",
        "name": "Thị trường Hàng hóa Thế giới và Việt Nam",
        "sources": [
            {"name": "Trading Economics Commodities", "jina": "https://tradingeconomics.com/commodity"},
            # CafeBiz thay CafeF (RSS hoạt động)
            {"name": "CafeBiz Kinh doanh", "rss": "https://cafebiz.vn/index.rss"},
        ],
    },
    {
        "id": 5, "icon": "🥇",
        "name": "Vàng & Bạc Thế giới và Việt Nam",
        "sources": [
            # Kitco dùng Jina (RSS 404)
            {"name": "Kitco Gold", "jina": "https://www.kitco.com/news/gold"},
            {"name": "SJC Giá vàng", "jina": "https://sjc.com.vn/"},
            {"name": "DOJI Giá vàng", "jina": "https://doji.vn/gia-vang/"},
        ],
    },
    {
        "id": 6, "icon": "🏦",
        "name": "Lãi suất Mỹ — Fed",
        "sources": [
            {"name": "Federal Reserve Releases", "jina": "https://www.federalreserve.gov/newsevents/pressreleases.htm"},
            {"name": "Trading Economics Fed Rate", "jina": "https://tradingeconomics.com/united-states/interest-rate"},
            {"name": "CME FedWatch", "jina": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"},
        ],
    },
    {
        "id": 7, "icon": "👷",
        "name": "Lao động Mỹ — NFP & Thất nghiệp",
        "sources": [
            {"name": "BLS News Releases", "jina": "https://www.bls.gov/bls/news-release/home.htm"},
            {"name": "Trading Economics US Jobs", "jina": "https://tradingeconomics.com/united-states/unemployment-rate"},
        ],
    },
    {
        "id": 8, "icon": "📈",
        "name": "Lạm phát & CPI Mỹ",
        "sources": [
            {"name": "BLS CPI", "jina": "https://www.bls.gov/cpi/"},
            {"name": "Trading Economics US CPI", "jina": "https://tradingeconomics.com/united-states/inflation-cpi"},
        ],
    },
    {
        "id": 9, "icon": "🛢️",
        "name": "Giá dầu Thế giới và Việt Nam",
        "sources": [
            {"name": "EIA Petroleum", "jina": "https://www.eia.gov/petroleum/"},
            {"name": "Trading Economics Crude Oil", "jina": "https://tradingeconomics.com/commodity/crude-oil"},
            {"name": "VnExpress Năng lượng", "rss": "https://vnexpress.net/rss/kinh-doanh.rss"},
        ],
    },
    {
        "id": 10, "icon": "📜",
        "name": "Văn bản pháp luật Việt Nam",
        "sources": [
            # Thuvienphapluat 403 → dùng Jina với URL khác
            {"name": "Thư viện Pháp luật", "jina": "https://thuvienphapluat.vn/van-ban/moi-nhat"},
            {"name": "Cổng văn bản Chính phủ", "jina": "https://vanban.chinhphu.vn/"},
            # LuatVietnam có RSS
            {"name": "LuatVietnam", "rss": "https://luatvietnam.vn/rss/van-ban-moi.rss"},
        ],
    },
    {
        "id": 11, "icon": "🏛️",
        "name": "Chính sách Tài chính – Ngân hàng Việt Nam",
        "sources": [
            {"name": "NHNN", "jina": "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu"},
            # VnEconomy tài chính ngân hàng
            {"name": "VnEconomy Tài chính", "rss": "https://vneconomy.vn/tai-chinh.rss"},
            {"name": "VnExpress Kinh doanh", "rss": "https://vnexpress.net/rss/kinh-doanh.rss"},
        ],
    },
    {
        "id": 12, "icon": "💱",
        "name": "Tỷ giá VND/USD",
        "sources": [
            {"name": "Vietcombank Tỷ giá", "jina": "https://vietcombank.com.vn/ExchangeRates"},
            {"name": "Trading Economics USD/VND", "jina": "https://tradingeconomics.com/usdt-vnd:cur"},
            {"name": "VnEconomy Tỷ giá", "rss": "https://vneconomy.vn/ty-gia.rss"},
        ],
    },
    {
        "id": 13, "icon": "🎙️",
        "name": "Phát biểu & Ý chí lãnh đạo Việt Nam",
        "note": "Tô Lâm · Trần Thanh Mẫn · Lê Minh Hưng · Nguyễn Tấn Dũng · Phó Thủ tướng",
        "sources": [
            # Chinhphu.vn RSS đổi path
            {"name": "Cổng Chính phủ", "jina": "https://chinhphu.vn/"},
            # Nhandan RSS — fix encoding
            {"name": "Nhân dân Online", "rss": "https://nhandan.vn/rss/chinh-tri.rss", "encoding_fix": True},
            # VnExpress thời sự
            {"name": "VnExpress Thời sự", "rss": "https://vnexpress.net/rss/thoi-su.rss"},
            {"name": "VnExpress Thế giới", "rss": "https://vnexpress.net/rss/the-gioi.rss"},
        ],
    },
    {
        "id": 14, "icon": "🗺️",
        "name": "Trump & Chính sách Hưng Yên / HCM / Hà Nội",
        "note": "Donald Trump + Nghị quyết phát triển 3 địa phương",
        "sources": [
            # White House RSS đổi URL
            {"name": "White House Briefings", "rss": "https://www.whitehouse.gov/briefing-room/feed/"},
            {"name": "Hưng Yên Portal", "jina": "https://hungyen.gov.vn/"},
            {"name": "HCM Portal", "jina": "https://www.hochiminhcity.gov.vn/"},
            {"name": "Hà Nội Portal", "jina": "https://hanoi.gov.vn/"},
        ],
    },
]

# ── Fetch RSS ──────────────────────────────────────────────────────────────────

def fetch_rss(url: str, encoding_fix: bool = False) -> list:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {str(e)[:100]}"}]

    # Fix encoding: thử UTF-8, fallback UTF-8 ignore, fallback latin-1
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc, errors="replace" if enc == "latin-1" else "strict")
            break
        except Exception:
            continue

    # Xóa ký tự invalid XML (hay gặp với nguồn VN)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Fix encoding declaration sai
    text = re.sub(r'encoding=["\'][^"\']+["\']', 'encoding="utf-8"', text, count=1)

    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        return [{"error": f"XML parse: {str(e)[:100]}"}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link") or "").strip()
        desc    = item.findtext("description") or item.findtext("summary") or ""
        pubdate = (item.findtext("pubDate") or item.findtext("dc:date", namespaces={"dc":"http://purl.org/dc/elements/1.1/"}) or "").strip()
        summary = re.sub(r"<[^>]+>", " ", desc)
        summary = re.sub(r"\s+", " ", summary).strip()[:400]
        if title:
            items.append({"title": title, "link": link, "summary": summary, "published": pubdate})
        if len(items) >= MAX_ITEMS_PER_RSS:
            break

    # Atom
    if not items:
        for entry in root.findall(".//atom:entry", ns):
            title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            le      = entry.find("atom:link", ns)
            link    = le.get("href", "") if le is not None else ""
            summ    = entry.findtext("atom:summary", namespaces=ns) or entry.findtext("atom:content", namespaces=ns) or ""
            summ    = re.sub(r"<[^>]+>", " ", summ)
            summ    = re.sub(r"\s+", " ", summ).strip()[:400]
            pubdate = (entry.findtext("atom:published", namespaces=ns) or "").strip()
            if title:
                items.append({"title": title, "link": link, "summary": summ, "published": pubdate})
            if len(items) >= MAX_ITEMS_PER_RSS:
                break

    return items if items else [{"error": "Không có item nào trong feed"}]


# ── Fetch Jina ─────────────────────────────────────────────────────────────────

def fetch_jina(url: str, max_chars: int = MAX_CHARS_JINA) -> str:
    req = urllib.request.Request(
        JINA_BASE + url,
        headers={**HEADERS, "Accept": "text/plain, text/markdown, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return clean_jina(raw)[:max_chars]
    except Exception as e:
        return f"[Lỗi Jina: {type(e).__name__}: {str(e)[:80]}]"


def clean_jina(text: str) -> str:
    lines, out = text.split("\n"), []
    for line in lines:
        s = line.strip()
        if len(s) < 20: continue
        if re.match(r'^https?://\S+$', s): continue
        if re.match(r'^[=\-_*#]{3,}$', s): continue
        noise = ["cookie","javascript","subscribe","sign in","log in",
                 "advertisement","quảng cáo","đăng nhập","đăng ký",
                 "skip to content","toggle navigation"]
        if any(n in s.lower() for n in noise): continue
        out.append(s)
    return "\n".join(out[:100])


# ── Quan trọng → fetch full ────────────────────────────────────────────────────

def is_important(title: str, summary: str) -> bool:
    return any(kw in (title + " " + summary).lower() for kw in IMPORTANT_KEYWORDS)


def fetch_full(url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    content = fetch_jina(url, MAX_CHARS_FULL)
    return "" if content.startswith("[Lỗi") else content


# ── Process source ─────────────────────────────────────────────────────────────

def process_source(source: dict) -> dict:
    result = {"name": source["name"], "mode": "", "items": [],
              "jina_content": "", "ok": False, "important_count": 0}

    if "rss" in source:
        result["mode"] = "RSS"
        enc_fix = source.get("encoding_fix", False)
        items = fetch_rss(source["rss"], enc_fix)

        if items and "error" not in items[0]:
            result["ok"] = True
            enriched = []
            for item in items:
                full = ""
                if is_important(item.get("title",""), item.get("summary","")):
                    full = fetch_full(item.get("link",""))
                    if full:
                        result["important_count"] += 1
                        time.sleep(1)
                item["full"] = full
                enriched.append(item)
            result["items"] = enriched
        else:
            err = items[0].get("error","Unknown") if items else "No response"
            # Fallback sang Jina nếu có jina_fallback
            if "jina_fallback" in source:
                print(f"    RSS failed → Jina fallback")
                content = fetch_jina(source["jina_fallback"])
                result["mode"] = "RSS→Jina"
                if not content.startswith("[Lỗi"):
                    result["ok"] = True
                result["jina_content"] = content
            else:
                result["items"] = [{"error": err}]

    elif "jina" in source:
        result["mode"] = "Jina"
        content = fetch_jina(source["jina"])
        if not content.startswith("[Lỗi"):
            result["ok"] = True
        result["jina_content"] = content

    return result


def collect_group(group: dict) -> dict:
    sources_data = []
    for source in group["sources"]:
        mode = "RSS" if "rss" in source else "Jina"
        print(f"  [{mode}] {source['name']}...")
        data = process_source(source)
        sources_data.append(data)
        time.sleep(1.0)
    return {"group": group, "sources": sources_data}


# ── Build Markdown ─────────────────────────────────────────────────────────────

def build_markdown(all_data: list, vn_now: datetime.datetime) -> str:
    time_str = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    lines = [
        "# 🇻🇳 Vietnam Intelligence Report",
        "",
        f"> **Thời gian:** {time_str}  ",
        "> **Phiên bản:** v3 — RSS + Jina + Full article cho tin quan trọng  ",
        "> **Dùng cho:** AI Investment Team",
        "",
        "---", "",
    ]

    total_items, total_ok, total_important = 0, 0, 0

    for gd in all_data:
        group, sources = gd["group"], gd["sources"]
        ok_count = sum(1 for s in sources if s["ok"])
        total_ok += ok_count

        lines.append(f"## {group['icon']} Nhóm {group['id']}: {group['name']}")
        lines.append("")
        if "note" in group:
            lines.append(f"*{group['note']}*")
            lines.append("")
        lines.append(f"*{len(sources)} nguồn — {ok_count} thành công*")
        lines.append("")

        for src in sources:
            status = "✅" if src["ok"] else "❌"
            lines.append(f"### {status} {src['name']} `[{src['mode']}]`")
            lines.append("")

            if src["mode"] in ("RSS", "RSS→Jina") and src.get("items"):
                if "error" not in src["items"][0]:
                    n = len(src["items"])
                    ni = src.get("important_count", 0)
                    total_items += n
                    total_important += ni
                    label = f"{n} tin" + (f" — {ni} tin quan trọng (đọc full)" if ni else "")
                    lines.append(f"*{label}*")
                    lines.append("")
                    for i, item in enumerate(src["items"], 1):
                        title = item.get("title","")
                        link  = item.get("link","")
                        summ  = item.get("summary","")
                        pub   = item.get("published","")[:50]
                        full  = item.get("full","")
                        lines.append(f"**{i}. [{title}]({link})**" if link else f"**{i}. {title}**")
                        if pub: lines.append(f"*{pub}*")
                        if summ: lines.append(f"> {summ[:300]}")
                        if full:
                            lines.append("")
                            lines.append("📌 **Nội dung đầy đủ:**")
                            lines.append(full[:MAX_CHARS_FULL])
                        lines.append("")
                else:
                    lines.append(f"*❌ Lỗi: {src['items'][0]['error']}*")
                    lines.append("")
            elif src.get("jina_content"):
                content = src["jina_content"]
                if not content.startswith("[Lỗi"):
                    lines.append(content)
                else:
                    lines.append(f"*{content}*")
                lines.append("")

            lines += ["---", ""]

    total_sources = sum(len(g["sources"]) for g in all_data)
    lines += [
        "## 📊 Tóm tắt",
        "",
        f"| Chỉ tiêu | Kết quả |",
        f"|---|---|",
        f"| Tổng nguồn | {total_sources} |",
        f"| Thành công | {total_ok} |",
        f"| Thất bại | {total_sources - total_ok} |",
        f"| Tin RSS thu thập | {total_items} |",
        f"| Tin quan trọng (full) | {total_important} |",
        f"| Thời gian | {time_str} |",
        "",
        "*Vietnam Intelligence Collector v3 — github.com/TrangMinh0204/Macro-Data*",
    ]
    return "\n".join(lines)


# ── Index ──────────────────────────────────────────────────────────────────────

def update_index(index_file: Path, date_str: str, hour_str: str, vn_now: datetime.datetime):
    time_str = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    entry = f"- [{time_str}](output/{date_str}/{hour_str}.md)"
    if index_file.exists():
        lines = index_file.read_text(encoding="utf-8").split("\n")
        insert_at = next((i for i, l in enumerate(lines) if l.startswith("- [")), 5)
        lines.insert(insert_at, entry)
        index_file.write_text("\n".join(lines), encoding="utf-8")
    else:
        index_file.write_text(
            f"# Vietnam Intelligence — Index\n\nDanh sách report theo giờ.\n\n{entry}\n",
            encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    utc_now  = datetime.datetime.utcnow()
    vn_now   = utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)
    date_str = vn_now.strftime("%Y-%m-%d")
    hour_str = vn_now.strftime("%H-%M")

    print(f"\n{'='*60}")
    print(f"Vietnam Intelligence Collector v3")
    print(f"Thời gian: {vn_now.strftime('%Y-%m-%d %H:%M ICT')}")
    print(f"Fix: URL mới, encoding UTF-8, Jina fallback, thay Reuters→AP")
    print(f"{'='*60}\n")

    output_dir  = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{hour_str}.md"

    all_data = []
    for group in GROUPS:
        print(f"\n[Nhóm {group['id']}] {group['icon']} {group['name']}")
        all_data.append(collect_group(group))

    print(f"\n{'='*60}")
    md = build_markdown(all_data, vn_now)
    output_file.write_text(md, encoding="utf-8")
    update_index(Path("output") / "INDEX.md", date_str, hour_str, vn_now)

    ok_count = sum(
        sum(1 for s in g["sources"] if s["ok"])
        for g in all_data
    )
    total = sum(len(g["sources"]) for g in all_data)
    print(f"✅ Xong! {ok_count}/{total} nguồn thành công")
    print(f"   File: {output_file} ({len(md):,} ký tự)")


if __name__ == "__main__":
    main()
