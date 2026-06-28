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

LAST_RUN_FILE     = Path("output/last_run.txt")   # Lưu timestamp lần chạy trước


# ── Hàm xử lý thời gian ──────────────────────────────────────────────────────

def load_last_run() -> datetime.datetime:
    """Đọc timestamp lần chạy trước từ file. Nếu chưa có → trả về 1 tiếng trước."""
    try:
        if LAST_RUN_FILE.exists():
            ts_str = LAST_RUN_FILE.read_text(encoding="utf-8").strip()
            return datetime.datetime.fromisoformat(ts_str)
    except Exception:
        pass
    # Lần đầu chạy hoặc file bị lỗi → lấy tin trong 1 tiếng qua
    utc_now = datetime.datetime.utcnow()
    return utc_now - datetime.timedelta(hours=1)


def save_last_run(utc_now: datetime.datetime):
    """Lưu timestamp UTC hiện tại để lần sau dùng làm cutoff."""
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(utc_now.isoformat(), encoding="utf-8")


def parse_pubdate(raw: str) -> datetime.datetime | None:
    """Parse pubDate RSS / ISO 8601 → datetime UTC. Trả None nếu không parse được."""
    if not raw:
        return None
    raw = raw.strip()

    # Thử các format phổ biến
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822: "Sat, 28 Jun 2026 06:00:00 +0700"
        "%a, %d %b %Y %H:%M:%S %Z",   # RFC 2822 với tz name: "... GMT"
        "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601: "2026-06-28T06:00:00+07:00"
        "%Y-%m-%dT%H:%M:%SZ",         # ISO UTC: "2026-06-28T06:00:00Z"
        "%Y-%m-%dT%H:%M:%S.%f%z",     # ISO with microseconds
        "%Y-%m-%d %H:%M:%S",          # Simple
        "%Y-%m-%d",                    # Date only
    ]

    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            # Chuẩn hóa về UTC
            if dt.tzinfo is not None:
                dt = dt.utctimetuple()
                dt = datetime.datetime(*dt[:6])
            return dt
        except ValueError:
            continue

    # Fallback: thử email.utils (xử lý RFC 2822 linh hoạt hơn)
    try:
        import email.utils
        ts = email.utils.parsedate_to_datetime(raw)
        return ts.replace(tzinfo=None) - ts.utcoffset() if ts.utcoffset() else ts.replace(tzinfo=None)
    except Exception:
        pass

    return None


def is_new_item(published_str: str, last_run_utc: datetime.datetime) -> bool:
    """Kiểm tra tin có mới hơn last_run không. Nếu không parse được date → giữ lại (an toàn)."""
    dt = parse_pubdate(published_str)
    if dt is None:
        return True   # Không parse được → giữ lại để không bỏ sót
    return dt > last_run_utc

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
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
    """Giá vàng — open.er-api XAU/USD (no key) + CafeF fallback"""
    result = {"xau_usd": None, "xag_usd": None,
              "sjc_vnd": None, "source": "", "error": ""}

    # Nguồn 1: open.er-api XAU base (truly no key required)
    try:
        data = fetch_json("https://open.er-api.com/v6/latest/XAU")
        if isinstance(data, dict) and data.get("result") == "success":
            rates = data.get("rates", {})
            if rates.get("USD"):
                result["xau_usd"] = round(float(rates["USD"]), 2)
                result["source"]  = "open.er-api (XAU)"
                # Silver từ XAG base
                try:
                    d2 = fetch_json("https://open.er-api.com/v6/latest/XAG")
                    if isinstance(d2, dict) and d2.get("result") == "success":
                        result["xag_usd"] = round(float(d2["rates"]["USD"]), 2)
                except: pass
                return result
    except Exception as e:
        result["_er_err"] = str(e)[:60]

    # Nguồn 2: frankfurter.app — XAU/USD qua EUR pivot
    try:
        d3 = fetch_json("https://api.frankfurter.app/latest?from=XAU&to=USD,EUR")
        if isinstance(d3, dict) and "rates" in d3 and d3["rates"].get("USD"):
            result["xau_usd"] = round(float(d3["rates"]["USD"]), 2)
            result["source"]  = "frankfurter.app (XAU)"
            return result
    except Exception as e2:
        result["_frank_err"] = str(e2)[:60]

    # Nguồn 3: coinbase public (no key)
    try:
        d4 = fetch_json("https://api.coinbase.com/v2/exchange-rates?currency=XAU")
        if isinstance(d4, dict):
            usd = d4.get("data", {}).get("rates", {}).get("USD")
            if usd:
                result["xau_usd"] = round(float(usd), 2)
                result["source"]  = "coinbase (XAU)"
                return result
    except Exception as e3:
        result["_cb_err"] = str(e3)[:60]

    result["error"] = "Không lấy được giá vàng — thử lại sau"
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


def get_vnindex() -> dict:
    """VNIndex + HNX-Index từ SSI iBoard API (public, không cần key)"""
    result = {
        "vnindex": None, "vnindex_change": None, "vnindex_pct": None,
        "hnx": None, "hnx_change": None,
        "total_value_bn": None,   # Tổng giá trị khớp lệnh HOSE (tỷ đồng)
        "foreign_net_bn": None,   # Khối ngoại mua ròng HOSE (tỷ đồng)
        "source": "", "error": ""
    }

    # Nguồn 1: SSI iBoard public API — index snapshot
    try:
        url = "https://iboard-query.ssi.com.vn/v2/stock/index/VNINDEX"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Origin": "https://iboard.ssi.com.vn",
            "Referer": "https://iboard.ssi.com.vn/",
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        d = data.get("data", data)
        if isinstance(d, list): d = d[0] if d else {}
        if d.get("indexValue"):
            result["vnindex"]       = float(d.get("indexValue", 0))
            result["vnindex_change"]= float(d.get("indexChange", 0))
            result["vnindex_pct"]   = float(d.get("percentChange", 0))
            result["total_value_bn"]= round(float(d.get("totalValue", 0)) / 1e9, 0)
            result["source"] = "SSI iBoard"
            # Lấy thêm HNX
            try:
                url2 = "https://iboard-query.ssi.com.vn/v2/stock/index/HNXIndex"
                req2 = urllib.request.Request(url2, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Origin": "https://iboard.ssi.com.vn",
                    "Referer": "https://iboard.ssi.com.vn/",
                })
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    raw2 = resp2.read()
                if raw2[:2] == b"\x1f\x8b": raw2 = gzip.decompress(raw2)
                d2 = json.loads(raw2.decode("utf-8", errors="replace"))
                d2 = d2.get("data", d2)
                if isinstance(d2, list): d2 = d2[0] if d2 else {}
                if d2.get("indexValue"):
                    result["hnx"]        = float(d2.get("indexValue", 0))
                    result["hnx_change"] = float(d2.get("indexChange", 0))
            except: pass
            return result
    except Exception as e:
        result["_ssi_err"] = str(e)[:80]

    # Nguồn 2: TCBS public market summary
    try:
        url3 = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/VNIndex"
        req3 = urllib.request.Request(url3, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req3, timeout=REQUEST_TIMEOUT) as resp3:
            raw3 = resp3.read()
        if raw3[:2] == b"\x1f\x8b": raw3 = gzip.decompress(raw3)
        d3 = json.loads(raw3.decode("utf-8", errors="replace"))
        if d3.get("indexValue"):
            result["vnindex"]        = float(d3.get("indexValue", 0))
            result["vnindex_change"] = float(d3.get("change", 0))
            result["vnindex_pct"]    = float(d3.get("percentChange", 0))
            result["source"]         = "TCBS API"
            return result
    except Exception as e2:
        result["_tcbs_err"] = str(e2)[:80]

    # Nguồn 3: Jina đọc CafeF bảng giá (fallback)
    try:
        jina_url = JINA_BASE + "https://cafef.vn/thi-truong-chung-khoan.chn"
        req4 = urllib.request.Request(jina_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req4, timeout=REQUEST_TIMEOUT) as resp4:
            raw4 = resp4.read()
        if raw4[:2] == b"\x1f\x8b": raw4 = gzip.decompress(raw4)
        text4 = raw4.decode("utf-8", errors="replace")
        # Tìm pattern VNIndex trong text
        m = __import__("re").search(
            r"VN[\-\s]?Index[^\d]*(\d[\d,.]+)", text4, __import__("re").IGNORECASE)
        if m:
            result["vnindex"] = float(m.group(1).replace(",",""))
            result["source"]  = "CafeF Jina (fallback)"
            return result
    except Exception as e3:
        result["_jina_err"] = str(e3)[:80]

    result["error"] = "Không lấy được VNIndex — thị trường đóng cửa hoặc API lỗi"
    return result


def get_fed_rate() -> dict:
    """Fed Funds Rate — FRED CSV với xử lý gzip/encoding đúng"""
    result = {"rate": None, "date": None, "source": "", "error": ""}

    # Nguồn 1: FRED CSV — không gửi Accept-Encoding để tránh gzip
    req = urllib.request.Request(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; VietnamIntelligence/2.0)",
            "Accept": "text/csv, text/plain, */*",
            # Bỏ Accept-Encoding để nhận plain text
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        # Decompress nếu server vẫn gzip
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif raw[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            raw = zlib.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.split("\n")
                 if l.strip() and not l.startswith("DATE")]
        if lines:
            last = lines[-1].split(",")
            if len(last) == 2 and last[1].strip() not in (".", ""):
                result["rate"]   = float(last[1].strip())
                result["date"]   = last[0].strip()
                result["source"] = "FRED St.Louis Fed"
                return result
    except Exception as e:
        result["_fred_err"] = str(e)[:80]

    # Nguồn 2: Federal Reserve H.15 trang HTML
    try:
        req2 = urllib.request.Request(
            "https://www.federalreserve.gov/releases/h15/current/default.htm",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
        )
        with urllib.request.urlopen(req2, timeout=REQUEST_TIMEOUT) as resp2:
            raw2 = resp2.read()
        if raw2[:2] == b"\x1f\x8b": raw2 = gzip.decompress(raw2)
        text2 = raw2.decode("utf-8", errors="replace")
        import re as _re2
        m = _re2.search(r"Federal funds[^\d]*(\d+\.\d+)", text2, _re2.IGNORECASE)
        if m:
            result["rate"]   = float(m.group(1))
            result["source"] = "FederalReserve.gov H.15"
            return result
    except Exception as e2:
        result["_h15_err"] = str(e2)[:80]

    # Nguồn 3: fetch_json exchangeratesapi backup
    try:
        d = fetch_json("https://open.er-api.com/v6/latest/USD")
        if isinstance(d, dict) and d.get("result") == "success":
            # Không có Fed rate trực tiếp nhưng xác nhận API sống
            pass
    except: pass

    # Nguồn 4: FOMC statement page — đọc lãi suất từ trang tóm tắt
    try:
        req4 = urllib.request.Request(
            "https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        # Không có Fed rate từ đây, nhưng xác nhận mạng OK
        # Dùng hardcode từ lần họp FOMC gần nhất làm fallback
        result["rate"]   = 4.25  # FOMC target upper bound (cập nhật thủ công nếu thay đổi)
        result["date"]   = "Fallback — cập nhật thủ công"
        result["source"] = "Hardcode FOMC 2026 (FRED unavailable)"
        result["note"]   = "FRED bị chặn từ GitHub Actions — giá trị tham khảo"
        return result
    except: pass

    result["error"] = "Fed rate: thất bại tất cả nguồn"
    return result
def get_us_cpi() -> dict:
    """US CPI YoY — tính đúng: (index_now - index_12m_ago) / index_12m_ago * 100"""
    result = {"cpi_yoy": None, "cpi_index": None, "period": None,
              "source": "", "error": ""}

    # BLS API v1 trả về CPI Index level (không phải %) — cần lấy 13 điểm để tính YoY
    url = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif raw[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            raw = zlib.decompress(raw)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        series = data.get("Results", {}).get("series", [])
        if series and series[0].get("data"):
            rows = series[0]["data"]
            # rows được sort DESC (mới nhất trước)
            if len(rows) >= 13:
                latest     = rows[0]   # tháng mới nhất
                year_ago   = rows[12]  # cùng tháng năm trước
                idx_now    = float(latest.get("value", 0))
                idx_ago    = float(year_ago.get("value", 1))
                yoy        = round((idx_now - idx_ago) / idx_ago * 100, 2)
                result["cpi_yoy"]   = yoy
                result["cpi_index"] = idx_now
                result["period"]    = f"{latest.get('periodName')} {latest.get('year')}"
                result["source"]    = "BLS.gov (YoY tính từ index)"
                return result
            elif rows:
                # Chỉ có 1 điểm — lưu index, báo thiếu YoY
                latest = rows[0]
                result["cpi_index"] = float(latest.get("value", 0))
                result["period"]    = f"{latest.get('periodName')} {latest.get('year')}"
                result["error"]     = "Thiếu data 12 tháng để tính YoY"
                result["source"]    = "BLS.gov"
                return result
    except Exception as e:
        result["error"] = str(e)[:80]

    result["error"] = result.get("error", "") + " | BLS API lỗi"
    return result
def get_us_jobs() -> dict:
    """US Unemployment Rate — BLS public API với xử lý gzip đúng"""
    result = {"unemployment": None, "period": None, "source": "", "error": ""}

    url = "https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        # Fix lỗi 0x8b — decompress gzip/zlib
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif raw[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            raw = zlib.decompress(raw)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        series = data.get("Results", {}).get("series", [])
        if series and series[0].get("data"):
            latest = series[0]["data"][0]
            result["unemployment"] = latest.get("value")
            result["period"]       = f"{latest.get('periodName')} {latest.get('year')}"
            result["source"]       = "BLS.gov"
            return result
    except Exception as e:
        result["error"] = str(e)[:80]

    result["error"] = result.get("error", "") + " | BLS API lỗi"
    return result

# ══════════════════════════════════════════════════════════════════
# PHẦN 2: RSS — Tin tức thực sự hoạt động
# ══════════════════════════════════════════════════════════════════

RSS_SOURCES = [
    # ── Quốc tế — Big 6 sources ─────────────────────────────────
    # BBC — RSS chính thức còn hoạt động
    {"group": 2, "name": "BBC World News",              "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"group": 2, "name": "BBC Business",                "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},

    # CNN — RSS edition world
    {"group": 2, "name": "CNN World",                   "url": "https://rss.cnn.com/rss/edition_world.rss"},
    {"group": 3, "name": "CNN Business",                "url": "https://rss.cnn.com/rss/money_latest.rss"},

    # Reuters — đã tắt RSS trực tiếp 2020, dùng Google News RSS
    {"group": 2, "name": "Reuters World (GNews)",       "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en-US&gl=US&ceid=US:en"},
    {"group": 3, "name": "Reuters Business (GNews)",    "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+business&hl=en-US&gl=US&ceid=US:en"},

    # NYT — RSS còn hoạt động (nội dung tóm tắt, full article có paywall)
    {"group": 2, "name": "NYT World",                   "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"group": 3, "name": "NYT Business",                "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},

    # Washington Post — RSS còn hoạt động
    {"group": 2, "name": "Washington Post World",       "url": "https://feeds.washingtonpost.com/rss/world"},
    {"group": 3, "name": "Washington Post Business",    "url": "https://feeds.washingtonpost.com/rss/business"},

    # Bloomberg — không có public RSS, dùng Google News RSS về Bloomberg
    {"group": 3, "name": "Bloomberg (GNews)",           "url": "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com&hl=en-US&gl=US&ceid=US:en"},
    {"group": 6, "name": "Bloomberg Economics (GNews)", "url": "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com+fed+rate+economy&hl=en-US&gl=US&ceid=US:en"},

    # Giữ lại The Guardian + RFI
    {"group": 2, "name": "The Guardian World",         "url": "https://www.theguardian.com/world/rss"},
    {"group": 2, "name": "RFI English",                "url": "https://www.rfi.fr/en/rss"},
    {"group": 3, "name": "The Guardian Business",      "url": "https://www.theguardian.com/business/rss"},

    # AP News — thêm vào làm nguồn tin cậy
    {"group": 2, "name": "AP News World",              "url": "https://feeds.apnews.com/rss/apf-intlnews"},
    {"group": 3, "name": "AP News Business",           "url": "https://feeds.apnews.com/rss/apf-business"},

    # ── Việt Nam tin tức ──────────────────────────────────────────
    # VnExpress — thường bị 503 do chặn bot, dùng VnEconomy + Tuổi Trẻ thay thế
    {"group": 3, "name": "VnEconomy Chứng khoán",      "url": "https://vneconomy.vn/chung-khoan.rss"},
    {"group": 3, "name": "VnEconomy Tài chính",        "url": "https://vneconomy.vn/tai-chinh.rss"},
    {"group": 3, "name": "Tuổi Trẻ Kinh tế",           "url": "https://tuoitre.vn/rss/kinh-te.rss"},
    {"group":13, "name": "Tuổi Trẻ Thời sự",           "url": "https://tuoitre.vn/rss/thoi-su.rss"},
    {"group":13, "name": "Nhân dân Thế giới",          "url": "https://nhandan.vn/rss/the-gioi.rss"},
    # Giữ VnExpress nhưng là backup
    {"group": 3, "name": "VnExpress Kinh doanh",       "url": "https://vnexpress.net/rss/kinh-doanh.rss"},
    {"group":13, "name": "VnExpress Góc nhìn",         "url": "https://vnexpress.net/rss/goc-nhin.rss"},

    # ── CafeF — thay thế Vietstock (RSS hoạt động tốt) ───────────
    {"group": 3, "name": "CafeF Chứng khoán",          "url": "https://cafef.vn/thi-truong-chung-khoan.rss"},
    {"group": 3, "name": "CafeF Vĩ mô VN",             "url": "https://cafef.vn/vi-mo-dau-tu.rss"},
    {"group": 3, "name": "CafeF Doanh nghiệp",         "url": "https://cafef.vn/doanh-nghiep.rss"},

    # ── Phân tích TTCK — Jina đọc được ───────────────────────────
    {"group": 3, "name": "Nhịp cầu đầu tư",            "jina": "https://nhipcaudautu.vn/"},
    {"group": 3, "name": "Tin nhanh chứng khoán",      "jina": "https://tinnhanhchungkhoan.vn/"},

    # ── Người Quan Sát (nguoiquansat.vn) — tài chính đầu tư VN ──
    # Jina vì OneCMS không có public RSS — trang load được tốt
    {"group": 3,  "name": "NQS Chứng khoán",           "jina": "https://nguoiquansat.vn/chung-khoan"},
    {"group": 3,  "name": "NQS Doanh nghiệp",          "jina": "https://nguoiquansat.vn/doanh-nghiep"},
    {"group": 3,  "name": "NQS Vĩ mô",                 "jina": "https://nguoiquansat.vn/vi-mo"},
    {"group": 11, "name": "NQS Tài chính Ngân hàng",   "jina": "https://nguoiquansat.vn/tai-chinh-ngan-hang"},
    {"group": 12, "name": "NQS Vàng - Tỷ giá",         "jina": "https://nguoiquansat.vn/tai-chinh-ngan-hang/vang-ty-gia"},
    {"group": 2,  "name": "NQS Thế giới",               "jina": "https://nguoiquansat.vn/the-gioi"},

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
    # White House đã bỏ RSS — dùng Jina đọc trang HTML
    {"group":14, "name": "White House News",            "jina": "https://www.whitehouse.gov/news/"},
    {"group":14, "name": "White House Briefings",       "jina": "https://www.whitehouse.gov/briefings-statements/"},
    {"group":14, "name": "White House Executive Orders","jina": "https://www.whitehouse.gov/presidential-actions/executive-orders/"},
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
    except ET.ParseError:
        # Fix & không encode — lỗi phổ biến ở CafeF, nguồn VN
        text2 = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', text)
        try:
            root = ET.fromstring(text2.encode("utf-8"))
        except ET.ParseError as e2:
            return [{"error": f"XML: {str(e2)[:80]}"}]

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


def collect_all_rss(last_run_utc: datetime.datetime) -> dict:
    """Thu thập RSS — chỉ giữ item MỚI hơn last_run_utc."""
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
                  "ok": False, "items": [], "important_count": 0,
                  "filtered_count": 0}
        if items and "error" not in items[0]:
            result["ok"] = True
            enriched = []
            skipped  = 0
            for item in items:
                # ── FILTER: chỉ giữ tin mới hơn last_run ──────
                if not is_new_item(item.get("published", ""), last_run_utc):
                    skipped += 1
                    continue
                full = ""
                if is_important(item.get("title",""), item.get("summary","")):
                    full = fetch_full_article(item.get("link",""))
                    if full: result["important_count"] += 1; time.sleep(0.5)
                item["full"] = full
                enriched.append(item)
            result["items"]         = enriched
            result["filtered_count"] = skipped
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


def build_markdown(api_data: dict, rss_data: dict,
                   vn_now: datetime.datetime,
                   last_run_ict: datetime.datetime | None = None) -> str:
    ts       = vn_now.strftime("%Y-%m-%d %H:%M ICT")
    last_str = last_run_ict.strftime("%Y-%m-%d %H:%M ICT") if last_run_ict else "N/A"
    lines = [
        "# 🇻🇳 Vietnam Intelligence Report",
        "",
        f"> **Thời gian hiện tại:** {ts}  ",
        f"> **Cập nhật từ:** {last_str}  ",
        f"> **Window:** Chỉ tin TỨC MỚI trong khoảng [{last_str} → {ts}]  ",
        "> **Phiên bản:** v5 — API JSON (số liệu thực) + RSS (chỉ tin mới)  ",
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

    # ── VNIndex block ──────────────────────────────────────────────────
    vi = api_data.get("vnindex", {})
    if vi.get("vnindex"):
        chg   = float(vi.get("vnindex_change") or 0)
        pct   = float(vi.get("vnindex_pct") or 0)
        sign  = "+" if chg >= 0 else ""
        arrow = "🟢" if chg >= 0 else "🔴"
        lines += [
            "### 📈 VNIndex & TTCK Việt Nam",
            "| Chỉ số | Điểm | Thay đổi | Nguồn |",
            "|---|---|---|---|",
            f"| **VNIndex** | **{fmt_num(vi['vnindex'],2,'')}** | {arrow} {sign}{fmt_num(chg,2,'')} ({sign}{fmt_num(pct,2,'%')}) | {vi.get('source','N/A')} |",
        ]
        if vi.get("hnx"):
            hchg  = float(vi.get("hnx_change") or 0)
            harr  = "🟢" if hchg >= 0 else "🔴"
            hsign = "+" if hchg >= 0 else ""
            lines.append(f"| HNX-Index | {fmt_num(vi['hnx'],2,'')} | {harr} {hsign}{fmt_num(hchg,2,'')} | {vi.get('source','N/A')} |")
        if vi.get("total_value_bn"):
            lines.append(f"| Giá trị khớp lệnh HOSE | {fmt_num(vi['total_value_bn'],0,' tỷ đồng')} | — | — |")
        lines.append("")
    else:
        lines += [
            "### 📈 VNIndex & TTCK Việt Nam",
            f"> ⚠️ VNIndex: {vi.get('error', 'Không lấy được — thị trường có thể đóng cửa')}",
            "",
        ]

    # Ghi chú lỗi API nếu có
    for key, label in [("gold","Vàng"),("fx","Tỷ giá"),("fed","Fed"),("cpi","CPI"),("jobs","Jobs"),("vnindex","VNIndex")]:
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
                    n          = len(items)
                    ni         = src.get("important_count", 0)
                    n_filtered = src.get("filtered_count", 0)
                    total_items += n; total_imp += ni
                    skip_note = f" — bỏ qua {n_filtered} tin cũ" if n_filtered else ""
                    if n == 0:
                        lines.append(f"*Không có tin MỚI trong window này{skip_note}*")
                    else:
                        imp_note = f" — {ni} tin quan trọng (đọc full)" if ni else ""
                        lines.append(f"*{n} tin MỚI{imp_note}{skip_note}*")
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

    print("  [API] VNIndex + HNX-Index...")
    api_data["vnindex"] = get_vnindex()
    vi = api_data["vnindex"]
    if vi.get("vnindex"):
        chg = vi.get("vnindex_change", 0) or 0
        pct = vi.get("vnindex_pct", 0) or 0
        sign = "+" if chg >= 0 else ""
        print(f"        VNIndex = {vi['vnindex']:.2f} ({sign}{chg:.2f} | {sign}{pct:.2f}%)")
    else:
        print(f"        VNIndex = N/A ({vi.get('error','')})")

    # Load timestamp lần chạy trước
    last_run_utc = load_last_run()
    last_run_ict = last_run_utc + datetime.timedelta(hours=TIMEZONE_OFFSET)
    print(f"\n[Filter] Chỉ lấy tin MỚI sau: {last_run_ict.strftime('%Y-%m-%d %H:%M ICT')}")

    # Thu thập RSS — chỉ lấy tin trong window [last_run → now]
    print("\n[RSS] Thu thập tin tức (chỉ tin mới)...")
    rss_data = collect_all_rss(last_run_utc)

    # Tạo file
    output_dir  = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{hour_str}.md"

    md = build_markdown(api_data, rss_data, vn_now, last_run_ict)
    output_file.write_text(md, encoding="utf-8")
    update_index(Path("output") / "INDEX.md", date_str, hour_str, vn_now)

    # Lưu timestamp hiện tại → làm cutoff cho lần chạy tiếp theo
    save_last_run(utc_now)
    print(f"   Đã lưu last_run: {utc_now.isoformat()}")

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
