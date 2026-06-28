"""
Vietnam Intelligence Collector v5
===================================
Chiến lược mới hoàn toàn:
  - Dữ liệu số (vàng, tỷ giá, dầu, Fed, CPI) → API JSON miễn phí
  - Tin tức → RSS từ nguồn có feed thực sự hoạt động
  - Bỏ hoàn toàn Jina cho trang VN (JS-rendered, không crawl được)
  - Jina chỉ dùng cho bài báo cụ thể (có URL thẳng đến bài)
"""

import time, datetime, gzip, json, zlib
import urllib.request, urllib.error
import re, xml.etree.ElementTree as ET
from pathlib import Path

TIMEZONE_OFFSET   = 7
REQUEST_TIMEOUT   = 20
MAX_ITEMS_RSS     = 8
MAX_CHARS_ARTICLE = 4000
JINA_BASE         = "https://r.jina.ai/"

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}

API_HEADERS = {
    "User-Agent": "VietnamIntelligence/5.0",
    "Accept": "application/json, text/json, */*",
    "Accept-Encoding": "gzip, deflate",
}

JINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 VietnamIntelligence/5.0",
    "Accept": "text/plain, text/markdown, */*",
    "Accept-Encoding": "identity",
}

IMPORTANT_KEYWORDS = [
    "tô lâm","lê minh hưng","trần thanh mẫn","nguyễn tấn dũng",
    "thủ tướng","tổng bí thư","chủ tịch nước","phó thủ tướng",
    "trump","white house","fed","federal reserve","interest rate",
    "nghị quyết","nghị định","thông tư","lãi suất","tỷ giá",
    "hưng yên","hồ chí minh","hà nội",
    "dịch bệnh","bùng phát","ebola","outbreak","emergency",
    "chiến tranh","xung đột","thuế quan","tariff",
    "vàng tăng","vàng giảm","dầu tăng","dầu giảm","gold","oil price",
]

# ══════════════════════════════════════════════════════════════════
# PHẦN 1: API JSON — Dữ liệu số thực
# ══════════════════════════════════════════════════════════════════

def fetch_json(url: str, headers: dict = None) -> dict | list | None:
    h = {**API_HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"_error": str(e)[:120]}


def get_gold_prices() -> dict:
    """Giá vàng thế giới — metals-api miễn phí (không cần key cho XAU/USD basic)"""
    result = {"xau_usd": None, "xag_usd": None, "source": "", "error": ""}

    # Thử ExchangeRate-API metals (free, không cần key)
    data = fetch_json("https://api.metals.live/v1/spot/gold,silver")
    if isinstance(data, list) and not isinstance(data, dict):
        for item in data:
            if isinstance(item, dict):
                if item.get("gold"): result["xau_usd"] = item["gold"]
                if item.get("silver"): result["xag_usd"] = item["silver"]
        if result["xau_usd"]:
            result["source"] = "metals.live"
            return result

    # Fallback: frankfurter.app (EUR base, tính ngược)
    data2 = fetch_json("https://api.frankfurter.app/latest?from=XAU&to=USD")
    if isinstance(data2, dict) and "rates" in data2:
        result["xau_usd"] = data2["rates"].get("USD")
        result["source"] = "frankfurter.app"
        return result

    result["error"] = "Không lấy được giá vàng"
    return result


def get_exchange_rates() -> dict:
    """Tỷ giá USD/VND và các cặp chính — ExchangeRate-API free"""
    result = {"usd_vnd": None, "eur_usd": None, "cny_usd": None,
              "dxy_approx": None, "source": "", "error": ""}

    # exchangerate-api free (không cần key, giới hạn 1500 req/tháng)
    data = fetch_json("https://open.er-api.com/v6/latest/USD")
    if isinstance(data, dict) and data.get("result") == "success":
        rates = data.get("rates", {})
        result["usd_vnd"]  = rates.get("VND")
        result["eur_usd"]  = round(1 / rates["EUR"], 4) if rates.get("EUR") else None
        result["cny_usd"]  = round(1 / rates["CNY"], 4) if rates.get("CNY") else None
        result["source"]   = "open.er-api.com"
        return result

    # Fallback: frankfurter
    data2 = fetch_json("https://api.frankfurter.app/latest?from=USD&to=VND,EUR,CNY")
    if isinstance(data2, dict) and "rates" in data2:
        r = data2["rates"]
        result["usd_vnd"] = r.get("VND")
        result["eur_usd"] = round(1/r["EUR"], 4) if r.get("EUR") else None
        result["cny_usd"] = round(1/r["CNY"], 4) if r.get("CNY") else None
        result["source"]  = "frankfurter.app"
        return result

    result["error"] = "Không lấy được tỷ giá"
    return result


def get_oil_price() -> dict:
    """Giá dầu WTI/Brent — dùng EIA API (free, không cần key cho public data)"""
    result = {"wti": None, "brent": None, "source": "", "error": ""}

    # EIA open data — series WTI daily
    url_wti = "https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=DEMO_KEY&frequency=daily&data[0]=value&facets[product][]=EPCWTI&sort[0][column]=period&sort[0][direction]=desc&length=1"
    data = fetch_json(url_wti)
    if isinstance(data, dict) and "response" in data:
        rows = data["response"].get("data", [])
        if rows:
            result["wti"] = rows[0].get("value")
            result["source"] = "EIA API"

    # Trading Economics public JSON (không cần key)
    # Fallback: dùng giá từ commodity RSS
    if not result["wti"]:
        result["error"] = "EIA DEMO_KEY giới hạn — cần API key hoặc dùng RSS"

    return result


def get_fed_rate() -> dict:
    """Fed Funds Rate — FRED API (St. Louis Fed, hoàn toàn miễn phí)"""
    result = {"rate": None, "date": None, "source": "", "error": ""}

    # FRED public API — series FEDFUNDS (monthly) không cần key cho read
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
    req = urllib.request.Request(url, headers=API_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8")
            lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
            # Lấy dòng cuối cùng (mới nhất)
            last = lines[-1].split(",")
            if len(last) == 2 and last[1] != ".":
                result["rate"] = float(last[1])
                result["date"] = last[0]
                result["source"] = "FRED St.Louis Fed"
                return result
    except Exception as e:
        result["error"] = str(e)[:80]

    # Fallback: Trading Economics
    result["error"] = "FRED không khả dụng"
    return result


def get_us_cpi() -> dict:
    """US CPI YoY — BLS public API (không cần key)"""
    result = {"cpi_yoy": None, "period": None, "source": "", "error": ""}

    # BLS Public Data API v1 (không cần key, giới hạn 25 req/ngày)
    url = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
    req = urllib.request.Request(url, headers=API_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
        series = data.get("Results", {}).get("series", [])
        if series:
            latest = series[0]["data"][0]
            result["cpi_yoy"] = latest.get("value")
            result["period"]  = f"{latest.get('periodName')} {latest.get('year')}"
            result["source"]  = "BLS.gov"
            return result
    except Exception as e:
        result["error"] = str(e)[:80]

    return result


def get_us_jobs() -> dict:
    """US Unemployment Rate — BLS public API"""
    result = {"unemployment": None, "period": None, "source": "", "error": ""}

    url = "https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000"
    req = urllib.request.Request(url, headers=API_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
        series = data.get("Results", {}).get("series", [])
        if series:
            latest = series[0]["data"][0]
            result["unemployment"] = latest.get("value")
            result["period"]       = f"{latest.get('periodName')} {latest.get('year')}"
            result["source"]       = "BLS.gov"
            return result
    except Exception as e:
        result["error"] = str(e)[:80]

    return result


# ══════════════════════════════════════════════════════════════════
# PHẦN 2: RSS — Tin tức thực sự hoạt động
# ══════════════════════════════════════════════════════════════════

RSS_SOURCES = [
    # ── Quốc tế ───────────────────────────────────────────────────
    {"group": 2, "name": "The Guardian World",         "url": "https://www.theguardian.com/world/rss"},
    {"group": 2, "name": "BBC World News",              "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"group": 2, "name": "RFI English",                 "url": "https://www.rfi.fr/en/rss"},
    {"group": 3, "name": "The Guardian Business",       "url": "https://www.theguardian.com/business/rss"},
    {"group": 3, "name": "BBC Business",                "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},

    # ── Việt Nam tin tức ──────────────────────────────────────────
    {"group": 3, "name": "VnExpress Kinh doanh",       "url": "https://vnexpress.net/rss/kinh-doanh.rss"},
    {"group": 3, "name": "VnExpress Thời sự",          "url": "https://vnexpress.net/rss/thoi-su.rss"},
    {"group":13, "name": "VnExpress Thế giới",         "url": "https://vnexpress.net/rss/the-gioi.rss"},
    {"group":13, "name": "VnExpress Góc nhìn",         "url": "https://vnexpress.net/rss/goc-nhin.rss"},

    # ── Chính phủ VN — Chỉ đạo điều hành (nhóm 10) ───────────────
    {"group":10, "name": "ChinhPhu Chỉ đạo điều hành", "jina": "https://chinhphu.vn/chi-dao-quyet-dinh-cua-chinh-phu-thu-tuong-chinh-phu"},
    {"group":10, "name": "ChinhPhu Thông cáo BC",       "jina": "https://baochinhphu.vn/thong-cao-bao-chi.htm"},
    {"group":10, "name": "ChinhPhu Hệ thống văn bản",   "jina": "https://chinhphu.vn/chinh-phu"},
    {"group":10, "name": "VanBan ChinhPhu",              "jina": "https://vanban.chinhphu.vn/"},
    {"group":10, "name": "BaoChinhPhu Chỉ đạo ĐH",     "jina": "https://baochinhphu.vn/chi-dao-dieu-hanh.htm"},

    # ── Lãnh đạo VN (nhóm 13) ────────────────────────────────────
    {"group":13, "name": "VTV Tổng Bí thư Tô Lâm",     "url": "https://vtv.vn/rss/dai-hoi-dang/tong-bi-thu-to-lam.rss"},
    {"group":13, "name": "VTV Chính trị",                "url": "https://vtv.vn/rss/chinh-tri.rss"},
    {"group":13, "name": "BaoChinhPhu Phát biểu Tô Lâm","jina": "https://baochinhphu.vn/chu-de/bai-viet-phat-bieu-cua-tong-bi-thu-to-lam-285.htm"},
    {"group":13, "name": "BaoChinhPhu Phát biểu TT",    "jina": "https://chinhphu.vn/cac-bai-phat-bieu-cua-thu-tuong"},
    {"group":13, "name": "BaoChinhPhu Họp báo CP",      "jina": "https://baochinhphu.vn/hop-bao-chinh-phu.htm"},

    # ── Dịch bệnh ─────────────────────────────────────────────────
    {"group": 1, "name": "ProMED Mail",                 "url": "https://promedmail.org/feed/"},
    {"group": 1, "name": "CDC Health Updates",          "url": "https://tools.cdc.gov/api/v2/resources/media/316422.rss"},

    # ── Trump / Địa chính trị Mỹ ─────────────────────────────────
    {"group":14, "name": "White House Briefings",       "url": "https://www.whitehouse.gov/briefing-room/feed/"},
]


def decompress(data: bytes) -> bytes:
    if data[:2] == b'\x1f\x8b':
        try: return gzip.decompress(data)
        except: pass
    try: return zlib.decompress(data)
    except: pass
    return data


def fetch_rss(url: str) -> list:
    req = urllib.request.Request(url, headers=RSS_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {str(e)[:80]}"}]

    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except:
            text = raw.decode("latin-1", errors="replace")

    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'encoding=["\'][^"\']+["\']', 'encoding="utf-8"', text, count=1)

    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        return [{"error": f"XML: {str(e)[:80]}"}]

    ns = {"atom": "http://www.w3.org/2005/Atom",
          "dc":   "http://purl.org/dc/elements/1.1/"}
    items = []

    for item in root.findall(".//item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        desc    = item.findtext("description") or ""
        pubdate = (item.findtext("pubDate") or
                   item.findtext("dc:date", namespaces=ns) or "").strip()
        summary = re.sub(r"<[^>]+>", " ", desc)
        summary = re.sub(r"\s+", " ", summary).strip()[:400]
        if title:
            items.append({"title": title, "link": link,
                          "summary": summary, "published": pubdate[:50]})
        if len(items) >= MAX_ITEMS_RSS: break

    if not items:
        for entry in root.findall(".//atom:entry", ns):
            title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            le      = entry.find("atom:link", ns)
            link    = le.get("href","") if le is not None else ""
            summ    = (entry.findtext("atom:summary", namespaces=ns) or
                       entry.findtext("atom:content", namespaces=ns) or "")
            summ    = re.sub(r"<[^>]+>","",summ)
            summ    = re.sub(r"\s+"," ",summ).strip()[:400]
            pubdate = (entry.findtext("atom:published", namespaces=ns) or "").strip()
            if title:
                items.append({"title":title,"link":link,
                              "summary":summ,"published":pubdate[:50]})
            if len(items) >= MAX_ITEMS_RSS: break

    return items or [{"error": "Feed rỗng"}]


def is_important(title: str, summary: str) -> bool:
    return any(kw in (title+" "+summary).lower() for kw in IMPORTANT_KEYWORDS)


def fetch_full_article(url: str) -> str:
    if not url or not url.startswith("http"): return ""
    req = urllib.request.Request(JINA_BASE + url, headers=JINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.split("\n")
                 if len(l.strip()) > 30 and not l.strip().startswith("http")]
        return "\n".join(lines[:80])[:MAX_CHARS_ARTICLE]
    except:
        return ""


def fetch_jina_content(url: str) -> str:
    """Fetch Jina và trả về text sạch."""
    req = urllib.request.Request(JINA_BASE + url, headers=JINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
        # Lọc noise
        lines, out = text.split("\n"), []
        noise = {"cookie","javascript","subscribe","sign in","log in",
                 "advertisement","đăng nhập","đăng ký","skip to content",
                 "toggle navigation","menu","weather","thời tiết"}
        for line in lines:
            s = line.strip()
            if len(s) < 20: continue
            if re.match(r'^https?://\S+$', s): continue
            if re.match(r'^[=\-_*#|]{3,}$', s): continue
            if any(n in s.lower() for n in noise): continue
            out.append(s)
        return "\n".join(out[:150])[:5000]
    except Exception as e:
        return f"[Lỗi Jina: {str(e)[:80]}]"


def collect_all_rss() -> dict:
    """Trả về dict {group_id: {sources: [...]}}"""
    by_group = {}
    for src in RSS_SOURCES:
        gid = src["group"]
        if gid not in by_group:
            by_group[gid] = {"sources": []}

        # ── Jina source ──────────────────────────────────────────
        if "jina" in src:
            print(f"  [Jina] {src['name']}...")
            content = fetch_jina_content(src["jina"])
            result = {
                "name": src["name"], "mode": "Jina",
                "ok": not content.startswith("[Lỗi"),
                "items": [], "jina_content": content, "important_count": 0
            }
            by_group[gid]["sources"].append(result)
            time.sleep(1.0)
            continue

        # ── RSS source ───────────────────────────────────────────
        print(f"  [RSS] {src['name']}...")
        items = fetch_rss(src["url"])
        result = {"name": src["name"], "mode": "RSS",
                  "ok": False, "items": [], "important_count": 0}
        if items and "error" not in items[0]:
            result["ok"] = True
            enriched = []
            for item in items:
                full = ""
                if is_important(item.get("title",""), item.get("summary","")):
                    full = fetch_full_article(item.get("link",""))
                    if full: result["important_count"] += 1; time.sleep(0.5)
                item["full"] = full
                enriched.append(item)
            result["items"] = enriched
        else:
            result["items"] = items
        by_group[gid]["sources"].append(result)
        time.sleep(0.8)
    return by_group


# ══════════════════════════════════════════════════════════════════
# PHẦN 3: Build Markdown
# ══════════════════════════════════════════════════════════════════

def fmt_num(v, decimals=2, suffix=""):
    if v is None: return "N/A"
    try: return f"{float(v):,.{decimals}f}{suffix}"
    except: return str(v)


def build_markdown(api_data: dict, rss_data: dict, vn_now: datetime.datetime) -> str:
    ts = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    lines = [
        "# 🇻🇳 Vietnam Intelligence Report",
        "",
        f"> **Thời gian:** {ts}  ",
        "> **Phiên bản:** v5 — API JSON (số liệu thực) + RSS (tin tức)  ",
        "> **Dùng cho:** AI Investment Team",
        "",
        "---", "",
    ]

    # ── BẢNG SỐ LIỆU TỔNG HỢP ──────────────────────────────────────
    gold  = api_data.get("gold", {})
    fx    = api_data.get("fx", {})
    fed   = api_data.get("fed", {})
    cpi   = api_data.get("cpi", {})
    jobs  = api_data.get("jobs", {})
    oil   = api_data.get("oil", {})

    lines += [
        "## 📊 Bảng Số liệu Thị trường (Real-time API)",
        "",
        "### 🥇 Vàng & Bạc",
        f"| | Giá | Nguồn |",
        f"|---|---|---|",
        f"| Vàng thế giới (XAU/USD) | **{fmt_num(gold.get('xau_usd'))} USD/oz** | {gold.get('source','N/A')} |",
        f"| Bạc thế giới (XAG/USD) | {fmt_num(gold.get('xag_usd'))} USD/oz | {gold.get('source','N/A')} |",
        "",
        "### 💱 Tỷ giá",
        f"| Cặp | Tỷ giá | Nguồn |",
        f"|---|---|---|",
        f"| USD/VND | **{fmt_num(fx.get('usd_vnd'),0)} VND** | {fx.get('source','N/A')} |",
        f"| EUR/USD | {fmt_num(fx.get('eur_usd'),4)} | {fx.get('source','N/A')} |",
        f"| CNY/USD | {fmt_num(fx.get('cny_usd'),4)} | {fx.get('source','N/A')} |",
        "",
        "### 🏦 Lãi suất & Vĩ mô Mỹ",
        f"| Chỉ số | Giá trị | Kỳ | Nguồn |",
        f"|---|---|---|---|",
        f"| Fed Funds Rate | **{fmt_num(fed.get('rate'),2,'%')}** | {fed.get('date','N/A')} | {fed.get('source','N/A')} |",
        f"| CPI YoY | **{fmt_num(cpi.get('cpi_yoy'),1,'%')}** | {cpi.get('period','N/A')} | {cpi.get('source','N/A')} |",
        f"| Tỷ lệ thất nghiệp | {fmt_num(jobs.get('unemployment'),1,'%')} | {jobs.get('period','N/A')} | {jobs.get('source','N/A')} |",
        "",
    ]

    if oil.get("wti"):
        lines += [
            "### 🛢️ Giá dầu",
            f"| | Giá | Nguồn |",
            f"|---|---|---|",
            f"| WTI Crude | **{fmt_num(oil.get('wti'))} USD/barrel** | {oil.get('source','N/A')} |",
            "",
        ]

    # Ghi chú lỗi API nếu có
    for key, label in [("gold","Vàng"),("fx","Tỷ giá"),("fed","Fed"),("cpi","CPI"),("jobs","Jobs")]:
        d = api_data.get(key,{})
        if d.get("error"):
            lines.append(f"> ⚠️ {label}: {d['error']}")
    lines += ["", "---", ""]

    # ── TIN TỨC RSS THEO NHÓM ───────────────────────────────────────
    GROUP_NAMES = {
        1:  ("🏥", "Dịch bệnh & Thiên tai"),
        2:  ("🌍", "Địa chính trị Thế giới"),
        3:  ("💹", "Kinh tế & Tài chính"),
        10: ("📜", "Chỉ đạo điều hành & Văn bản Chính phủ"),
        13: ("🎙️", "Phát biểu & Ý chí lãnh đạo VN"),
        14: ("🗺️", "Trump & Chính sách địa phương"),
    }

    total_items = total_imp = 0

    for gid in sorted(GROUP_NAMES.keys()):
        icon, gname = GROUP_NAMES[gid]
        gdata = rss_data.get(gid)
        lines.append(f"## {icon} {gname}")
        lines.append("")

        if not gdata:
            lines += ["*Không có nguồn RSS nào cho nhóm này*", "", "---", ""]
            continue

        ok = sum(1 for s in gdata["sources"] if s["ok"])
        lines.append(f"*{len(gdata['sources'])} nguồn — {ok} thành công*")
        lines.append("")

        for src in gdata["sources"]:
            status = "✅" if src["ok"] else "❌"
            mode = src.get("mode","RSS")
            lines.append(f"### {status} {src['name']} `[{mode}]`")
            lines.append("")

            # ── Jina content ──────────────────────────────────────
            if mode == "Jina":
                content = src.get("jina_content","")
                if content and not content.startswith("[Lỗi"):
                    lines.append(content)
                else:
                    lines.append(f"*{content}*")
                lines.append("")

            # ── RSS items ─────────────────────────────────────────
            else:
                items = src.get("items", [])
                if items and "error" not in items[0]:
                    n  = len(items)
                    ni = src.get("important_count", 0)
                    total_items += n; total_imp += ni
                    lines.append(f"*{n} tin*" + (f" — *{ni} tin quan trọng (đọc full)*" if ni else ""))
                    lines.append("")
                    for i, item in enumerate(items, 1):
                        t = item.get("title","")
                        l = item.get("link","")
                        s = item.get("summary","")
                        p = item.get("published","")
                        f = item.get("full","")
                        lines.append(f"**{i}. [{t}]({l})**" if l else f"**{i}. {t}**")
                        if p: lines.append(f"*{p}*")
                        if s: lines.append(f"> {s[:300]}")
                        if f: lines += ["", "📌 **Nội dung đầy đủ:**", f[:MAX_CHARS_ARTICLE], ""]
                        lines.append("")
                else:
                    err = items[0].get("error","") if items else ""
                    lines.append(f"*❌ {err}*")
                    lines.append("")

            lines += ["---", ""]

    # ── FOOTER ──────────────────────────────────────────────────────
    lines += [
        "## 📋 Tóm tắt",
        "",
        f"| Chỉ tiêu | Kết quả |",
        f"|---|---|",
        f"| API số liệu thực | Vàng · Tỷ giá · Fed · CPI · Jobs |",
        f"| Tổng tin RSS | {total_items} |",
        f"| Tin quan trọng (full) | {total_imp} |",
        f"| Thời gian | {ts} |",
        "",
        "*Vietnam Intelligence Collector v5 — github.com/TrangMinh0204/Macro-Data*",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# PHẦN 4: Index & Main
# ══════════════════════════════════════════════════════════════════

def update_index(index_file: Path, date_str: str, hour_str: str, vn_now: datetime.datetime):
    ts    = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    entry = f"- [{ts}](output/{date_str}/{hour_str}.md)"
    if index_file.exists():
        lines = index_file.read_text(encoding="utf-8").split("\n")
        ins   = next((i for i,l in enumerate(lines) if l.startswith("- [")), 5)
        lines.insert(ins, entry)
        index_file.write_text("\n".join(lines), encoding="utf-8")
    else:
        index_file.write_text(
            f"# Vietnam Intelligence — Index\n\nReport tự động theo giờ.\n\n{entry}\n",
            encoding="utf-8")


def main():
    utc_now  = datetime.datetime.utcnow()
    vn_now   = utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)
    date_str = vn_now.strftime("%Y-%m-%d")
    hour_str = vn_now.strftime("%H-%M")

    print(f"\n{'='*60}")
    print(f"Vietnam Intelligence Collector v5")
    print(f"Thời gian: {vn_now.strftime('%Y-%m-%d %H:%M ICT')}")
    print(f"Strategy: API JSON (số liệu thực) + RSS (tin tức)")
    print(f"{'='*60}\n")

    # Thu thập API
    print("[API] Lấy số liệu thị trường...")
    api_data = {}

    print("  [API] Giá vàng/bạc...")
    api_data["gold"] = get_gold_prices()
    print(f"        XAU/USD = {api_data['gold'].get('xau_usd')} ({api_data['gold'].get('source')})")

    print("  [API] Tỷ giá...")
    api_data["fx"] = get_exchange_rates()
    print(f"        USD/VND = {api_data['fx'].get('usd_vnd')} ({api_data['fx'].get('source')})")

    print("  [API] Fed Funds Rate...")
    api_data["fed"] = get_fed_rate()
    print(f"        Fed = {api_data['fed'].get('rate')}% ({api_data['fed'].get('date')})")

    print("  [API] US CPI...")
    api_data["cpi"] = get_us_cpi()
    print(f"        CPI = {api_data['cpi'].get('cpi_yoy')}% ({api_data['cpi'].get('period')})")

    print("  [API] US Jobs...")
    api_data["jobs"] = get_us_jobs()
    print(f"        Unemployment = {api_data['jobs'].get('unemployment')}%")

    print("  [API] Giá dầu...")
    api_data["oil"] = get_oil_price()

    # Thu thập RSS
    print("\n[RSS] Thu thập tin tức...")
    rss_data = collect_all_rss()

    # Tạo file
    output_dir  = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{hour_str}.md"

    md = build_markdown(api_data, rss_data, vn_now)
    output_file.write_text(md, encoding="utf-8")
    update_index(Path("output") / "INDEX.md", date_str, hour_str, vn_now)

    rss_ok = sum(
        sum(1 for s in g["sources"] if s["ok"])
        for g in rss_data.values()
    )
    rss_total = sum(len(g["sources"]) for g in rss_data.values())
    print(f"\n✅ Xong!")
    print(f"   API: gold={bool(api_data['gold'].get('xau_usd'))} fx={bool(api_data['fx'].get('usd_vnd'))} fed={bool(api_data['fed'].get('rate'))}")
    print(f"   RSS: {rss_ok}/{rss_total} nguồn thành công")
    print(f"   File: {output_file} ({len(md):,} ký tự)")


if __name__ == "__main__":
    main()
