"""
Vietnam Intelligence Collector v5
===================================
Chiến lược mới hoàn toàn:
  - Dữ liệu số (vàng, tỷ giá, dầu, Fed, CPI) → API JSON miễn phí
  - Tin tức → RSS từ nguồn có feed thực sự hoạt động
  - Bỏ hoàn toàn Jina cho trang VN (JS-rendered, không crawl được)
  - Jina chỉ dùng cho bài báo cụ thể (có URL thẳng đến bài)
"""

import time, datetime, gzip, json, zlib, ssl, random
import urllib.request, urllib.error, urllib.parse
import re, xml.etree.ElementTree as ET
from pathlib import Path

TIMEZONE_OFFSET   = 7
REQUEST_TIMEOUT   = 20
MAX_ITEMS_RSS     = 8
MAX_CHARS_ARTICLE = 4000
JINA_BASE         = "https://r.jina.ai/"

LAST_RUN_FILE     = Path("output/last_run.txt")   # Lưu timestamp lần chạy trước
MARKET_CACHE_FILE = Path("output/market_cache.json")  # Giá tốt gần nhất (VNIndex, vàng)


def load_market_cache() -> dict:
    """Đọc giá tốt gần nhất từ lần chạy trước (persist vì workflow commit output/)."""
    try:
        if MARKET_CACHE_FILE.exists():
            return json.loads(MARKET_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_market_cache(cache: dict):
    try:
        MARKET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        MARKET_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


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
    """Giá vàng — gold-api.com (free, KHÔNG cần key) làm nguồn chính;
    Metal Sentinel làm fallback (cần RapidAPI key, hiện chưa cấu hình
    nên chỉ có tác dụng nếu sau này bạn thêm key vào)."""
    result = {"xau_usd": None, "xag_usd": None,
              "sjc_vnd": None, "source": "", "error": ""}

    # Nguồn 1: gold-api.com — free, KHÔNG cần API key, không giới hạn rate
    # cho giá real-time. Đã xác minh còn hoạt động (2026). Field name "price"
    # dựa trên giao diện trang chủ ("$X Per Oz"); nếu schema đổi, debug dưới
    # sẽ in ra toàn bộ response để chỉnh lại nhanh.
    try:
        d1 = fetch_json("https://api.gold-api.com/price/XAU")
        price = None
        if isinstance(d1, dict):
            price = d1.get("price") or d1.get("rate") or d1.get("value")
        if price:
            result["xau_usd"] = round(float(price), 2)
            result["source"]  = "gold-api.com"
            try:
                d2 = fetch_json("https://api.gold-api.com/price/XAG")
                if isinstance(d2, dict):
                    p2 = d2.get("price") or d2.get("rate") or d2.get("value")
                    if p2: result["xag_usd"] = round(float(p2), 2)
            except: pass
            sjc = get_sjc_gold_vn()
            result["sjc_vnd"] = sjc.get("sell")
            result["sjc_buy"] = sjc.get("buy")
            return result
        else:
            result["_goldapi_err"] = f"Response không đúng schema kỳ vọng: {str(d1)[:100]}"
    except Exception as e0:
        result["_goldapi_err"] = str(e0)[:80]

    # Nguồn 2: Metal Sentinel — cần RapidAPI key (X-RapidAPI-Key header),
    # hiện code KHÔNG truyền key nên nguồn này sẽ luôn fail cho tới khi
    # được cấu hình. Vẫn giữ làm fallback và sửa lỗi cũ (get_gold_prices()
    # từng vứt bỏ ms.get("error") mà không đọc — giờ đọc và surface ra).
    try:
        ms = get_metal_sentinel_gold()
        if ms.get("xau_usd"):
            result["xau_usd"] = ms["xau_usd"]
            result["xag_usd"] = ms.get("xag_usd")
            result["source"]  = "Metal Sentinel"
            sjc = get_sjc_gold_vn()
            result["sjc_vnd"] = sjc.get("sell")
            result["sjc_buy"] = sjc.get("buy")
            return result
        elif ms.get("error"):
            result["_ms_err"] = ms["error"]
    except Exception as e1:
        result["_ms_err"] = str(e1)[:80]

    debug = " | ".join(f"{k}={result[k]}" for k in ("_goldapi_err", "_ms_err") if k in result)
    result["error"] = f"Không lấy được giá vàng từ cả 2 nguồn. Debug: {debug or 'không có chi tiết'}"
    return result

def get_who_outbreaks(last_run_utc: datetime.datetime = None) -> list:
    """WHO Disease Outbreak News — REST API chính thức, không cần key.
    Lọc theo last_run_utc (giống RSS) + sort mới nhất trước, tránh trả về
    tin từ nhiều năm trước lẫn lộn với tin mới."""
    try:
        data = fetch_json("https://www.who.int/api/news/diseaseoutbreaknews")
        items = data if isinstance(data, list) else data.get("value", data.get("items", []))
        results = []
        for item in items:
            title   = item.get("title","") or item.get("Title","")
            date    = item.get("publicationDate","") or item.get("PublicationDate","")
            summary = item.get("summary","") or item.get("Summary","") or item.get("excerpt","")
            country = item.get("countryTitle","") or item.get("country","")
            url     = item.get("url","") or item.get("Url","")
            if not title or not date: continue
            dt = parse_pubdate(str(date))
            if last_run_utc is not None and (dt is None or dt <= last_run_utc):
                continue   # bỏ tin cũ hơn last_run — cùng logic với RSS
            if isinstance(summary, str):
                summary = summary[:300]
            results.append({
                "title":   title,
                "date":    str(date)[:20],
                "_sort":   dt or datetime.datetime.min,
                "summary": summary,
                "country": country,
                "url":     url,
            })
        results.sort(key=lambda x: x["_sort"], reverse=True)
        for r in results: r.pop("_sort", None)
        return results[:8]
    except Exception as e:
        return [{"error": str(e)[:100]}]


def get_usgs_earthquakes() -> list:
    """USGS Earthquake API — động đất >= M5.0 trong 24h qua, không cần key"""
    try:
        url = (
            "https://earthquake.usgs.gov/fdsnws/event/1/query"
            "?format=geojson&minmagnitude=5.0"
            "&orderby=time&limit=10"
            "&starttime={start}"
        )
        import datetime as _dt
        start = (_dt.datetime.utcnow() - _dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        data  = fetch_json(url.format(start=start))
        features = data.get("features", [])
        results  = []
        for f in features[:8]:
            p   = f.get("properties", {})
            geo = f.get("geometry", {}).get("coordinates", [None, None, None])
            results.append({
                "title":   p.get("title",""),
                "mag":     p.get("mag"),
                "place":   p.get("place",""),
                "time":    p.get("time"),
                "depth_km": round(geo[2], 1) if geo[2] is not None else None,
                "alert":   p.get("alert",""),
                "url":     p.get("url",""),
            })
        return results
    except Exception as e:
        return [{"error": str(e)[:100]}]


def get_gdelt_geopolitics() -> list:
    """GDELT API — sự kiện địa chính trị Đông Nam Á & VN, cập nhật 15 phút, không cần key"""
    results = []
    queries = [
        ("Vietnam geopolitics economy", "VN"),
        ("Southeast Asia trade policy 2026", "SEA"),
        ("US China trade war 2026", "US-CN"),
    ]
    for query, tag in queries:
        try:
            url = (
                "https://api.gdeltproject.org/api/v2/doc/doc"
                f"?query={urllib.parse.quote(query)}"
                "&mode=artlist&maxrecords=5&format=json"
                "&timespan=24h&sort=hybridrel"
            )
            data = fetch_json(url)
            if isinstance(data, dict) and "_error" in data:
                results.append({"tag": tag, "error": data["_error"][:80]})
                time.sleep(0.5); continue
            arts = data.get("articles", []) if isinstance(data, dict) else []
            if not arts:
                # GDELT trả JSON hợp lệ nhưng rỗng — thường do throttle hoặc
                # query không có kết quả trong 24h; ghi debug thay vì im lặng
                results.append({"tag": tag,
                                "error": f"0 bài (response: {str(data)[:60]})"})
            for a in arts[:3]:
                results.append({
                    "tag":     tag,
                    "title":   a.get("title",""),
                    "url":     a.get("url",""),
                    "source":  a.get("domain",""),
                    "seendate": a.get("seendate",""),
                    "tone":    a.get("tone"),
                })
            time.sleep(0.5)
        except Exception as e:
            results.append({"tag": tag, "error": str(e)[:80]})
    return results


def get_world_bank_vn() -> dict:
    """World Bank API — GDP, CPI, FDI của VN, không cần key, CC-BY 4.0"""
    result = {}
    indicators = {
        "GDP_USD":       "NY.GDP.MKTP.CD",
        "GDP_growth":    "NY.GDP.MKTP.KD.ZG",
        "inflation":     "FP.CPI.TOTL.ZG",
        "fdi_net":       "BX.KLT.DINV.CD.WD",
        "trade_pct_gdp": "NE.TRD.GNFS.ZS",
        "unemployment":  "SL.UEM.TOTL.ZS",
    }
    for key, ind in indicators.items():
        try:
            url  = f"https://api.worldbank.org/v2/country/VN/indicator/{ind}?format=json&mrv=3&per_page=3"
            data = fetch_json(url)
            if isinstance(data, list) and len(data) > 1:
                rows = [r for r in data[1] if r.get("value") is not None]
                if rows:
                    latest = rows[0]
                    result[key] = {
                        "value": latest["value"],
                        "year":  latest["date"],
                    }
            time.sleep(0.3)
        except Exception as e:
            result[key] = {"error": str(e)[:60]}
    result["source"] = "World Bank Open Data"
    return result


def get_sjc_gold_vn() -> dict:
    """Giá vàng SJC VN — endpoint text thuần, dễ parse"""
    result = {"buy": None, "sell": None, "unit": "nghìn đồng/chỉ", "source": "SJC"}
    try:
        req = urllib.request.Request(
            "https://sjc.com.vn/giavang/textContent.php",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain,*/*"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
        # Parse: dòng đầu là SJC 1L: mua | bán
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines[:5]:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    result["buy"]  = float(parts[0].replace(",","").replace(".",""))
                    result["sell"] = float(parts[1].replace(",","").replace(".",""))
                    result["raw"]  = line
                    return result
                except: continue
    except Exception as e:
        result["error"] = str(e)[:80]
    # Fallback: Jina
    try:
        jina_text = fetch_jina_content("https://sjc.com.vn/")
        result["jina_text"] = jina_text[:300]
    except: pass
    return result


def get_metal_sentinel_gold() -> dict:
    """Metal Sentinel API — XAU/XAG real-time, 15.000 req/tháng free"""
    result = {"xau_usd": None, "xag_usd": None, "source": ""}
    try:
        data = fetch_json("https://metal-sentinel.com/api/metal-quote?metals=XAU,XAG&currency=USD")
        if isinstance(data, dict):
            xau = data.get("XAU") or data.get("xau") or data.get("gold")
            xag = data.get("XAG") or data.get("xag") or data.get("silver")
            if xau:
                result["xau_usd"] = round(float(xau), 2)
                result["source"]  = "Metal Sentinel"
            if xag:
                result["xag_usd"] = round(float(xag), 2)
    except Exception as e:
        result["error"] = str(e)[:80]
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


VNINDEX_SANITY_RANGE = (300.0, 5000.0)  # VNIndex thực tế chưa từng nằm ngoài khoảng này


def _vnindex_plausible(v) -> bool:
    """Sanity-check: từ chối số vô lý (vd. bắt nhầm '17' từ regex) thay vì báo cáo như số thật."""
    try:
        return VNINDEX_SANITY_RANGE[0] <= float(v) <= VNINDEX_SANITY_RANGE[1]
    except (TypeError, ValueError):
        return False


def _http_err_detail(e: Exception) -> str:
    """Trích status code + 150 ký tự đầu response body (nếu có) từ HTTPError.
    Giúp phân biệt 'WAF trả trang chặn giả dạng lỗi' vs 'endpoint đổi thật' ở
    lần debug tiếp theo, thay vì chỉ có mã lỗi trần trụi không rõ nguyên nhân."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read(200).decode("utf-8", errors="replace").replace("\n", " ").strip()
        except Exception:
            body = ""
        return f"HTTP {e.code}" + (f" | body: {body[:150]}" if body else "")
    return str(e)[:80]


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
            **RSS_HEADERS,
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
        if d.get("indexValue") and _vnindex_plausible(d.get("indexValue")):
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
        elif d.get("indexValue"):
            result["_ssi_err"] = f"Giá trị vô lý bị loại: {d.get('indexValue')}"
    except Exception as e:
        result["_ssi_err"] = _http_err_detail(e)

    # Nguồn 2: TCBS public market summary
    try:
        url3 = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/VNIndex"
        req3 = urllib.request.Request(url3, headers={
            **RSS_HEADERS,
            "Accept": "application/json",
            "Origin": "https://tcinvest.tcbs.com.vn",
            "Referer": "https://tcinvest.tcbs.com.vn/",
        })
        with urllib.request.urlopen(req3, timeout=REQUEST_TIMEOUT) as resp3:
            raw3 = resp3.read()
        if raw3[:2] == b"\x1f\x8b": raw3 = gzip.decompress(raw3)
        d3 = json.loads(raw3.decode("utf-8", errors="replace"))
        if d3.get("indexValue") and _vnindex_plausible(d3.get("indexValue")):
            result["vnindex"]        = float(d3.get("indexValue", 0))
            result["vnindex_change"] = float(d3.get("change", 0))
            result["vnindex_pct"]    = float(d3.get("percentChange", 0))
            result["source"]         = "TCBS API"
            return result
        elif d3.get("indexValue"):
            result["_tcbs_err"] = f"Giá trị vô lý bị loại: {d3.get('indexValue')}"
    except Exception as e2:
        result["_tcbs_err"] = _http_err_detail(e2)

    # Nguồn 3: VNDirect dchart (public chart API, thường không chặn IP datacenter
    # như SSI/TCBS) — lấy nến ngày gần nhất, dùng giá đóng cửa 'c' làm indexValue.
    try:
        now_ts = int(time.time())
        url_dc = ("https://dchart-api.vndirect.com.vn/dchart/history"
                  f"?resolution=1D&symbol=VNINDEX&from={now_ts-7*86400}&to={now_ts}")
        req_dc = urllib.request.Request(url_dc, headers={
            **RSS_HEADERS,
            "Accept": "application/json",
            "Origin": "https://dstock.vndirect.com.vn",
            "Referer": "https://dstock.vndirect.com.vn/",
        })
        with urllib.request.urlopen(req_dc, timeout=REQUEST_TIMEOUT) as resp_dc:
            raw_dc = resp_dc.read()
        if raw_dc[:2] == b"\x1f\x8b": raw_dc = gzip.decompress(raw_dc)
        d_dc = json.loads(raw_dc.decode("utf-8", errors="replace"))
        closes = d_dc.get("c") or []
        opens  = d_dc.get("o") or []
        if d_dc.get("s") == "ok" and closes and _vnindex_plausible(closes[-1]):
            last_close = float(closes[-1])
            prev_ref   = float(opens[-1]) if opens else last_close
            result["vnindex"]        = last_close
            result["vnindex_change"] = round(last_close - prev_ref, 2)
            result["vnindex_pct"]    = round((last_close - prev_ref) / prev_ref * 100, 2) if prev_ref else 0.0
            result["source"]         = "VNDirect dchart"
            return result
        elif closes:
            result["_vndirect_err"] = f"Giá trị vô lý bị loại: {closes[-1]}"
        else:
            result["_vndirect_err"] = f"Không có dữ liệu (status={d_dc.get('s')})"
    except Exception as e_dc:
        result["_vndirect_err"] = _http_err_detail(e_dc)

    # Nguồn 4: Jina đọc CafeF bảng giá (fallback cuối) — regex có thể bắt nhầm số rác
    # nên BẮT BUỘC qua sanity-check; nguồn này không có change/pct đáng tin cậy
    # nên cố tình để None thay vì mặc định 0 (tránh hiển thị giả "+0.00%").
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
            candidate = float(m.group(1).replace(",",""))
            if _vnindex_plausible(candidate):
                result["vnindex"] = candidate
                result["source"]  = "CafeF Jina (fallback, chưa xác thực change/pct)"
                return result
            else:
                result["_jina_err"] = f"Regex bắt nhầm giá trị vô lý: {candidate}"
        else:
            result["_jina_err"] = "Không tìm thấy pattern VNIndex trong trang (có thể do JS-render)"
    except Exception as e3:
        result["_jina_err"] = str(e3)[:80]

    debug = " | ".join(f"{k}={result[k]}" for k in
                       ("_ssi_err","_tcbs_err","_vndirect_err","_jina_err") if k in result)
    result["error"] = f"Không lấy được VNIndex hợp lệ từ cả 4 nguồn (SSI/TCBS/VNDirect/CafeF-Jina). Debug: {debug}"
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
    # CNN RSS bị chặn SSL với client không phải browser (lỗi lặp lại qua nhiều
    # lần chạy) → thay bằng CNBC (feed ID ổn định lâu năm, không chặn bot)
    {"group": 2, "name": "CNBC World News",             "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"},
    {"group": 3, "name": "CNBC Business",               "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147"},

    # Reuters — đã tắt RSS trực tiếp 2020, dùng Google News RSS
    # GNews search endpoint bị Google chặn với IP datacenter (Feed rỗng lặp lại
    # dù đã retry) → chuyển sang topic feed (ít bị chặn hơn endpoint search)
    {"group": 2, "name": "Google News World",           "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en"},
    {"group": 3, "name": "Google News Business",        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"},

    # NYT — RSS còn hoạt động (nội dung tóm tắt, full article có paywall)
    {"group": 2, "name": "NYT World",                   "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"group": 3, "name": "NYT Business",                "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},

    # Washington Post — RSS còn hoạt động
    {"group": 2, "name": "Washington Post World",       "url": "https://feeds.washingtonpost.com/rss/world"},
    {"group": 3, "name": "Washington Post Business (GNews)", "url": "https://news.google.com/rss/search?q=when:24h+allinurl:washingtonpost.com/business&hl=en-US&gl=US&ceid=US:en"},

    # Bloomberg — không có public RSS, dùng Google News RSS về Bloomberg
    {"group": 3, "name": "MarketWatch Top Stories",     "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    {"group": 6, "name": "Bloomberg Economics (GNews)", "url": "https://news.google.com/rss/search?q=when:24h+allinurl:bloomberg.com+fed+rate+economy&hl=en-US&gl=US&ceid=US:en"},

    # Giữ lại The Guardian + RFI
    {"group": 2, "name": "The Guardian World",         "url": "https://www.theguardian.com/world/rss"},
    {"group": 2, "name": "RFI English",                "url": "https://www.rfi.fr/en/rss"},
    {"group": 3, "name": "The Guardian Business",      "url": "https://www.theguardian.com/business/rss"},

    # AP News — thêm vào làm nguồn tin cậy
    # TODO: feeds.apnews.com không còn resolve DNS (AP đã khai tử subdomain feed cũ).
    # Cần tìm domain feed RSS mới của AP hoặc bỏ hẳn nguồn này.
    # {"group": 2, "name": "AP News World",            "url": "https://feeds.apnews.com/rss/apf-intlnews"},
    # {"group": 3, "name": "AP News Business",         "url": "https://feeds.apnews.com/rss/apf-business"},

    # ── Việt Nam tin tức ──────────────────────────────────────────
    # VnExpress — thường bị 503 do chặn bot, dùng VnEconomy + Tuổi Trẻ thay thế
    {"group": 3, "name": "VnEconomy Chứng khoán",      "url": "https://vneconomy.vn/chung-khoan.rss"},
    {"group": 3, "name": "VnEconomy Tài chính",        "url": "https://vneconomy.vn/tai-chinh.rss"},
    {"group": 3, "name": "Tuổi Trẻ Kinh doanh",        "url": "https://tuoitre.vn/rss/kinh-doanh.rss"},
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
    # TODO: nguoiquansat.vn bị Cloudflare bot-challenge chặn ở CẢ 6 endpoint —
    # Jina reader free tier không vượt qua được "Just a moment..." của Cloudflare.
    # Cần nguồn thay thế tương đương hoặc dịch vụ crawl có anti-detection.
    # {"group": 3,  "name": "NQS Chứng khoán",           "jina": "https://nguoiquansat.vn/chung-khoan"},
    # {"group": 3,  "name": "NQS Doanh nghiệp",          "jina": "https://nguoiquansat.vn/doanh-nghiep"},
    # {"group": 3,  "name": "NQS Vĩ mô",                 "jina": "https://nguoiquansat.vn/vi-mo"},
    # {"group": 11, "name": "NQS Tài chính Ngân hàng",   "jina": "https://nguoiquansat.vn/tai-chinh-ngan-hang"},
    # {"group": 12, "name": "NQS Vàng - Tỷ giá",         "jina": "https://nguoiquansat.vn/tai-chinh-ngan-hang/vang-ty-gia"},
    # {"group": 2,  "name": "NQS Thế giới",               "jina": "https://nguoiquansat.vn/the-gioi"},

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
    # TODO: ProMED đã đổi nền tảng (Next.js/Vercel), /feed/ không còn tồn tại và
    # không tìm thấy RSS thay thế công khai trên trang mới — cần quyết định hướng
    # (xem "Giai đoạn 3" trong kế hoạch sửa chữa) trước khi bật lại nguồn này.
    # {"group": 1, "name": "ProMED Mail",               "url": "https://promedmail.org/feed/"},
    {"group": 1, "name": "CDC Health Updates",          "url": "https://tools.cdc.gov/api/v2/resources/media/316422.rss"},

    # ── Trump / Địa chính trị Mỹ ─────────────────────────────────
    # White House đã bỏ RSS — dùng Jina đọc trang HTML
    {"group":14, "name": "White House News",            "jina": "https://www.whitehouse.gov/news/"},
    {"group":14, "name": "White House Briefings",       "jina": "https://www.whitehouse.gov/briefings-statements/"},
    {"group":14, "name": "White House Executive Orders","jina": "https://www.whitehouse.gov/presidential-actions/executive-orders/"},
    {"group":14, "name": "White House Remarks Trump",   "jina": "https://www.whitehouse.gov/remarks/"},
    {"group":14, "name": "White House Fact Sheets",     "jina": "https://www.whitehouse.gov/fact-sheets/"},

    # ── GDACS — Cảnh báo thiên tai EU JRC (RSS chuẩn, không cần key) ──
    {"group": 1, "name": "GDACS Thiên tai TG",          "url":  "https://www.gdacs.org/xml/rss.xml"},

    # ── Pháp luật VN — LuatVietnam (có tóm tắt nội dung) ────────────
    {"group": 10, "name": "LuatVietnam Tài chính NH",   "jina": "https://luatvietnam.vn/tai-chinh.html"},
    {"group": 10, "name": "LuatVietnam Bất động sản",   "jina": "https://luatvietnam.vn/bat-dong-san.html"},
    {"group": 10, "name": "LuatVietnam Mới nhất",       "jina": "https://luatvietnam.vn/van-ban-moi-nhat.html"},
    {"group": 10, "name": "vbpl.vn Trung ương",         "jina": "https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx"},

    # ── Lãnh đạo VN — TTXVN / Báo Tin Tức (RSS) ─────────────────────
    {"group": 13, "name": "TTXVN Thời sự",              "url":  "https://baotintuc.vn/rss/thoi-su.rss"},
    {"group": 13, "name": "TTXVN Chính trị",            "url":  "https://baotintuc.vn/rss/chinh-tri.rss"},
    {"group": 13, "name": "Nhân dân Chính trị",         "url":  "https://nhandan.vn/rss/chinh-tri.rss"},

    # ── Thiên tai VN — Khí tượng thủy văn ───────────────────────────
    {"group": 1,  "name": "KTTV VN Tin tức",            "url":  "https://nchmf.gov.vn/kttvsite/vi-VN/1/homerss.html"},
    {"group": 1,  "name": "PCTT VN Thông báo",          "jina": "https://phongchongthientai.mard.gov.vn/Pages/tin-tuc.aspx"},

    # ── GSO Kinh tế VN ───────────────────────────────────────────────
    {"group": 3,  "name": "GSO Thông cáo thống kê",     "jina": "https://www.gso.gov.vn/tin-tuc-thong-ke/"},

    # ── Bộ Công Thương — Giá xăng dầu VN ────────────────────────────
    {"group": 9,  "name": "Bộ Công Thương Giá xăng",   "jina": "https://www.moit.gov.vn/tin-tuc/dieu-hanh-gia-xang-dau"},

    # ── Tạp chí Ngân hàng ────────────────────────────────────────────
    {"group": 11, "name": "Tạp chí Ngân hàng",          "jina": "https://tapchinganhang.gov.vn/"},
]


def decompress(data: bytes) -> bytes:
    if data[:2] == b'\x1f\x8b':
        try: return gzip.decompress(data)
        except: pass
    try: return zlib.decompress(data)
    except: pass
    return data


def _regex_parse_rss(text: str) -> list:
    """Parse RSS bằng regex khi XML sai chuẩn nặng (TTXVN...). Best-effort.
    Thử <item> (RSS 2.0) trước; nếu rỗng, thử <entry> (Atom) — một số feed VN
    (TTXVN/KTTV) đổi định dạng hoặc trả HTML lỗi lẫn Atom tag rời rạc."""
    def _tag(block, name):
        m = re.search(rf'<{name}[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>',
                      block, re.S | re.I)
        return (m.group(1).strip() if m else "")

    def _parse_blocks(tag: str, link_from_attr: bool = False) -> list:
        found = []
        for m in re.finditer(rf'<{tag}[\s>].*?</{tag}>', text, re.S | re.I):
            block = m.group(0)
            title = re.sub(r'<[^>]+>', ' ', _tag(block, "title")).strip()
            if link_from_attr:
                lm = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', block, re.I)
                link = lm.group(1) if lm else _tag(block, "link")
            else:
                link = _tag(block, "link")
            desc = re.sub(r'<[^>]+>', ' ',
                          _tag(block, "description") or _tag(block, "summary")
                          or _tag(block, "content"))
            desc = re.sub(r'\s+', ' ', desc).strip()[:400]
            pubdate = (_tag(block, "pubDate") or _tag(block, "published")
                      or _tag(block, "updated"))
            if title:
                found.append({"title": title, "link": link,
                              "summary": desc, "published": pubdate[:50]})
            if len(found) >= MAX_ITEMS_RSS: break
        return found

    items = _parse_blocks("item")
    if not items:
        items = _parse_blocks("entry", link_from_attr=True)
    return items


def _fetch_rss_once(url: str) -> list:
    req = urllib.request.Request(url, headers=RSS_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
    except Exception as e:
        err_str = str(e)
        # Server dùng TLS renegotiation cũ (vd. baotintuc.vn/TTXVN) mà OpenSSL 3.x
        # mặc định từ chối — thử lại 1 lần với context cho phép legacy renegotiation
        # thay vì bỏ cuộc ngay.
        if "UNSAFE_LEGACY_RENEGOTIATION" in err_str or "legacy renegotiation" in err_str.lower():
            try:
                legacy_ctx = ssl.create_default_context()
                legacy_ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=legacy_ctx) as resp:
                    raw = decompress(resp.read())
            except Exception as e2:
                return [{"error": f"{type(e2).__name__}: {str(e2)[:80]} (đã thử legacy SSL context)"}]
        else:
            return [{"error": f"{type(e).__name__}: {err_str[:80]}"}]

    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except:
            text = raw.decode("latin-1", errors="replace")

    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'encoding=["\'][^"\']+["\']', 'encoding="utf-8"', text, count=1)

    head_lower = text[:500].lower()
    if "<item" not in head_lower and "<entry" not in head_lower and (
            "<!doctype html" in head_lower or "<html" in head_lower):
        return [{"error": "Server trả về trang HTML, không phải RSS/XML "
                           "(có thể do chặn bot hoặc feed URL đã đổi)"}]

    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        # Fix & không encode — lỗi phổ biến ở CafeF, nguồn VN
        text2 = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', text)
        # Fix < trần trong nội dung (vd. KTTV: "mưa <10mm") — chỉ escape <
        # KHÔNG theo sau bởi ký tự bắt đầu tag hợp lệ (chữ cái, /, !, ?)
        text2 = re.sub(r'<(?![a-zA-Z/!?])', '&lt;', text2)
        try:
            root = ET.fromstring(text2.encode("utf-8"))
        except ET.ParseError as e2:
            # Fallback cuối: feed viết sai chuẩn XML nặng (TTXVN) — trích
            # <item> bằng regex thay vì bỏ cuộc
            items = _regex_parse_rss(text)
            if items:
                return items
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


def fetch_rss(url: str) -> list:
    """Wrapper quanh _fetch_rss_once(): với Google News RSS (news.google.com),
    'Feed rỗng' có thể do throttle tạm thời từ IP dùng chung của GitHub Actions
    chứ không hẳn là thực sự không có tin — thử lại 1 lần sau khi chờ jitter."""
    items = _fetch_rss_once(url)
    if ("news.google.com" in url and items and len(items) == 1
            and items[0].get("error") == "Feed rỗng"):
        time.sleep(random.uniform(3, 7))
        items = _fetch_rss_once(url)
    return items


def is_important(title: str, summary: str) -> bool:
    return any(kw in (title+" "+summary).lower() for kw in IMPORTANT_KEYWORDS)


def _is_nav_boilerplate(line: str) -> bool:
    """True nếu dòng trông như menu/nav (nhiều link liên tiếp, không phải văn
    xuôi) — vd. danh sách 63 tỉnh thành VnExpress, thanh chuyên mục báo VN."""
    link_count = line.count("](")
    if link_count >= 3:
        return True
    # Dòng toàn các cụm ngắn lặp lại kiểu "[Chọn mặc định]...[Xem]...[Mặc định]"
    if link_count >= 1 and len(line) / max(link_count, 1) < 25:
        return True
    return False


def fetch_full_article(url: str) -> str:
    if not url or not url.startswith("http"): return ""
    req = urllib.request.Request(JINA_BASE + url, headers=JINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.split("\n")
                 if len(l.strip()) > 30 and not l.strip().startswith("http")
                 and not _is_nav_boilerplate(l.strip())]
        return "\n".join(lines[:80])[:MAX_CHARS_ARTICLE]
    except:
        return ""


ECON_SOCIAL_KEYWORDS = [
    # Kinh tế - tài chính
    "kinh tế","tài chính","ngân hàng","lãi suất","tỷ giá","tín dụng","chứng khoán",
    "cổ phiếu","trái phiếu","đầu tư","gdp","lạm phát","cpi","xuất khẩu","nhập khẩu",
    "thuế","ngân sách","fdi","bất động sản","đất đai","giá vàng","giá dầu","giá điện",
    "doanh nghiệp","thị trường","thương mại","hải quan","đấu giá","đấu thầu",
    "nghị quyết","nghị định","thông tư","quyết định","chỉ thị","luật","quy hoạch",
    # Xã hội - chính sách lớn
    "lương","bảo hiểm","y tế","giáo dục","hạ tầng","cao tốc","metro","sân bay",
    "điện","năng lượng","chuyển đổi số","công nghệ","bán dẫn","ai ",
    # English (White House...)
    "econom","tariff","trade","tax","interest rate","inflation","invest",
    "energy","chip","semiconductor","sanction","executive order","budget",
]


def _score_econ_relevance(title: str) -> int:
    """Đếm số keyword kinh tế-tài chính-xã hội khớp trong tiêu đề."""
    t = title.lower()
    return sum(1 for kw in ECON_SOCIAL_KEYWORDS if kw in t)


def _extract_links_from_html(url: str) -> list:
    """Fallback khi Jina lỗi (vd. 422): fetch thẳng HTML gốc và trích link <a>.
    Hoạt động tốt với trang server-rendered (GSO WordPress, vbpl ASP.NET...)."""
    try:
        req = urllib.request.Request(url, headers=RSS_HEADERS)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
        html = raw.decode("utf-8", errors="replace")
        # <a href="...">tiêu đề</a> — cho phép thẻ lồng bên trong, strip tag sau
        pairs = []
        for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
            href, inner = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', ' ', inner)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) < 20: continue
            if href.startswith("/"):
                base = re.match(r'(https?://[^/]+)', url)
                href = (base.group(1) if base else url.rstrip("/")) + href
            if not href.startswith("http"): continue
            pairs.append((title, href))
        return pairs
    except Exception:
        return []


_ARTICLE_URL_REQUIRED = {
    # domain → regex mà href PHẢI khớp mới được coi là bài viết thật.
    # Chỉ áp cho domain đã quan sát thấy hay lẫn link menu/nav vào danh sách
    # headline (White House, PCTT) — domain khác không bị ràng buộc thêm.
    "whitehouse.gov": re.compile(
        r"/(briefings-statements|fact-sheets|presidential-actions|remarks)/\d{4}/\d{2}/", re.I),
    "phongchongthientai.mard.gov.vn": re.compile(
        r"/Pages/[a-zA-Z0-9\-]{20,}\.aspx", re.I),
}


def _passes_article_url_pattern(href: str) -> bool:
    """True nếu href không thuộc domain bị ràng buộc, HOẶC khớp pattern bài viết."""
    for domain, pattern in _ARTICLE_URL_REQUIRED.items():
        if domain in href:
            return bool(pattern.search(href))
    return True


def _filter_headline(title: str, href: str, source_url: str, noise: set, seen: set) -> bool:
    """True nếu đây là headline bài viết thật đáng giữ."""
    tl = title.lower()
    if any(n in tl for n in noise): return False
    # Loại link ảnh/markdown image lọt vào ([![Image 26: ads](...)
    if title.startswith("!") or "![image" in tl or "image " in tl[:12]: return False
    if "ads" == tl or tl.startswith("ads"): return False
    # Loại widget thời tiết kiểu "Lai Châu 22° - 23°..."
    if "°" in title: return False
    # Loại nav tiếng Anh của SharePoint/ASP.NET (PCTT): "Turn on more accessible mode"
    if tl.startswith(("turn on", "turn off", "skip ribbon", "sign in")): return False
    if not re.search(r'[.!?]| ', title): return False   # nhãn 1 từ
    # Loại link trỏ về CHÍNH trang danh sách (nav item không có bài riêng)
    if href.rstrip("/") == source_url.rstrip("/"): return False
    if href in seen or title in seen: return False       # dedupe
    # Domain hay lẫn menu (White House, PCTT): bắt buộc href đúng cấu trúc bài viết
    if not _passes_article_url_pattern(href): return False
    return True


_BLOCKED_PAGE_MARKERS = [
    "404", "not found", "không tồn tại", "đã bị gỡ",
    "just a moment", "security verification", "checking your browser",
    "verify you are human", "enable javascript and cookies",
    "access denied", "forbidden",
]

def _blocked_page_marker(text: str) -> str:
    """Kiểm tra 800 ký tự đầu của nội dung xem có phải trang lỗi/chặn không.
    Trả về marker khớp được (để log rõ lý do), hoặc '' nếu nội dung có vẻ hợp lệ."""
    head = text[:800].lower()
    for marker in _BLOCKED_PAGE_MARKERS:
        if marker in head:
            return marker
    return ""


def fetch_jina_content(url: str) -> str:
    """Fetch Jina và trả về danh sách headline dạng '- [tiêu đề](link)'.
    Nếu Jina lỗi (vd. 422) → fallback fetch thẳng HTML gốc để trích link."""
    noise = {"cookie","javascript","subscribe","sign in","log in",
             "advertisement","đăng nhập","đăng ký","skip to content",
             "toggle navigation","menu","weather","thời tiết",
             "trang chủ","liên hệ","sơ đồ","giới thiệu cổng",
             "thư điện tử","văn phòng điện tử","lịch công tác",
             "đặt tạp chí","đặt báo","mua báo","quảng cáo","podcast",
             "youtube","rss","tải app","app store","google play",
             # Nav cố định White House — trùng econ keyword (budget, executive
             # order) nên hay bị chọn nhầm làm "tin nổi bật" dù chỉ là menu
             "executive orders","office of management and budget",
             "council of economic advisors","grow the economy",
             "unleash american energy","working families tax cut",
             "major investments in america","election integrity",
             "save america","ratepayer protection","lab leak",
             "january 6","arrested: worst of the worst","this is our why",
             "criminal aliens","briefings & statements","presidential actions",
             "download the official white house app",
             # Nav cố định LuatVietnam — lặp lại y hệt ở mọi trang chuyên mục
             "tính lãi suất","tính thuế thu nhập cá nhân",
             "tính bảo hiểm xã hội","tính lương gross","tính bảo hiểm thất nghiệp",
             "đấu thầu-cạnh tranh","giáo dục-đào tạo-dạy nghề",
             "khoa học-công nghệ","lao động-tiền lương","pháp lý doanh nghiệp",
             "dịch vụ dịch thuật","dịch vụ nội dung","tổng đài tư vấn",
             "phiên bản tiếng anh","gói dịch vụ & giá",
             # Nav cố định VNDMS/PCTT
             "chú giải","turn on more accessible","turn off more accessible",
             "sơ đồ tổ chức","chức năng, nhiệm vụ","đơn vị trực thuộc",
             "ban chỉ huy pctt"}

    jina_err = ""
    text = ""
    try:
        req = urllib.request.Request(JINA_BASE + url, headers=JINA_HEADERS)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = decompress(resp.read())
            text = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            # 422 thường do URL chưa được encode đúng khi ghép vào r.jina.ai/
            try:
                quoted = urllib.parse.quote(url, safe=":/?=&%")
                req2 = urllib.request.Request(JINA_BASE + quoted, headers=JINA_HEADERS)
                with urllib.request.urlopen(req2, timeout=REQUEST_TIMEOUT) as resp2:
                    raw = decompress(resp2.read())
                    text = raw.decode("utf-8", errors="replace")
            except Exception as e2:
                jina_err = f"HTTP 422 (đã thử encode lại URL): {str(e2)[:60]}"
        else:
            jina_err = str(e)[:80]
    except Exception as e:
        jina_err = str(e)[:80]

    if text:
        blocked = _blocked_page_marker(text)
        if blocked:
            return f"[Lỗi Jina: trang lỗi/bị chặn — phát hiện '{blocked}' ({url})]"

    headline_candidates, seen = [], set()

    if text:
        link_pattern = re.compile(r'\[([^\]]{15,200})\]\((https?://[^\)]+)\)')
        for line in text.split("\n"):
            for m in link_pattern.finditer(line):
                title, href = m.group(1).strip(), m.group(2).strip()
                if _filter_headline(title, href, url, noise, seen):
                    headline_candidates.append((title, href))
                    seen.add(href); seen.add(title)

    # Fallback: Jina lỗi HOẶC Jina thành công nhưng không trích được gì
    # (trang JS-render một phần) → thử HTML gốc
    if len(headline_candidates) < 3:
        for title, href in _extract_links_from_html(url):
            if _filter_headline(title, href, url, noise, seen):
                headline_candidates.append((title, href))
                seen.add(href); seen.add(title)

    if len(headline_candidates) >= 3:
        # Sắp xếp: headline liên quan kinh tế-tài chính-xã hội lên đầu
        headline_candidates.sort(key=lambda th: -_score_econ_relevance(th[0]))
        out = [f"- [{t}]({h})" for t, h in headline_candidates[:15]]
        return ("\n".join(out))[:5000]

    # Pass cuối: trang thông báo đơn lẻ không có danh sách link — lọc đoạn văn
    if text:
        out = []
        for line in text.split("\n"):
            s = line.strip()
            if len(s) < 20: continue
            if re.match(r'^https?://\S+$', s): continue
            if re.match(r'^[=\-_*#|]{3,}$', s): continue
            if any(n in s.lower() for n in noise): continue
            if _is_nav_boilerplate(s): continue
            out.append(s)
        if out:
            return "\n".join(out[:150])[:5000]

    return f"[Lỗi Jina: {jina_err or 'không trích được nội dung nào'}]"


def enrich_jina_with_articles(content: str, max_articles: int = 2) -> str:
    """Nhận danh sách headline '- [t](h)', chọn tối đa N bài NỔI BẬT nhất về
    kinh tế-tài chính-xã hội, đọc full qua Jina và đính kèm trích đoạn.
    Đây là bước 'trích thông tin chi tiết' thay vì chỉ liệt kê đầu mục."""
    pairs = re.findall(r'^- \[(.+?)\]\((https?://[^\)]+)\)$', content, re.M)
    if not pairs:
        return content
    scored = sorted(pairs, key=lambda th: -_score_econ_relevance(th[0]))
    extras = []
    for title, href in scored[:max_articles]:
        if _score_econ_relevance(title) == 0:
            break   # danh sách đã sort — gặp bài 0 điểm thì các bài sau cũng 0
        body = fetch_full_article(href)
        if body:
            excerpt = body[:900]
            extras.append(f"\n📌 **Chi tiết nổi bật: {title}**\n> {excerpt}")
            time.sleep(0.5)
    return content + ("\n" + "\n".join(extras) if extras else "")


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
            ok = not content.startswith("[Lỗi")
            if ok:
                # Đọc sâu 2 bài nổi bật nhất về kinh tế-tài chính-xã hội
                content = enrich_jina_with_articles(content, max_articles=2)
            result = {
                "name": src["name"], "mode": "Jina",
                "ok": ok,
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
        # Chỉ tính chg/pct khi THỰC SỰ có dữ liệu — None nghĩa là nguồn (vd. Jina
        # fallback) không cung cấp, phải hiện "N/A", không được ngầm hiểu là "không đổi"
        has_chg = vi.get("vnindex_change") is not None
        chg   = float(vi.get("vnindex_change")) if has_chg else 0.0
        pct   = float(vi.get("vnindex_pct") or 0) if has_chg else 0.0
        sign  = "+" if chg >= 0 else ""
        arrow = "🟢" if chg >= 0 else ("🔴" if chg < 0 else "⚪")
        chg_display = f"{arrow} {sign}{fmt_num(chg,2,'')} ({sign}{fmt_num(pct,2,'%')})" if has_chg else "⚪ N/A (nguồn không cung cấp % thay đổi)"
        lines += [
            "### 📈 VNIndex & TTCK Việt Nam",
            "| Chỉ số | Điểm | Thay đổi | Nguồn |",
            "|---|---|---|---|",
            f"| **VNIndex** | **{fmt_num(vi['vnindex'],2,'')}** | {chg_display} | {vi.get('source','N/A')} |",
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
    # Lưu ý: KHÔNG thêm "vnindex" vào danh sách dưới — khối if/else phía trên
    # đã tự render cảnh báo VNIndex riêng; thêm lại vào đây sẽ in trùng 2 lần.
    for key, label in [("gold","Vàng"),("fx","Tỷ giá"),("fed","Fed"),("cpi","CPI"),("jobs","Jobs")]:
        d = api_data.get(key,{})
        if d.get("error"):
            lines.append(f"> ⚠️ {label}: {d['error']}")
    lines += ["", "---", ""]

    # ── WHO Disease Outbreaks ──────────────────────────────────────────
    who_data  = api_data.get("who_outbreaks", [])
    who_error = who_data[0].get("error") if who_data and "error" in who_data[0] else None
    who_ok    = [x for x in who_data if "title" in x]
    lines += ["## 🦠 WHO Disease Outbreak News (API Chính thức)", ""]
    if who_ok:
        lines.append(f"*{len(who_ok)} cảnh báo dịch bệnh MỚI từ WHO*")
        lines.append("")
        for item in who_ok[:6]:
            country = f" — {item['country']}" if item.get("country") else ""
            link    = f"[{item['title']}]({item['url']})" if item.get("url") else item["title"]
            lines.append(f"**{link}**{country}")
            if item.get("date"):
                lines.append(f"*{item['date']}*")
            if item.get("summary"):
                lines.append(f"> {str(item['summary'])[:250]}")
            lines.append("")
    elif who_error:
        lines.append(f"> ⚠️ WHO API: Không lấy được dữ liệu ({who_error})")
    else:
        lines.append("*Không có cảnh báo dịch bệnh MỚI từ WHO trong window này*")
    lines += ["---", ""]

    # ── USGS Earthquakes ────────────────────────────────────────────────
    eq_data = api_data.get("earthquakes", [])
    eq_ok   = [x for x in eq_data if "mag" in x]
    lines += ["## 🌍 Động đất Toàn cầu (USGS, M≥5.0, 24h qua)", ""]
    if eq_ok:
        lines.append(f"*{len(eq_ok)} trận động đất trong 24h qua*")
        lines.append("")
        lines.append("| Độ lớn | Địa điểm | Độ sâu | Cảnh báo |")
        lines.append("|---|---|---|---|")
        for eq in eq_ok:
            mag   = f"M{eq.get('mag','?')}"
            place = eq.get("place","?")[:50]
            depth = f"{eq.get('depth_km','?')} km"
            alert = eq.get("alert","—") or "—"
            lines.append(f"| **{mag}** | {place} | {depth} | {alert} |")
        lines.append("")
    else:
        lines.append("> Không có động đất M≥5.0 trong 24h qua")
    lines += ["---", ""]

    # ── GDELT Geopolitics ───────────────────────────────────────────────
    gd_data = api_data.get("gdelt", [])
    gd_ok   = [x for x in gd_data if "title" in x]
    lines += ["## 🌐 GDELT Địa chính trị (Cập nhật 15 phút)", ""]
    if gd_ok:
        lines.append(f"*{len(gd_ok)} bài từ GDELT — VN, SEA, Mỹ-Trung*")
        lines.append("")
        cur_tag = None
        for item in gd_ok:
            if item.get("tag") != cur_tag:
                cur_tag = item.get("tag")
                tag_names = {"VN": "🇻🇳 Việt Nam", "SEA": "🌏 Đông Nam Á", "US-CN": "🇺🇸🇨🇳 Mỹ-Trung"}
                lines.append(f"**{tag_names.get(cur_tag, cur_tag)}**")
            title  = item.get("title","")
            src    = item.get("source","")
            url    = item.get("url","")
            tone   = item.get("tone")
            tone_s = f" (tone: {tone:.1f})" if tone is not None else ""
            if url:
                lines.append(f"- [{title}]({url}) *{src}*{tone_s}")
            else:
                lines.append(f"- {title} *{src}*{tone_s}")
        lines.append("")
    else:
        gd_errs = [f"{x.get('tag','?')}: {x.get('error','?')}" for x in gd_data if "error" in x]
        if gd_errs:
            lines.append(f"> ⚠️ GDELT API: Không có dữ liệu. Debug: {' | '.join(gd_errs[:3])}")
        else:
            lines.append("> ⚠️ GDELT API: Không có dữ liệu (không có debug — hàm không trả gì)")
    lines += ["---", ""]

    # ── World Bank VN ───────────────────────────────────────────────────
    wb = api_data.get("worldbank_vn", {})
    lines += ["## 🏦 World Bank — Kinh tế Vĩ mô Việt Nam", ""]
    wb_display = {
        "GDP_USD":       ("GDP (USD)", "tỷ USD", 1e9),
        "GDP_growth":    ("Tăng trưởng GDP", "%", 1),
        "inflation":     ("Lạm phát CPI", "%", 1),
        "fdi_net":       ("FDI ròng", "tỷ USD", 1e9),
        "trade_pct_gdp": ("Thương mại/GDP", "%", 1),
        "unemployment":  ("Thất nghiệp", "%", 1),
    }
    lines.append("| Chỉ số | Giá trị | Năm | Nguồn |")
    lines.append("|---|---|---|---|")
    for key, (label, unit, divisor) in wb_display.items():
        d = wb.get(key, {})
        if isinstance(d, dict) and d.get("value") is not None:
            val = d["value"] / divisor
            lines.append(f"| {label} | **{val:.1f} {unit}** | {d.get('year','N/A')} | World Bank |")
        else:
            lines.append(f"| {label} | N/A | — | World Bank |")
    lines += ["", "---", ""]

    # ── SJC Vàng VN ─────────────────────────────────────────────────────
    sjc = api_data.get("sjc", {})
    if sjc.get("buy") or sjc.get("sell"):
        lines += ["## 🥇 Giá Vàng SJC Việt Nam", ""]
        lines.append("| Loại | Mua vào | Bán ra | Đơn vị |")
        lines.append("|---|---|---|---|")
        lines.append(f"| SJC 1 lượng | {sjc.get('buy','N/A'):,} | {sjc.get('sell','N/A'):,} | nghìn đồng |")
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
                if src["ok"]:
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

    # Load timestamp lần chạy trước SỚM — cần cho cả WHO lẫn RSS filter
    last_run_utc = load_last_run()
    last_run_ict = last_run_utc + datetime.timedelta(hours=TIMEZONE_OFFSET)

    # Thu thập API
    print("[API] Lấy số liệu thị trường...")
    api_data = {}
    market_cache = load_market_cache()
    vn_now_str = (utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)).strftime("%Y-%m-%d %H:%M ICT")

    print("  [API] Giá vàng/bạc...")
    api_data["gold"] = get_gold_prices()
    if api_data["gold"].get("xau_usd"):
        market_cache["gold"] = {k: api_data["gold"].get(k) for k in
                                ("xau_usd","xag_usd","sjc_vnd","sjc_buy","source")}
        market_cache["gold"]["cached_at"] = vn_now_str
    elif market_cache.get("gold", {}).get("xau_usd"):
        # API lỗi → dùng giá gần nhất từ cache, ghi rõ là giá cũ
        cached = market_cache["gold"]
        api_data["gold"].update({k: cached.get(k) for k in
                                 ("xau_usd","xag_usd","sjc_vnd","sjc_buy")})
        api_data["gold"]["source"] = f"{cached.get('source','?')} (giá gần nhất, lưu {cached.get('cached_at','?')})"
        api_data["gold"]["error"]  = ""   # có giá (cũ) rồi — không cần cảnh báo lỗi nữa
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
        market_cache["vnindex"] = {k: vi.get(k) for k in
                                   ("vnindex","vnindex_change","vnindex_pct",
                                    "hnx","hnx_change","total_value_bn","source")}
        market_cache["vnindex"]["cached_at"] = vn_now_str
    elif market_cache.get("vnindex", {}).get("vnindex"):
        # Thị trường đóng cửa (T7/CN) hoặc API lỗi → trả giá ĐÓNG CỬA PHIÊN
        # GẦN NHẤT từ cache thay vì N/A
        cached  = market_cache["vnindex"]
        is_wknd = (utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET)).weekday() >= 5
        reason  = "thị trường nghỉ cuối tuần" if is_wknd else "API lỗi"
        vi.update({k: cached.get(k) for k in
                   ("vnindex","vnindex_change","vnindex_pct",
                    "hnx","hnx_change","total_value_bn")})
        vi["source"] = f"Đóng cửa phiên gần nhất — {reason} (lưu {cached.get('cached_at','?')})"
        vi["error"]  = ""

    save_market_cache(market_cache)

    print("  [API] WHO Disease Outbreaks...")
    api_data["who_outbreaks"] = get_who_outbreaks(last_run_utc)
    n_who = len([x for x in api_data["who_outbreaks"] if "title" in x])
    print(f"        WHO: {n_who} outbreaks")

    print("  [API] USGS Earthquakes (M>=5.0, 24h)...")
    api_data["earthquakes"] = get_usgs_earthquakes()
    n_eq = len([x for x in api_data["earthquakes"] if "mag" in x])
    print(f"        USGS: {n_eq} earthquakes")

    print("  [API] GDELT Geopolitics...")
    api_data["gdelt"] = get_gdelt_geopolitics()
    n_gd = len([x for x in api_data["gdelt"] if "title" in x])
    print(f"        GDELT: {n_gd} articles")

    print("  [API] World Bank Vietnam...")
    api_data["worldbank_vn"] = get_world_bank_vn()
    wb_keys = [k for k in api_data["worldbank_vn"] if k != "source" and "error" not in str(api_data["worldbank_vn"].get(k))]
    print(f"        WB: {len(wb_keys)} indicators")

    print("  [API] SJC Gold VN...")
    api_data["sjc"] = get_sjc_gold_vn()
    vi = api_data["vnindex"]
    if vi.get("vnindex"):
        chg = vi.get("vnindex_change", 0) or 0
        pct = vi.get("vnindex_pct", 0) or 0
        sign = "+" if chg >= 0 else ""
        print(f"        VNIndex = {vi['vnindex']:.2f} ({sign}{chg:.2f} | {sign}{pct:.2f}%)")
    else:
        print(f"        VNIndex = N/A ({vi.get('error','')})")

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
