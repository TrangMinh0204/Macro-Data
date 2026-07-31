"""
Spike test: xác nhận GitHub Actions tải được file ZIP dữ liệu CafeF.

Kiểm tra 4 điều:
  1. Actions truy cập được trang download cafef.vn (không bị chặn IP)
  2. Tìm được link ZIP "Số liệu GD (Upto)" và "Số liệu cung cầu (Upto)"
  3. Tải và giải nén được ZIP
  4. Nội dung hợp lệ: có VNINDEX, đếm được số dòng/số mã

Chỉ đọc và in log — KHÔNG ghi file nào vào repo.
Exit 0 = spike PASS (đi thẳng SP1). Exit 1 = spike FAIL (kích hoạt nhánh Worker proxy).
"""

import io
import re
import sys
import zipfile
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

# Pattern URL lịch sử — đường dự phòng nếu không parse được trang
# {d8} = YYYYMMDD (thư mục), {d8b} = DDMMYYYY (tên file)
FALLBACK_PATTERNS = [
    "https://cafef1.mediacdn.vn/data/ami_data/{d8}/CafeF.SolieuGD.Upto{d8b}.zip",
    "https://cafef1.mediacdn.vn/data/ami_data/{d8}/CafeF.Index.Upto{d8b}.zip",
    "https://cafef1.mediacdn.vn/data/ami_data/{d8}/CafeF.CungCau.Upto{d8b}.zip",
]

VN_TZ = timezone(timedelta(hours=7))


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, binary: bool = False, timeout: int = 60):
    """GET một URL, trả (status_code, content|text, err_note)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        body = r.content if binary else r.text
        return r.status_code, body, ""
    except requests.RequestException as e:
        return 0, b"" if binary else "", f"{type(e).__name__}: {e}"


def discover_zip_links(html: str) -> list[str]:
    """Trích mọi href .zip trên trang download, ưu tiên link có Upto/SolieuGD/CungCau."""
    links = re.findall(r'href=["\']([^"\']+\.zip)["\']', html, flags=re.IGNORECASE)
    # Chuẩn hóa link tương đối
    norm = []
    for u in links:
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://cafef.vn" + u
        norm.append(u)
    # Ưu tiên các file mục tiêu, loại trùng, giữ thứ tự
    seen, ordered = set(), []
    keywords = ("upto", "solieugd", "cungcau", "index")
    for u in sorted(norm, key=lambda x: (not any(k in x.lower() for k in keywords), x)):
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def try_zip(url: str) -> bool:
    """Tải 1 ZIP, giải nén trong RAM, kiểm tra nội dung. True nếu hợp lệ."""
    log(f"\n--- Thử tải: {url}")
    status, body, err = fetch(url, binary=True, timeout=120)
    if err:
        log(f"    LỖI mạng: {err}")
        return False
    log(f"    HTTP {status} | {len(body):,} bytes")
    if status != 200 or len(body) < 10_000:
        preview = body[:200].decode("utf-8", errors="replace") if body else ""
        log(f"    Không phải ZIP hợp lệ. Preview: {preview!r}")
        return False
    if not body[:2] == b"PK":
        log("    Body không có magic 'PK' — không phải ZIP.")
        return False
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as e:
        log(f"    BadZipFile: {e}")
        return False
    names = zf.namelist()
    log(f"    ZIP OK — {len(names)} file bên trong: {names[:5]}")
    ok_any = False
    for name in names[:3]:  # đọc tối đa 3 file đầu
        raw = zf.read(name)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        log(f"    > {name}: {len(raw):,} bytes, {len(lines):,} dòng")
        for ln in lines[:3]:
            log(f"      | {ln[:160]}")
        has_vnindex = "VNINDEX" in text.upper()
        log(f"      VNINDEX xuất hiện: {has_vnindex}")
        # Đếm sơ bộ số mã (cột đầu mỗi dòng CSV)
        tickers = {ln.split(",")[0].strip().upper() for ln in lines[1:5000] if "," in ln}
        log(f"      Số mã (mẫu 5000 dòng đầu): ~{len(tickers)}")
        if len(lines) > 100:
            ok_any = True
    return ok_any


def main() -> int:
    now_vn = datetime.now(VN_TZ)
    log(f"=== SPIKE TEST CAFEF === {now_vn:%Y-%m-%d %H:%M} (giờ VN)")

    passed_urls: list[str] = []

    # Bước 1: trang download
    log(f"\n[1] GET trang download: {DOWNLOAD_PAGE}")
    status, html, err = fetch(DOWNLOAD_PAGE)
    if err:
        log(f"    LỖI mạng: {err}")
        html = ""
    else:
        log(f"    HTTP {status} | {len(html):,} ký tự")

    # Bước 2: khám phá link từ trang
    zip_links = discover_zip_links(html) if html else []
    log(f"\n[2] Link .zip tìm thấy trên trang: {len(zip_links)}")
    for u in zip_links[:10]:
        log(f"    - {u}")

    for u in zip_links[:4]:
        if try_zip(u):
            passed_urls.append(u)

    # Bước 3: fallback pattern lịch sử (lùi tối đa 5 ngày)
    if not passed_urls:
        log("\n[3] Không có link nào từ trang chạy được — thử pattern URL lịch sử:")
        for back in range(0, 6):
            d = now_vn - timedelta(days=back)
            for pat in FALLBACK_PATTERNS:
                url = pat.format(d8=d.strftime("%Y%m%d"), d8b=d.strftime("%d%m%Y"))
                if try_zip(url):
                    passed_urls.append(url)
            if passed_urls:
                break

    # Kết luận
    log("\n" + "=" * 60)
    if passed_urls:
        log("KẾT QUẢ: PASS ✅ — GitHub Actions tải & parse được ZIP CafeF.")
        log("URL dùng được cho Job B:")
        for u in passed_urls:
            log(f"  {u}")
        log("=> Đi thẳng SP1, KHÔNG cần Cloudflare Worker.")
        return 0
    log("KẾT QUẢ: FAIL ❌ — không tải được ZIP nào từ Actions runner.")
    log("=> Kích hoạt nhánh dự phòng: Cloudflare Worker proxy (mục 10 design doc).")
    log("   Dán TOÀN BỘ log này về chat để Claude chẩn đoán nguyên nhân cụ thể.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
