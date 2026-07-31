"""
Spike test v2: xác nhận GitHub Actions tải được ZIP CafeF NGÀY MỚI NHẤT.

Sửa so với v1: v1 sắp link theo chữ cái (tăng dần) nên luôn dính ngày cũ nhất.
v2 trích ngày từ URL, gom link theo ngày, thử từ ngày MỚI NHẤT lùi dần,
và nhắm đúng 4 họ file mục tiêu của Job B:
  - SolieuGD.Upto      (giá ĐÃ điều chỉnh, 3 sàn)
  - SolieuGD.Raw.Upto  (giá CHƯA điều chỉnh, 3 sàn)
  - Index.Upto         (chỉ số)
  - CCNN.Upto          (cung cầu + khối ngoại theo sàn)

Chỉ đọc và in log — KHÔNG ghi file vào repo.
Exit 0 = PASS. Exit 1 = FAIL.
"""

import io
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

DOWNLOAD_PAGE = "https://cafef.vn/du-lieu/du-lieu-download.chn"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/zip,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer": "https://cafef.vn/",
}

# 4 họ file mục tiêu — khớp bằng regex trên TÊN FILE trong URL
TARGET_FAMILIES = {
    "gia_dieu_chinh": re.compile(r"CafeF\.SolieuGD\.Upto\d{8}\.zip$", re.I),
    "gia_chua_dieu_chinh": re.compile(r"CafeF\.SolieuGD\.Raw\.Upto\d{8}\.zip$", re.I),
    "index": re.compile(r"CafeF\.Index\.Upto\d{8}\.zip$", re.I),
    "cung_cau": re.compile(r"CafeF\.CCNN\.Upto\d{8}\.zip$", re.I),
}

# Pattern dự phòng nếu không parse được trang (đã xác nhận từ spike v1)
FALLBACK_BASE = "https://cafef1.mediacdn.vn/data/ami_data/{d8}/CafeF.{fam}Upto{d8b}.zip"
FALLBACK_FAMS = {
    "gia_dieu_chinh": "SolieuGD.",
    "gia_chua_dieu_chinh": "SolieuGD.Raw.",
    "index": "Index.",
    "cung_cau": "CCNN.",
}

DATE_IN_URL = re.compile(r"/ami_data/(\d{8})/")
VN_TZ = timezone(timedelta(hours=7))


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, binary: bool = False, timeout: int = 120):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.status_code, (r.content if binary else r.text), ""
    except requests.RequestException as e:
        return 0, b"" if binary else "", f"{type(e).__name__}: {e}"


def discover_links_by_date(html: str) -> dict[str, dict[str, str]]:
    """Trả về {YYYYMMDD: {family: url}} — chỉ giữ link thuộc 4 họ mục tiêu."""
    links = re.findall(r'href=["\']([^"\']+\.zip)["\']', html, flags=re.IGNORECASE)
    by_date: dict[str, dict[str, str]] = defaultdict(dict)
    for u in links:
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://cafef.vn" + u
        m = DATE_IN_URL.search(u)
        if not m:
            continue
        d8 = m.group(1)
        for fam, pat in TARGET_FAMILIES.items():
            if pat.search(u):
                by_date[d8][fam] = u
    return dict(by_date)


def check_zip(fam: str, url: str) -> bool:
    """Tải ZIP, giải nén trong RAM, in cấu trúc, kiểm tra hợp lệ."""
    log(f"\n--- [{fam}] {url}")
    status, body, err = fetch(url, binary=True)
    if err:
        log(f"    LỖI mạng: {err}")
        return False
    log(f"    HTTP {status} | {len(body):,} bytes")
    if status != 200 or not body[:2] == b"PK":
        log("    Không phải ZIP hợp lệ.")
        return False
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as e:
        log(f"    BadZipFile: {e}")
        return False
    names = zf.namelist()
    log(f"    ZIP OK — {len(names)} file: {names}")
    ok = False
    for name in names[:2]:
        raw = zf.read(name)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        log(f"    > {name}: {len(raw):,} bytes, {len(lines):,} dòng")
        for ln in lines[:2]:
            log(f"      | {ln[:160]}")
        # Ngày dữ liệu mới nhất trong file (cột 2, đếm từ cuối lên cho nhanh)
        last_dates = {ln.split(",")[1] for ln in lines[-200:] if ln.count(",") >= 2}
        if last_dates:
            log(f"      Ngày mới nhất trong file: {max(last_dates)}")
        if len(lines) > 100:
            ok = True
    return ok


def main() -> int:
    now_vn = datetime.now(VN_TZ)
    log(f"=== SPIKE TEST CAFEF v2 === {now_vn:%Y-%m-%d %H:%M} (giờ VN)")

    log(f"\n[1] GET trang download: {DOWNLOAD_PAGE}")
    status, html, err = fetch(DOWNLOAD_PAGE)
    if err:
        log(f"    LỖI mạng: {err}")
        html = ""
    else:
        log(f"    HTTP {status} | {len(html):,} ký tự")

    by_date = discover_links_by_date(html) if html else {}
    dates_desc = sorted(by_date.keys(), reverse=True)
    log(f"\n[2] Các ngày có link trên trang (mới → cũ): {dates_desc}")
    for d in dates_desc:
        log(f"    {d}: {sorted(by_date[d].keys())}")

    # Thử từ ngày MỚI NHẤT, lùi dần; yêu cầu đủ cả 4 họ file cùng một ngày
    for d8 in dates_desc:
        fams = by_date[d8]
        missing = set(TARGET_FAMILIES) - set(fams)
        log(f"\n[3] Thử ngày {d8} — có {len(fams)}/4 họ file"
            + (f", thiếu: {sorted(missing)}" if missing else ""))
        results = {fam: check_zip(fam, url) for fam, url in sorted(fams.items())}
        if all(results.get(f) for f in TARGET_FAMILIES):
            log("\n" + "=" * 60)
            log(f"KẾT QUẢ: PASS ✅ — đủ 4/4 file hợp lệ cho ngày {d8}.")
            log("URL chốt cho Job B:")
            for fam in sorted(fams):
                log(f"  [{fam}] {fams[fam]}")
            log("=> Ngày mới nhất được lấy đúng. Sẵn sàng viết Job B.")
            return 0
        log(f"    Ngày {d8} chưa đủ 4/4 hợp lệ — lùi ngày kế.")

    # Fallback pattern (không parse được trang): thử lùi 5 ngày
    log("\n[4] Fallback pattern URL (trang không parse được):")
    for back in range(0, 6):
        d = now_vn - timedelta(days=back)
        d8, d8b = d.strftime("%Y%m%d"), d.strftime("%d%m%Y")
        urls = {fam: FALLBACK_BASE.format(d8=d8, fam=pre, d8b=d8b)
                for fam, pre in FALLBACK_FAMS.items()}
        results = {fam: check_zip(fam, url) for fam, url in sorted(urls.items())}
        if all(results.values()):
            log("\n" + "=" * 60)
            log(f"KẾT QUẢ: PASS ✅ (qua fallback) — đủ 4/4 file ngày {d8}.")
            return 0

    log("\n" + "=" * 60)
    log("KẾT QUẢ: FAIL ❌ — không gom đủ 4 họ file hợp lệ cho bất kỳ ngày nào.")
    log("Dán TOÀN BỘ log về chat để Claude chẩn đoán.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
