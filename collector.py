--- collector_original.py	2026-07-30 11:16:54.457679561 +0000
+++ collector_patched.py	2026-07-30 11:16:28.613269276 +0000
@@ -9,7 +9,7 @@
 """
 
 import time, datetime, gzip, json, zlib, ssl, random
-import urllib.request, urllib.error
+import urllib.request, urllib.error, urllib.parse
 import re, xml.etree.ElementTree as ET
 from pathlib import Path
 
@@ -478,7 +478,7 @@
     try:
         url = "https://iboard-query.ssi.com.vn/v2/stock/index/VNINDEX"
         req = urllib.request.Request(url, headers={
-            "User-Agent": "Mozilla/5.0",
+            **RSS_HEADERS,
             "Accept": "application/json",
             "Origin": "https://iboard.ssi.com.vn",
             "Referer": "https://iboard.ssi.com.vn/",
@@ -524,8 +524,10 @@
     try:
         url3 = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/VNIndex"
         req3 = urllib.request.Request(url3, headers={
-            "User-Agent": "Mozilla/5.0",
+            **RSS_HEADERS,
             "Accept": "application/json",
+            "Origin": "https://tcinvest.tcbs.com.vn",
+            "Referer": "https://tcinvest.tcbs.com.vn/",
         })
         with urllib.request.urlopen(req3, timeout=REQUEST_TIMEOUT) as resp3:
             raw3 = resp3.read()
@@ -542,7 +544,40 @@
     except Exception as e2:
         result["_tcbs_err"] = str(e2)[:80]
 
-    # Nguồn 3: Jina đọc CafeF bảng giá (fallback) — regex có thể bắt nhầm số rác
+    # Nguồn 3: VNDirect dchart (public chart API, thường không chặn IP datacenter
+    # như SSI/TCBS) — lấy nến ngày gần nhất, dùng giá đóng cửa 'c' làm indexValue.
+    try:
+        now_ts = int(time.time())
+        url_dc = ("https://dchart-api.vndirect.com.vn/dchart/history"
+                  f"?resolution=1D&symbol=VNINDEX&from={now_ts-7*86400}&to={now_ts}")
+        req_dc = urllib.request.Request(url_dc, headers={
+            **RSS_HEADERS,
+            "Accept": "application/json",
+            "Origin": "https://dstock.vndirect.com.vn",
+            "Referer": "https://dstock.vndirect.com.vn/",
+        })
+        with urllib.request.urlopen(req_dc, timeout=REQUEST_TIMEOUT) as resp_dc:
+            raw_dc = resp_dc.read()
+        if raw_dc[:2] == b"\x1f\x8b": raw_dc = gzip.decompress(raw_dc)
+        d_dc = json.loads(raw_dc.decode("utf-8", errors="replace"))
+        closes = d_dc.get("c") or []
+        opens  = d_dc.get("o") or []
+        if d_dc.get("s") == "ok" and closes and _vnindex_plausible(closes[-1]):
+            last_close = float(closes[-1])
+            prev_ref   = float(opens[-1]) if opens else last_close
+            result["vnindex"]        = last_close
+            result["vnindex_change"] = round(last_close - prev_ref, 2)
+            result["vnindex_pct"]    = round((last_close - prev_ref) / prev_ref * 100, 2) if prev_ref else 0.0
+            result["source"]         = "VNDirect dchart"
+            return result
+        elif closes:
+            result["_vndirect_err"] = f"Giá trị vô lý bị loại: {closes[-1]}"
+        else:
+            result["_vndirect_err"] = f"Không có dữ liệu (status={d_dc.get('s')})"
+    except Exception as e_dc:
+        result["_vndirect_err"] = str(e_dc)[:80]
+
+    # Nguồn 4: Jina đọc CafeF bảng giá (fallback cuối) — regex có thể bắt nhầm số rác
     # nên BẮT BUỘC qua sanity-check; nguồn này không có change/pct đáng tin cậy
     # nên cố tình để None thay vì mặc định 0 (tránh hiển thị giả "+0.00%").
     try:
@@ -568,8 +603,9 @@
     except Exception as e3:
         result["_jina_err"] = str(e3)[:80]
 
-    debug = " | ".join(f"{k}={result[k]}" for k in ("_ssi_err","_tcbs_err","_jina_err") if k in result)
-    result["error"] = f"Không lấy được VNIndex hợp lệ từ cả 3 nguồn — thị trường đóng cửa hoặc API lỗi. Debug: {debug}"
+    debug = " | ".join(f"{k}={result[k]}" for k in
+                       ("_ssi_err","_tcbs_err","_vndirect_err","_jina_err") if k in result)
+    result["error"] = f"Không lấy được VNIndex hợp lệ từ cả 4 nguồn (SSI/TCBS/VNDirect/CafeF-Jina). Debug: {debug}"
     return result
 
 
@@ -759,7 +795,7 @@
 
     # Washington Post — RSS còn hoạt động
     {"group": 2, "name": "Washington Post World",       "url": "https://feeds.washingtonpost.com/rss/world"},
-    {"group": 3, "name": "Washington Post Business",    "url": "https://feeds.washingtonpost.com/rss/business"},
+    {"group": 3, "name": "Washington Post Business (GNews)", "url": "https://news.google.com/rss/search?q=when:24h+allinurl:washingtonpost.com/business&hl=en-US&gl=US&ceid=US:en"},
 
     # Bloomberg — không có public RSS, dùng Google News RSS về Bloomberg
     {"group": 3, "name": "MarketWatch Top Stories",     "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
@@ -876,23 +912,39 @@
 
 
 def _regex_parse_rss(text: str) -> list:
-    """Parse RSS bằng regex khi XML sai chuẩn nặng (TTXVN...). Best-effort."""
-    items = []
+    """Parse RSS bằng regex khi XML sai chuẩn nặng (TTXVN...). Best-effort.
+    Thử <item> (RSS 2.0) trước; nếu rỗng, thử <entry> (Atom) — một số feed VN
+    (TTXVN/KTTV) đổi định dạng hoặc trả HTML lỗi lẫn Atom tag rời rạc."""
     def _tag(block, name):
         m = re.search(rf'<{name}[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>',
                       block, re.S | re.I)
         return (m.group(1).strip() if m else "")
-    for m in re.finditer(r'<item[\s>].*?</item>', text, re.S | re.I):
-        block   = m.group(0)
-        title   = re.sub(r'<[^>]+>', ' ', _tag(block, "title")).strip()
-        link    = _tag(block, "link")
-        desc    = re.sub(r'<[^>]+>', ' ', _tag(block, "description"))
-        desc    = re.sub(r'\s+', ' ', desc).strip()[:400]
-        pubdate = _tag(block, "pubDate")
-        if title:
-            items.append({"title": title, "link": link,
-                          "summary": desc, "published": pubdate[:50]})
-        if len(items) >= MAX_ITEMS_RSS: break
+
+    def _parse_blocks(tag: str, link_from_attr: bool = False) -> list:
+        found = []
+        for m in re.finditer(rf'<{tag}[\s>].*?</{tag}>', text, re.S | re.I):
+            block = m.group(0)
+            title = re.sub(r'<[^>]+>', ' ', _tag(block, "title")).strip()
+            if link_from_attr:
+                lm = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', block, re.I)
+                link = lm.group(1) if lm else _tag(block, "link")
+            else:
+                link = _tag(block, "link")
+            desc = re.sub(r'<[^>]+>', ' ',
+                          _tag(block, "description") or _tag(block, "summary")
+                          or _tag(block, "content"))
+            desc = re.sub(r'\s+', ' ', desc).strip()[:400]
+            pubdate = (_tag(block, "pubDate") or _tag(block, "published")
+                      or _tag(block, "updated"))
+            if title:
+                found.append({"title": title, "link": link,
+                              "summary": desc, "published": pubdate[:50]})
+            if len(found) >= MAX_ITEMS_RSS: break
+        return found
+
+    items = _parse_blocks("item")
+    if not items:
+        items = _parse_blocks("entry", link_from_attr=True)
     return items
 
 
@@ -927,6 +979,12 @@
     text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
     text = re.sub(r'encoding=["\'][^"\']+["\']', 'encoding="utf-8"', text, count=1)
 
+    head_lower = text[:500].lower()
+    if "<item" not in head_lower and "<entry" not in head_lower and (
+            "<!doctype html" in head_lower or "<html" in head_lower):
+        return [{"error": "Server trả về trang HTML, không phải RSS/XML "
+                           "(có thể do chặn bot hoặc feed URL đã đổi)"}]
+
     try:
         root = ET.fromstring(text.encode("utf-8"))
     except ET.ParseError:
@@ -996,6 +1054,18 @@
     return any(kw in (title+" "+summary).lower() for kw in IMPORTANT_KEYWORDS)
 
 
+def _is_nav_boilerplate(line: str) -> bool:
+    """True nếu dòng trông như menu/nav (nhiều link liên tiếp, không phải văn
+    xuôi) — vd. danh sách 63 tỉnh thành VnExpress, thanh chuyên mục báo VN."""
+    link_count = line.count("](")
+    if link_count >= 3:
+        return True
+    # Dòng toàn các cụm ngắn lặp lại kiểu "[Chọn mặc định]...[Xem]...[Mặc định]"
+    if link_count >= 1 and len(line) / max(link_count, 1) < 25:
+        return True
+    return False
+
+
 def fetch_full_article(url: str) -> str:
     if not url or not url.startswith("http"): return ""
     req = urllib.request.Request(JINA_BASE + url, headers=JINA_HEADERS)
@@ -1004,7 +1074,8 @@
             raw = decompress(resp.read())
             text = raw.decode("utf-8", errors="replace")
         lines = [l.strip() for l in text.split("\n")
-                 if len(l.strip()) > 30 and not l.strip().startswith("http")]
+                 if len(l.strip()) > 30 and not l.strip().startswith("http")
+                 and not _is_nav_boilerplate(l.strip())]
         return "\n".join(lines[:80])[:MAX_CHARS_ARTICLE]
     except:
         return ""
@@ -1057,6 +1128,25 @@
         return []
 
 
+_ARTICLE_URL_REQUIRED = {
+    # domain → regex mà href PHẢI khớp mới được coi là bài viết thật.
+    # Chỉ áp cho domain đã quan sát thấy hay lẫn link menu/nav vào danh sách
+    # headline (White House, PCTT) — domain khác không bị ràng buộc thêm.
+    "whitehouse.gov": re.compile(
+        r"/(briefings-statements|fact-sheets|presidential-actions|remarks)/\d{4}/\d{2}/", re.I),
+    "phongchongthientai.mard.gov.vn": re.compile(
+        r"/Pages/[a-zA-Z0-9\-]{20,}\.aspx", re.I),
+}
+
+
+def _passes_article_url_pattern(href: str) -> bool:
+    """True nếu href không thuộc domain bị ràng buộc, HOẶC khớp pattern bài viết."""
+    for domain, pattern in _ARTICLE_URL_REQUIRED.items():
+        if domain in href:
+            return bool(pattern.search(href))
+    return True
+
+
 def _filter_headline(title: str, href: str, source_url: str, noise: set, seen: set) -> bool:
     """True nếu đây là headline bài viết thật đáng giữ."""
     tl = title.lower()
@@ -1072,9 +1162,28 @@
     # Loại link trỏ về CHÍNH trang danh sách (nav item không có bài riêng)
     if href.rstrip("/") == source_url.rstrip("/"): return False
     if href in seen or title in seen: return False       # dedupe
+    # Domain hay lẫn menu (White House, PCTT): bắt buộc href đúng cấu trúc bài viết
+    if not _passes_article_url_pattern(href): return False
     return True
 
 
+_BLOCKED_PAGE_MARKERS = [
+    "404", "not found", "không tồn tại", "đã bị gỡ",
+    "just a moment", "security verification", "checking your browser",
+    "verify you are human", "enable javascript and cookies",
+    "access denied", "forbidden",
+]
+
+def _blocked_page_marker(text: str) -> str:
+    """Kiểm tra 800 ký tự đầu của nội dung xem có phải trang lỗi/chặn không.
+    Trả về marker khớp được (để log rõ lý do), hoặc '' nếu nội dung có vẻ hợp lệ."""
+    head = text[:800].lower()
+    for marker in _BLOCKED_PAGE_MARKERS:
+        if marker in head:
+            return marker
+    return ""
+
+
 def fetch_jina_content(url: str) -> str:
     """Fetch Jina và trả về danh sách headline dạng '- [tiêu đề](link)'.
     Nếu Jina lỗi (vd. 422) → fallback fetch thẳng HTML gốc để trích link."""
@@ -1084,7 +1193,28 @@
              "trang chủ","liên hệ","sơ đồ","giới thiệu cổng",
              "thư điện tử","văn phòng điện tử","lịch công tác",
              "đặt tạp chí","đặt báo","mua báo","quảng cáo","podcast",
-             "youtube","rss","tải app","app store","google play"}
+             "youtube","rss","tải app","app store","google play",
+             # Nav cố định White House — trùng econ keyword (budget, executive
+             # order) nên hay bị chọn nhầm làm "tin nổi bật" dù chỉ là menu
+             "executive orders","office of management and budget",
+             "council of economic advisors","grow the economy",
+             "unleash american energy","working families tax cut",
+             "major investments in america","election integrity",
+             "save america","ratepayer protection","lab leak",
+             "january 6","arrested: worst of the worst","this is our why",
+             "criminal aliens","briefings & statements","presidential actions",
+             "download the official white house app",
+             # Nav cố định LuatVietnam — lặp lại y hệt ở mọi trang chuyên mục
+             "tính lãi suất","tính thuế thu nhập cá nhân",
+             "tính bảo hiểm xã hội","tính lương gross","tính bảo hiểm thất nghiệp",
+             "đấu thầu-cạnh tranh","giáo dục-đào tạo-dạy nghề",
+             "khoa học-công nghệ","lao động-tiền lương","pháp lý doanh nghiệp",
+             "dịch vụ dịch thuật","dịch vụ nội dung","tổng đài tư vấn",
+             "phiên bản tiếng anh","gói dịch vụ & giá",
+             # Nav cố định VNDMS/PCTT
+             "chú giải","turn on more accessible","turn off more accessible",
+             "sơ đồ tổ chức","chức năng, nhiệm vụ","đơn vị trực thuộc",
+             "ban chỉ huy pctt"}
 
     jina_err = ""
     text = ""
@@ -1093,9 +1223,27 @@
         with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
             raw = decompress(resp.read())
             text = raw.decode("utf-8", errors="replace")
+    except urllib.error.HTTPError as e:
+        if e.code == 422:
+            # 422 thường do URL chưa được encode đúng khi ghép vào r.jina.ai/
+            try:
+                quoted = urllib.parse.quote(url, safe=":/?=&%")
+                req2 = urllib.request.Request(JINA_BASE + quoted, headers=JINA_HEADERS)
+                with urllib.request.urlopen(req2, timeout=REQUEST_TIMEOUT) as resp2:
+                    raw = decompress(resp2.read())
+                    text = raw.decode("utf-8", errors="replace")
+            except Exception as e2:
+                jina_err = f"HTTP 422 (đã thử encode lại URL): {str(e2)[:60]}"
+        else:
+            jina_err = str(e)[:80]
     except Exception as e:
         jina_err = str(e)[:80]
 
+    if text:
+        blocked = _blocked_page_marker(text)
+        if blocked:
+            return f"[Lỗi Jina: trang lỗi/bị chặn — phát hiện '{blocked}' ({url})]"
+
     headline_candidates, seen = [], set()
 
     if text:
@@ -1130,6 +1278,7 @@
             if re.match(r'^https?://\S+$', s): continue
             if re.match(r'^[=\-_*#|]{3,}$', s): continue
             if any(n in s.lower() for n in noise): continue
+            if _is_nav_boilerplate(s): continue
             out.append(s)
         if out:
             return "\n".join(out[:150])[:5000]
@@ -1315,7 +1464,9 @@
         ]
 
     # Ghi chú lỗi API nếu có
-    for key, label in [("gold","Vàng"),("fx","Tỷ giá"),("fed","Fed"),("cpi","CPI"),("jobs","Jobs"),("vnindex","VNIndex")]:
+    # Lưu ý: KHÔNG thêm "vnindex" vào danh sách dưới — khối if/else phía trên
+    # đã tự render cảnh báo VNIndex riêng; thêm lại vào đây sẽ in trùng 2 lần.
+    for key, label in [("gold","Vàng"),("fx","Tỷ giá"),("fed","Fed"),("cpi","CPI"),("jobs","Jobs")]:
         d = api_data.get(key,{})
         if d.get("error"):
             lines.append(f"> ⚠️ {label}: {d['error']}")
