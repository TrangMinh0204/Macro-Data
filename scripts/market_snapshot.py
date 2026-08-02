"""
T3 — Sinh output/market-snapshot.md (Lop 1: snapshot thi truong).

Hai nguon du lieu khac nhau:
  (a) Breadth toan thi truong (so ma tang/giam/dung, top KL, tong KL/GT):
      quet TRUC TIEP file tho _raw/{PRICE_DATE}/gia_dieu_chinh/*.csv — vi
      can toan bo ~1700+ ma HOSE/HNX/UPCOM, khong chi 60 ma da cache.
  (b) VNINDEX/HNX-INDEX/VN30(xap xi)/rổ Vingroup: doc lai data/prices/*.csv
      ma T2 (buoc truoc, cung job) vua ghi — khong doc lai file tho.

An toan thu tu file: KHONG gia dinh file sap xep theo ma; voi moi ma chi
giu toi da 2 dong moi nhat bang so sanh ngay, dung bat ke thu tu goc.

Buoc nay CHI chay neu buoc T2 (Parse va cache CSV) da PASS — dat trong
workflow SAU buoc T2 va KHONG dung if:always(), de tu dong bi skip neu T2
fail, tranh tron ngay cu/moi trong cung 1 snapshot.
"""

import csv
import os
import sys
from pathlib import Path

RAW_DIR = Path("_raw")
PRICES_DIR = Path("data/prices")
OUT_FILE = Path("output/market-snapshot.md")

VN30_TICKERS = [
    "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
    "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
    "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE",
]
VINGROUP_TICKERS = ["VIC", "VHM", "VRE", "VPL"]
DIVERGENCE_THRESHOLD_PCT = 0.3  # canh bao phan ky khi lech dau va >= nguong nay


def log(msg: str) -> None:
    print(msg, flush=True)


def d8_to_iso(d8: str) -> str:
    return f"{d8[0:4]}-{d8[4:6]}-{d8[6:8]}" if len(d8) == 8 else d8


def scan_breadth(files_by_exchange: dict[str, Path], target_date_iso: str):
    """
    Quet moi file, giu toi da 2 dong moi nhat/ma (theo ngay, khong theo thu
    tu dong trong file). Tra ve breadth theo san + danh sach (san,ma,ngay,
    close,volume) cua dong moi nhat moi ma de tinh top KL / tong KL-GT.
    """
    breadth = {}
    latest_rows = []  # (exchange, ticker, date_iso, close, volume)

    for ex, fp in files_by_exchange.items():
        if not fp.exists():
            log(f"  CANH BAO: khong thay file {ex}: {fp}")
            continue
        top2: dict[str, list[tuple]] = {}
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 7:
                    continue
                ticker = row[0].strip().upper()
                date8 = row[1]
                rec = top2.setdefault(ticker, [])
                rec.append((date8, row[5], row[6]))  # date8, close, volume
                if len(rec) > 2:
                    rec.sort(key=lambda r: r[0], reverse=True)
                    del rec[2:]

        up = down = flat = 0
        for ticker, rows in top2.items():
            rows.sort(key=lambda r: r[0], reverse=True)
            d0_iso = d8_to_iso(rows[0][0])
            try:
                c0 = float(rows[0][1])
                v0 = float(rows[0][2])
            except ValueError:
                continue
            if d0_iso == target_date_iso:
                latest_rows.append((ex, ticker, d0_iso, c0, v0))
            if len(rows) >= 2:
                try:
                    c_prev = float(rows[1][1])
                except ValueError:
                    continue
                if d0_iso != target_date_iso:
                    continue  # ma khong giao dich phien nay -> khong tinh breadth
                if c0 > c_prev:
                    up += 1
                elif c0 < c_prev:
                    down += 1
                else:
                    flat += 1
        breadth[ex] = {"up": up, "down": down, "flat": flat, "total_scanned": len(top2)}
        log(f"  {ex}: quet {len(top2)} ma, tang {up} / giam {down} / dung {flat}")

    return breadth, latest_rows


def read_index_series(ticker_file: str) -> list[tuple[str, str, str, str, str, str]]:
    """Doc data/prices/{file}.csv da duoc T2 ghi, tra ve list (date,o,h,l,c,v)."""
    fp = PRICES_DIR / ticker_file
    if not fp.exists():
        return []
    rows = []
    with fp.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 6:
                rows.append(tuple(row[:6]))
    return rows


def pct_change(rows: list[tuple]) -> tuple[str, float, float] | None:
    """rows da sap theo ngay tang dan (dung dinh dang T2 ghi). Tra ve (ngay, close, %Δ)."""
    if len(rows) < 2:
        return None
    last, prev = rows[-1], rows[-2]
    try:
        c_last, c_prev = float(last[4]), float(prev[4])
    except (ValueError, IndexError):
        return None
    if c_prev == 0:
        return None
    chg = (c_last - c_prev) / c_prev * 100
    return last[0], c_last, chg


def basket_avg_change(tickers: list[str]) -> tuple[float, dict[str, float]]:
    changes = {}
    for t in tickers:
        rows = read_index_series(f"{t}.csv")
        r = pct_change(rows)
        if r:
            changes[t] = r[2]
    avg = sum(changes.values()) / len(changes) if changes else 0.0
    return avg, changes


def main() -> int:
    price_date = os.environ.get("PRICE_DATE")
    if not price_date:
        log("LOI: khong co PRICE_DATE.")
        return 1
    price_date_iso = d8_to_iso(price_date)
    log(f"=== T3 — Sinh market snapshot === ngay: {price_date_iso}")

    adj_dir = RAW_DIR / price_date / "gia_dieu_chinh"
    files_by_exchange = {}
    for ex, needle in (("HOSE", "HSX"), ("HNX", "HNX"), ("UPCOM", "UPCOM")):
        matches = list(adj_dir.glob(f"CafeF.{needle}.Upto*.csv"))
        if matches:
            files_by_exchange[ex] = matches[0]

    if not files_by_exchange:
        log("LOI: khong tim thay file gia tho (buoc T1 chua chay hoac da bi don dep).")
        return 1

    log("Dang quet breadth toan thi truong...")
    breadth, latest_rows = scan_breadth(files_by_exchange, price_date_iso)

    # Top 10 KL HOSE + tong KL/GT toan thi truong (chi tinh dong dung phien muc tieu)
    hose_rows = [r for r in latest_rows if r[0] == "HOSE"]
    top10_vol = sorted(hose_rows, key=lambda r: r[4], reverse=True)[:10]
    total_volume = sum(r[4] for r in latest_rows)
    total_value = sum(r[3] * r[4] for r in latest_rows)  # don vi: (nghin dong) x co phieu

    # VNINDEX / HNX-INDEX (doc tu data/prices/, da duoc T2 ghi cung job)
    vnindex_rows = read_index_series("VNINDEX.csv")
    hnx_rows = read_index_series("HNXINDEX.csv")
    vnindex_chg = pct_change(vnindex_rows)
    hnx_chg = pct_change(hnx_rows)

    # VN30 xap xi (trung binh gian don — KHONG phai gia tri index that vi
    # thieu trong so free-float; file Index CafeF khong co dong VN30-INDEX rieng)
    vn30_avg_chg, vn30_detail = basket_avg_change(VN30_TICKERS)

    # Ro Vingroup + co phan ky so voi VNINDEX
    vin_avg_chg, vin_detail = basket_avg_change(VINGROUP_TICKERS)
    divergence_flag = False
    if vnindex_chg:
        vni_chg_val = vnindex_chg[2]
        same_sign = (vin_avg_chg >= 0) == (vni_chg_val >= 0)
        if not same_sign and abs(vin_avg_chg - vni_chg_val) >= DIVERGENCE_THRESHOLD_PCT:
            divergence_flag = True

    # ---- Ghi output/market-snapshot.md ----
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("---")
    lines.append(f"ngay_du_lieu: {price_date_iso}")
    lines.append(f"nguon: gia_dieu_chinh=OK, index=OK")
    lines.append("---")
    lines.append("")
    lines.append(f"# Market Snapshot — {price_date_iso}")
    lines.append("")

    if vnindex_chg:
        d, c, chg = vnindex_chg
        lines.append(f"**VNINDEX**: {c:,.2f} ({chg:+.2f}%)")
    else:
        lines.append("**VNINDEX**: (chua co du lieu)")

    if hnx_chg:
        d, c, chg = hnx_chg
        lines.append(f"**HNX-INDEX**: {c:,.2f} ({chg:+.2f}%)")

    lines.append(f"**VN30 (xap xi, TB gian don 30 ma, KHONG phai index chinh thuc "
                 f"vi thieu trong so free-float)**: {vn30_avg_chg:+.2f}%")
    lines.append("")

    lines.append("## Do rong thi truong (ma tang/giam/dung)")
    for ex in ("HOSE", "HNX", "UPCOM"):
        b = breadth.get(ex)
        if b:
            lines.append(f"- {ex}: tang {b['up']} / giam {b['down']} / dung {b['flat']} "
                         f"(quet {b['total_scanned']} ma)")
    lines.append("")

    lines.append("## Top 10 khoi luong HOSE")
    for ex, ticker, d, c, v in top10_vol:
        lines.append(f"- {ticker}: {v:,.0f} cp, gia {c:,.2f}")
    lines.append("")

    lines.append(f"## Tong khoi luong / gia tri toan thi truong")
    lines.append(f"- Tong KL: {total_volume:,.0f} cp")
    lines.append(f"- Tong GT (uoc tinh, don vi nghin dong x cp): {total_value:,.0f}")
    lines.append("")

    lines.append("## Ro Vingroup (VIC, VHM, VRE, VPL) — theo doi song song VNINDEX")
    for t in VINGROUP_TICKERS:
        if t in vin_detail:
            lines.append(f"- {t}: {vin_detail[t]:+.2f}%")
        else:
            lines.append(f"- {t}: (chua co du lieu)")
    lines.append(f"- Trung binh gian don ro Vin: {vin_avg_chg:+.2f}%")
    if divergence_flag:
        lines.append(f"- ⚠️ CO PHAN KY: ro Vin va VNINDEX nguoc chieu nhau "
                     f"(lech {abs(vin_avg_chg - vnindex_chg[2]):.2f}pp) — kiem tra "
                     f"kha nang 'xanh vo do long'.")
    else:
        lines.append("- Khong co phan ky dang chu y voi VNINDEX.")

    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"\nKET QUA: PASS ✅ — da ghi {OUT_FILE} ({OUT_FILE.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
