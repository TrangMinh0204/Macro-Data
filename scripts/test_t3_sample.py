"""
Script TEST-ONLY — xem thu hinh hai output T3, dung du lieu THAT cua CafeF
(khong bia so), nhung KHONG dung validator nghiem ngat cua parse_prices.py
va KHONG ghi/commit bat cu gi vao data/prices/ that.

Cach hoat dong: goi lai truc tiep cac ham tai su dung duoc trong
parse_prices.py va market_snapshot.py (khong sua, khong copy lai logic),
nhung ghi ket qua ra /tmp/test_prices/ thay vi data/prices/, roi in noi
dung market-snapshot mau ra log de xem truoc.

KHONG dung ket qua nay cho phan tich that — index co the le 1 ngay so voi
gia co phieu (dung y nhu vay de test T3 co chay dung khong).
"""

import os
import sys
from pathlib import Path
import shutil

sys.path.insert(0, "scripts")
import parse_prices as p2  # noqa: E402
import market_snapshot as p3  # noqa: E402

TEST_DIR = Path("/tmp/test_prices")


def main() -> int:
    price_date = os.environ.get("PRICE_DATE")
    if not price_date:
        print("LOI: khong co PRICE_DATE (chay buoc T1 truoc).")
        return 1

    print("=" * 70)
    print("CHE DO TEST T3 — KHONG DUNG CHO PRODUCTION, KHONG COMMIT GI CA")
    print("Dung du lieu THAT tu CafeF (khong bia so). Neu file Index dang")
    print("le 1 ngay so voi file gia, phan VNINDEX/HNX-INDEX ben duoi se")
    print("hien dung ngay THAT ma CafeF dang co — chi de xem hinh hai T3.")
    print("=" * 70)

    universe = p2.load_universe()
    adj_files = p2.find_family_files(price_date, "gia_dieu_chinh", "CafeF.*.csv")
    raw_files = p2.find_family_files(price_date, "gia_chua_dieu_chinh", "CafeF.RAW_*.csv")
    idx_files = p2.find_family_files(price_date, "index", "CafeF.INDEX.*.csv")

    if not adj_files:
        print("LOI: khong thay file gia tho — chay buoc T1 (price_collector.py) truoc.")
        return 1

    print(f"\nDang parse {len(universe)} ma (khong kiem tra ngay index — day la TEST)...")
    adj_data = p2.scan_price_family(adj_files, universe)
    raw_data = p2.scan_price_family(raw_files, universe)
    idx_data = p2.scan_index_family(idx_files)

    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True)

    for ticker, rows in adj_data.items():
        raw_rows = raw_data.get(ticker, [])
        raw_close_by_date = {r[0]: r[4] for r in raw_rows}
        p2.write_price_csv(TEST_DIR / f"{p2.safe_filename(ticker)}.csv", rows, raw_close_by_date)

    for ticker, rows in idx_data.items():
        p2.write_index_csv(TEST_DIR / f"{p2.safe_filename(ticker)}.csv", rows)

    print(f"Da ghi {len(adj_data)} file gia + {len(idx_data)} file chi so vao {TEST_DIR}/ (TAM, khong phai data/prices that)")

    # Tro T3 vao thu muc test — RAW_DIR (breadth) van la _raw that, khong doi
    p3.PRICES_DIR = TEST_DIR
    p3.OUT_FILE = TEST_DIR / "market-snapshot-SAMPLE.md"

    print("\nDang chay T3 (market_snapshot.main) tren du lieu test...")
    ret = p3.main()

    vnindex_rows = p3.read_index_series("VNINDEX.csv")
    actual_index_date = vnindex_rows[-1][0] if vnindex_rows else "(khong co)"

    print("\n" + "=" * 70)
    print(f"LUU Y: VNINDEX/HNX-INDEX ben duoi la so THAT gan nhat CafeF dang co,")
    print(f"ngay thuc te = {actual_index_date} — co the KHONG trung voi ngay gia")
    print(f"co phieu ({p2.d8_to_iso(price_date)}) neu file Index dang cham hon.")
    print("Day la du lieu THAT, khong phai so uoc tinh/bia.")
    print("=" * 70)
    print("\nNOI DUNG MAU market-snapshot.md:\n")
    print(p3.OUT_FILE.read_text(encoding="utf-8"))
    print("=" * 70)
    print("(File nay chi nam trong /tmp cua runner, se mat khi job ket thuc.")
    print(" KHONG co gi duoc commit vao repo tu script test nay.)")

    return 0  # test script luon exit 0 — chi de XEM, khong dai dien PASS/FAIL that


if __name__ == "__main__":
    sys.exit(main())
