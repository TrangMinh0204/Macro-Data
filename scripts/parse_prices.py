"""
T2 — Parse & cache CSV (Lop 3).

Doc 4 file da tai o T1 (nam trong _raw/{PRICE_DATE}/{ho_file}/), loc ra
cac ma can cache (VN30 + HNX30 tu config/tickers.yml, cong watchlist doc
dong tu state/state.md), ghi moi ma thanh data/prices/{MA}.csv.

Nguyen tac an toan: ghi ra thu muc _stage_prices/ truoc, chi copy de vao
data/prices/ SAU KHI qua validator cung. Neu validator fail, data/prices/
khong bi dung toi -> khong bao gio ghi de cache tot bang du lieu hong.

File index (VNINDEX, HNX-INDEX, ...) luon duoc bat, khong phu thuoc
watchlist/tickers.yml.
"""

import csv
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import yaml

RAW_DIR = Path("_raw")
STAGE_DIR = Path("_stage_prices")
FINAL_DIR = Path("data/prices")
TICKERS_CFG = Path("config/tickers.yml")
STATE_FILE = Path("state/state.md")

COVERAGE_MIN = 0.90  # nguong hard-fail neu ty le cache thanh cong duoi muc nay


def log(msg: str) -> None:
    print(msg, flush=True)


def load_universe() -> set[str]:
    """VN30 + HNX30 (config/tickers.yml) + watchlist (state/state.md muc 5)."""
    universe: set[str] = set()

    if TICKERS_CFG.exists():
        cfg = yaml.safe_load(TICKERS_CFG.read_text(encoding="utf-8")) or {}
        for key in ("vn30", "hnx30"):
            for t in cfg.get(key, []) or []:
                universe.add(str(t).strip().upper())
    else:
        log(f"  CANH BAO: khong thay {TICKERS_CFG}, chi dung watchlist (neu co).")

    if STATE_FILE.exists():
        text = STATE_FILE.read_text(encoding="utf-8")
        m = re.search(r"##\s*5\.\s*Watchlist.*?\n(.*?)(?=\n##\s|\Z)", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                line = line.strip()
                tok = re.match(r"-\s*([A-Z0-9]{3,5})\b", line)
                if tok:
                    universe.add(tok.group(1))
    else:
        log(f"  CANH BAO: khong thay {STATE_FILE}, bo qua watchlist.")

    return universe


def find_family_files(price_date: str, family: str, prefix_glob: str) -> list[Path]:
    d = RAW_DIR / price_date / family
    if not d.exists():
        return []
    return sorted(d.glob(prefix_glob))


def scan_price_family(files: list[Path], wanted: set[str]) -> dict[str, list[tuple[str, str, str, str, str, str]]]:
    """
    Doc tap file (HSX/HNX/UPCOM cua 1 ho: adjusted HOAC raw), gom moi dong
    thuoc ma trong `wanted` vao dict ticker -> list (date8, open, high, low, close, volume).
    Mot lan quet toan bo file (moi file ~1-1.5 trieu dong) — set membership O(1).
    """
    out: dict[str, list[tuple[str, str, str, str, str, str]]] = defaultdict(list)
    for fp in files:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # bo header
            for row in reader:
                if len(row) < 7:
                    continue
                ticker = row[0].strip().upper()
                if ticker not in wanted:
                    continue
                date8, o, h, l, c, v = row[1], row[2], row[3], row[4], row[5], row[6]
                out[ticker].append((date8, o, h, l, c, v))
    return out


def scan_index_family(files: list[Path]) -> dict[str, list[tuple[str, str, str, str, str, str]]]:
    """Nhu tren nhung bat MOI ticker chua 'INDEX' trong ten, khong loc theo wanted."""
    out: dict[str, list[tuple[str, str, str, str, str, str]]] = defaultdict(list)
    for fp in files:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 7:
                    continue
                ticker = row[0].strip().upper()
                if "INDEX" not in ticker:
                    continue
                date8, o, h, l, c, v = row[1], row[2], row[3], row[4], row[5], row[6]
                out[ticker].append((date8, o, h, l, c, v))
    return out


def d8_to_iso(d8: str) -> str:
    return f"{d8[0:4]}-{d8[4:6]}-{d8[6:8]}" if len(d8) == 8 else d8


def write_price_csv(path: Path, adj_rows: list[tuple], raw_close_by_date: dict[str, str]) -> str | None:
    """Ghi 1 file CSV ma co phieu: date,open,high,low,close,volume,close_raw. Tra ve ngay cuoi (iso) hoac None."""
    if not adj_rows:
        return None
    adj_rows = sorted(adj_rows, key=lambda r: r[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume", "close_raw"])
        for date8, o, h, l, c, v in adj_rows:
            close_raw = raw_close_by_date.get(date8, "")
            w.writerow([d8_to_iso(date8), o, h, l, c, v, close_raw])
    return d8_to_iso(adj_rows[-1][0])


def write_index_csv(path: Path, rows: list[tuple]) -> str | None:
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for date8, o, h, l, c, v in rows:
            w.writerow([d8_to_iso(date8), o, h, l, c, v])
    return d8_to_iso(rows[-1][0])


def safe_filename(ticker: str) -> str:
    return ticker.replace("-", "")


def main() -> int:
    price_date = os.environ.get("PRICE_DATE")
    if not price_date:
        log("LOI: khong co bien PRICE_DATE (buoc T1 chua chay hoac chua ghi env).")
        return 1

    log(f"=== T2 — Parse & cache gia === ngay du lieu: {price_date}")

    universe = load_universe()
    log(f"  Tong so ma can cache (VN30+HNX30+watchlist): {len(universe)}")

    adj_files = find_family_files(price_date, "gia_dieu_chinh", "CafeF.*.csv")
    raw_files = find_family_files(price_date, "gia_chua_dieu_chinh", "CafeF.RAW_*.csv")
    idx_files = find_family_files(price_date, "index", "CafeF.INDEX.*.csv")
    log(f"  File gia da dieu chinh: {[f.name for f in adj_files]}")
    log(f"  File gia chua dieu chinh: {[f.name for f in raw_files]}")
    log(f"  File index: {[f.name for f in idx_files]}")

    if not adj_files:
        log("LOI: khong tim thay file gia da dieu chinh — dung lai, khong ghi gi ca.")
        return 1

    log("  Dang quet file gia da dieu chinh...")
    adj_data = scan_price_family(adj_files, universe)
    log(f"    -> tim thay {len(adj_data)}/{len(universe)} ma")

    log("  Dang quet file gia chua dieu chinh...")
    raw_data = scan_price_family(raw_files, universe)

    log("  Dang quet file index...")
    idx_data = scan_index_family(idx_files)
    log(f"    -> tim thay {len(idx_data)} chi so: {sorted(idx_data.keys())}")

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    last_dates: dict[str, str] = {}
    for ticker, rows in adj_data.items():
        raw_rows = raw_data.get(ticker, [])
        raw_close_by_date = {r[0]: r[4] for r in raw_rows}
        d = write_price_csv(STAGE_DIR / f"{safe_filename(ticker)}.csv", rows, raw_close_by_date)
        if d:
            last_dates[ticker] = d

    index_last_dates: dict[str, str] = {}
    for ticker, rows in idx_data.items():
        d = write_index_csv(STAGE_DIR / f"{safe_filename(ticker)}.csv", rows)
        if d:
            index_last_dates[ticker] = d

    # ---- Validator (hard checks truoc khi copy vao data/prices/) ----
    log("\n  --- Validator ---")
    price_date_iso = d8_to_iso(price_date)
    missing = sorted(universe - set(last_dates.keys()))
    stale = sorted(t for t, d in last_dates.items() if d != price_date_iso)
    fresh_count = len(last_dates) - len(stale)
    coverage = fresh_count / len(universe) if universe else 0.0

    log(f"  Ma khong tim thay (co the sai san/da huy niem yet): {missing[:20]}"
        + (f" ... (+{len(missing)-20})" if len(missing) > 20 else ""))
    log(f"  Ma co du lieu nhung KHONG phai phien {price_date_iso} (co the tam ngung GD): {stale}")
    log(f"  Coverage (ma dung ngay/{len(universe)}): {coverage:.1%}")

    vnindex_date = index_last_dates.get("VNINDEX")
    log(f"  VNINDEX ngay cuoi: {vnindex_date}")

    hard_fail = False
    if not vnindex_date:
        log("  HARD FAIL: khong tim thay VNINDEX trong file index.")
        hard_fail = True
    elif vnindex_date != price_date_iso:
        log(f"  HARD FAIL: VNINDEX ngay cuoi ({vnindex_date}) != ngay du lieu ({price_date_iso}).")
        hard_fail = True
    if coverage < COVERAGE_MIN:
        log(f"  HARD FAIL: coverage {coverage:.1%} < nguong {COVERAGE_MIN:.0%}.")
        hard_fail = True

    if hard_fail:
        log("\nKET QUA: FAIL ❌ — data/prices/ KHONG bi dung toi, cache cu van con nguyen.")
        return 1

    # ---- Copy staging -> final (chi ghi de file thanh cong lan nay) ----
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fp in STAGE_DIR.glob("*.csv"):
        shutil.copy(fp, FINAL_DIR / fp.name)
        copied += 1

    log(f"\nKET QUA: PASS ✅ — da cache {copied} file (co phieu + chi so) vao {FINAL_DIR}/")
    log(f"  VNINDEX: {vnindex_date} | Coverage co phieu: {coverage:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
