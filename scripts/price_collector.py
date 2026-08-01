"""
T1 — Khung Job B: tải & chọn ngày dữ liệu giá CafeF.

Phạm vi T1 (theo plan SP1): CHỈ tải 4 ZIP của ngày mới nhất có đủ 4/4 họ file
và giải nén vào thư mục tạm. KHÔNG parse nội dung, KHÔNG ghi gì vào repo —
đó là việc của T2 (cache CSV) và T3 (snapshot).

Logic chọn ngày tái dùng nguyên từ spike_cafef.py v2 (đã PASS thật trên
Actions ngày 2026-07-31): gom link theo ngày, thử từ mới nhất, yêu cầu đủ
4 họ file cùng ngày mới coi là hợp lệ.

Output của T1: thư mục ./_raw/{d8}/ chứa 4 file zip đã tải, và biến môi
trường PRICE_DATE (=d8) được ghi ra $GITHUB_ENV để các step/job sau dùng.
"""

import io
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

# 4 họ file mục tiêu (đã xác nhận qua spike v2)
TARGET_FAMILIES = {
    "gia_dieu_chinh": re.compile(r"CafeF\.SolieuGD\.Upto\d{8}\.zip$", re.I),
    "gia_chua_dieu_chinh": re.compile(r"CafeF\.SolieuGD\.Raw\.Upto\d{8}\.zip$", re.I),
    "index": re.compile(r"CafeF\.Index\.Upto\d{8}\.zip$", re.I),
    "cung_cau": re.compile(r"CafeF\.CCNN\.Upto\d{8}\.zip$", re.I),
}

FALLBACK_BASE = "https://cafef1.mediacdn.vn/data/ami_data/{d8}/CafeF.{fam}Upto{d8b}.zip"
FALLBACK_FAMS = {
    "gia_dieu_chinh": "SolieuGD.",
    "gia_chua_dieu_chinh": "SolieuGD.Raw.",
    "index": "Index.",
    "cung_cau": "CCNN.",
}

DATE_IN_URL = re.compile(r"/ami_data/(\d{8})/")
VN_TZ = timezone(timedelta(hours=7))
RAW_DIR = Path("_raw")
MAX_LOOKBACK_DAYS = 6  # đủ phủ 1 kỳ nghỉ lễ dài + cuối tuần


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, binary: bool = False, timeout: int = 120):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.status_code, (r.content if binary else r.text), ""
    except requests.RequestException as e:
        return 0, b"" if binary else "", f"{type(e).__name__}: {e}"


def discover_links_by_date(html: str) -> dict[str, dict[str, str]]:
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


def download_and_validate(fam: str, url: str, dest_dir: Path) -> bool:
    """Tải 1 ZIP, kiểm tra hợp lệ (magic PK + mở được), giải nén vào dest_dir/{fam}/."""
    log(f"    [{fam}] GET {url}")
    status, body, err = fetch(url, binary=True)
    if err:
        log(f"      LỖI mạng: {err}")
        return False
    if status != 200 or len(body) < 1000 or body[:2] != b"PK":
        log(f"      Không hợp lệ (HTTP {status}, {len(body)} bytes)")
        return False
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
        bad = zf.testzip()
        if bad:
            log(f"      ZIP hỏng tại: {bad}")
            return False
    except zipfile.BadZipFile as e:
        log(f"      BadZipFile: {e}")
        return False

    out_dir = dest_dir / fam
    out_dir.mkdir(parents=True, exist_ok=True)
    zf.extractall(out_dir)
    names = zf.namelist()
    log(f"      OK — {len(names)} file giải nén vào {out_dir}/: {names}")
    return True


def try_date(d8: str, fams: dict[str, str], dest_dir: Path) -> bool:
    """Tải đủ 4 họ file của một ngày. True nếu cả 4 đều hợp lệ."""
    ok_count = 0
    for fam in sorted(TARGET_FAMILIES):
        url = fams.get(fam)
        if not url:
            log(f"    [{fam}] không có link cho ngày {d8}")
            continue
        if download_and_validate(fam, url, dest_dir):
            ok_count += 1
    log(f"    => {ok_count}/4 họ file hợp lệ cho ngày {d8}")
    return ok_count == 4


def main() -> int:
    now_vn = datetime.now(VN_TZ)
    log(f"=== JOB B — Tải giá CafeF === {now_vn:%Y-%m-%d %H:%M} (giờ VN)")

    if RAW_DIR.exists():
        import shutil
        shutil.rmtree(RAW_DIR)

    # Bước 1: thử qua trang download
    log(f"\n[1] GET trang download: {DOWNLOAD_PAGE}")
    status, html, err = fetch(DOWNLOAD_PAGE)
    by_date = discover_links_by_date(html) if not err and status == 200 else {}
    dates_desc = sorted(by_date.keys(), reverse=True)
    log(f"    Các ngày tìm thấy (mới → cũ): {dates_desc}")

    chosen_date = None
    for d8 in dates_desc:
        dest = RAW_DIR / d8
        log(f"\n[2] Thử ngày {d8} (qua link trang):")
        if try_date(d8, by_date[d8], dest):
            chosen_date = d8
            break
        log(f"    Ngày {d8} không đủ 4/4 — xóa thư mục tạm, lùi ngày kế.")
        import shutil
        shutil.rmtree(dest, ignore_errors=True)

    # Bước 2: fallback pattern URL nếu trang không dùng được / không ngày nào đủ
    if not chosen_date:
        log("\n[3] Fallback pattern URL lịch sử:")
        for back in range(0, MAX_LOOKBACK_DAYS):
            d = now_vn - timedelta(days=back)
            d8, d8b = d.strftime("%Y%m%d"), d.strftime("%d%m%Y")
            fams = {fam: FALLBACK_BASE.format(d8=d8, fam=pre, d8b=d8b)
                    for fam, pre in FALLBACK_FAMS.items()}
            dest = RAW_DIR / d8
            log(f"    Thử ngày {d8}:")
            if try_date(d8, fams, dest):
                chosen_date = d8
                break
            import shutil
            shutil.rmtree(dest, ignore_errors=True)

    log("\n" + "=" * 60)
    if not chosen_date:
        log("KẾT QUẢ: FAIL ❌ — không tìm được ngày nào đủ 4/4 file trong "
            f"{MAX_LOOKBACK_DAYS} ngày gần nhất.")
        log("Actions sẽ đỏ có kiểm soát — không có gì bị ghi vào repo.")
        return 1

    log(f"KẾT QUẢ: PASS ✅ — đã tải đủ dữ liệu ngày {chosen_date} vào {RAW_DIR/chosen_date}/")
    # Ghi ra GITHUB_ENV để step sau (và T2 sau này) dùng lại
    gh_env = os.environ.get("GITHUB_ENV")
    if gh_env:
        with open(gh_env, "a") as f:
            f.write(f"PRICE_DATE={chosen_date}\n")
        log(f"Đã ghi PRICE_DATE={chosen_date} vào GITHUB_ENV")
    else:
        log(f"(Chạy local — không có GITHUB_ENV. PRICE_DATE={chosen_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
