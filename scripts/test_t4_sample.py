"""
Script TEST-ONLY — xem thu hinh hai Price Pack (T4), dung du lieu THAT
cua CafeF, KHONG ghi/commit bat cu gi vao data/packs/ that.

Chi sinh pack cho 3 ma mau, dung khop tieu chi verify da dinh trong ke
hoach SP1: 1 ma VN30 (HPG), 1 ma HNX30 (TNG), va VNINDEX — de doi chieu
tay voi chart that (vi tri/gia cac pivot ZigZag co khop +-1% khong).

Cach hoat dong: goi lai truc tiep ham tu parse_prices.py de dung du lieu
that (khong qua validator), roi goi ham tu price_pack.py (khong sua gi)
voi PRICES_DIR/PACKS_DIR tro sang /tmp — khong dung toi repo that.
"""

import os
import sys
import shutil
from pathlib import Path

sys.path.insert(0, "scripts")
import parse_prices as p2  # noqa: E402
import price_pack as p4  # noqa: E402

TEST_PRICES_DIR = Path("/tmp/test_prices")
TEST_PACKS_DIR = Path("/tmp/test_packs")
SAMPLE_TICKERS = ["HPG", "TNG", "VNINDEX"]  # 1 VN30, 1 HNX30, VNINDEX (dung tieu chi verify SP1)


def main() -> int:
    price_date = os.environ.get("PRICE_DATE")
    if not price_date:
        print("LOI: khong co PRICE_DATE (chay buoc T1 truoc).")
        return 1

    print("=" * 70)
    print("CHE DO TEST T4 — KHONG DUNG CHO PRODUCTION, KHONG COMMIT GI CA")
    print(f"Sinh pack mau cho {SAMPLE_TICKERS} tu du lieu THAT CafeF, de")
    print("doi chieu tay voi chart that (dung tieu chi verify T4 trong ke")
    print("hoach SP1: 1 VN30 + 1 HNX30 + VNINDEX).")
    print("=" * 70)

    universe = p2.load_universe()
    adj_files = p2.find_family_files(price_date, "gia_dieu_chinh", "CafeF.*.csv")
    raw_files = p2.find_family_files(price_date, "gia_chua_dieu_chinh", "CafeF.RAW_*.csv")
    idx_files = p2.find_family_files(price_date, "index", "CafeF.INDEX.*.csv")

    if not adj_files:
        print("LOI: khong thay file gia tho — chay buoc T1 (price_collector.py) truoc.")
        return 1

    print(f"\nDang parse {len(universe)} ma tu du lieu that (khong qua validator — day la TEST)...")
    adj_data = p2.scan_price_family(adj_files, universe)
    raw_data = p2.scan_price_family(raw_files, universe)
    idx_data = p2.scan_index_family(idx_files)

    for d in (TEST_PRICES_DIR, TEST_PACKS_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    for ticker, rows in adj_data.items():
        raw_rows = raw_data.get(ticker, [])
        raw_close_by_date = {r[0]: r[4] for r in raw_rows}
        p2.write_price_csv(TEST_PRICES_DIR / f"{p2.safe_filename(ticker)}.csv", rows, raw_close_by_date)
    for ticker, rows in idx_data.items():
        p2.write_index_csv(TEST_PRICES_DIR / f"{p2.safe_filename(ticker)}.csv", rows)

    print(f"Da ghi {len(adj_data)} file gia + {len(idx_data)} file chi so vao {TEST_PRICES_DIR}/ (TAM)")

    # Phat hien bat thuong O/H/L/C giong het production (T2), de test ca Phuong an 2
    test_anomalies: dict[str, list[str]] = {}
    for ticker, rows in adj_data.items():
        found = p2.detect_ohlc_anomalies(rows)
        if found:
            test_anomalies[ticker] = [f"{d}: {r}" for d, r in found]
    for ticker, rows in idx_data.items():
        found = p2.detect_ohlc_anomalies(rows)
        if found:
            test_anomalies.setdefault(ticker, []).extend(f"{d}: {r}" for d, r in found)
    if test_anomalies:
        print(f"[chan doan] Phat hien bat thuong O/H/L/C o: {sorted(test_anomalies.keys())}")

    # Tro T4 vao thu muc test — khong dung PRICES_DIR/PACKS_DIR that
    p4.PRICES_DIR = TEST_PRICES_DIR
    p4.PACKS_DIR = TEST_PACKS_DIR

    print(f"\nDang sinh pack mau cho: {SAMPLE_TICKERS}\n")
    for ticker in SAMPLE_TICKERS:
        rows = p4.read_series(ticker)
        if not rows or len(rows) < 10:
            print(f"  [{ticker}] BO QUA — khong du du lieu ({len(rows) if rows else 0} phien)")
            continue
        content = p4.build_pack(ticker, rows, test_anomalies.get(ticker))
        out_fp = TEST_PACKS_DIR / f"{ticker}.md"
        out_fp.write_text(content, encoding="utf-8")
        print("=" * 70)
        print(f"PACK MAU: {ticker}  ({out_fp.stat().st_size} bytes)")
        print("=" * 70)
        print(content)

    print("=" * 70)
    print("(File chi nam trong /tmp cua runner, se mat khi job ket thuc.")
    print(" KHONG co gi duoc commit vao repo tu script test nay.)")
    print()
    print("GOI Y KIEM TRA TAY: mo chart that cua 3 ma tren (vi du TradingView/")
    print("CafeF), doi chieu phan 'Swing points (ZigZag)' — vi tri ngay va")
    print("gia dinh/day co khop (+-1%) voi nhung gi nhin thay tren chart khong?")
    print("Day chinh la tieu chi verify quan trong nhat cua T4 theo ke hoach SP1.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
