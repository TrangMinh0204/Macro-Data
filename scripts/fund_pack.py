"""
T4b — Sinh Fundamental Pack tu file BCTC Vietstock (.xlsx) nguoi dung upload.

Nguon: thu muc data/fundamentals/{MA}/ chua file Vietstock (CSTC bat buoc,
KQKD/CDKT tuy chon) — ten file giu nguyen dinh dang Vietstock xuat ra, script
nhan dien loai file theo chuoi CSTC/KQKD/CDKT co trong ten file.

Day la nguon duy nhat cung cap EPS/BVPS/ROE/BCTC ma file gia CafeF khong co —
can cho graham-foundation va cac skill dinh gia. Script CHI tinh lai tu so
Vietstock da cung cap (Graham Number, Earnings Yield, EPS CAGR, PEG) — khong
tu suy doan them gi khac; metric nao khong tim thay trong file thi bo qua
(khong dien so gia).

Kich hoat: GitHub Actions tu chay khi co file moi day vao data/fundamentals/**
(hoac chay tay qua workflow_dispatch). Sinh data/packs/{MA}-fund.md.
"""

import re
import sys
from pathlib import Path

import pandas as pd

FUND_DIR = Path("data/fundamentals")
PACKS_DIR = Path("data/packs")

QUARTER_RE = re.compile(r"^Q(\d)/(\d{4})$")

# (nhan hien thi, [cac chuoi con co the co trong ten chi tieu Vietstock —
#  thu theo thu tu, chuoi cang cu the dat truoc de tranh khop nham dong chung])
CSTC_METRICS = [
    ("EPS_TTM", ["Thu nhập trên mỗi cổ phần", "EPS"]),
    ("BVPS", ["Giá trị sổ sách của cổ phiếu", "BVPS"]),
    ("PE", ["giá thị trường trên thu nhập", "P/E"]),
    ("PB", ["giá thị trường trên giá trị sổ sách", "P/B"]),
    ("Ty_suat_co_tuc", ["Tỷ suất cổ tức"]),
    ("Beta", ["Beta"]),
    ("ROE", ["vốn chủ sở hữu bình quân (ROEA)", "trên vốn chủ sở hữu", "ROE"]),
    ("ROA", ["tổng tài sản bình quân (ROAA)", "trên tổng tài sản", "ROA"]),
    ("NIM_nganhang", ["thu nhập lãi thuần (NIM)", "(NIM)"]),
    ("CIR_nganhang", ["(CIR)"]),
    ("LDR_nganhang", ["(LDR)"]),
]

KQKD_METRICS = [
    ("Doanh_thu", ["Thu nhập lãi thuần", "Doanh thu thuần"]),
    ("LNTT", ["Tổng lợi nhuận trước thuế", "Lợi nhuận kế toán trước thuế", "Lợi nhuận trước thuế"]),
    ("LNST", ["Lợi nhuận sau thuế của cổ đông", "Lợi nhuận sau thuế của Công ty mẹ", "Lợi nhuận sau thuế"]),
    ("EPS_baocao", ["Lãi cơ bản trên cổ phiếu"]),
    # --- Rieng nganh Chung khoan (CTCK) — da doi chieu 100% voi so that
    # SSI Q2/2026 (3.319 / 1.422 / 1.091 / 462 / 341 / 812 / 1.529 / 1.231
    # ty dong). Chu y "4.2. Chi phi lai vay" PHAI giu tien to "4.2." vi co
    # 1 dong khac ("2.3. Chi phi lai vay, lo tu cac khoan cho vay va phai
    # thu") cung chua cum "Chi phi lai vay" — khong co tien to se khop nham.
    ("Tong_DT_hoat_dong_ck", ["Cộng doanh thu hoạt động (01"]),
    ("Lai_FVTPL_ck", ["Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ (FVTPL)"]),
    ("Lai_HTM_ck", ["Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)"]),
    ("Lai_cho_vay_ck", ["Lãi từ các khoản cho vay và phải thu"]),
    ("DT_moi_gioi_ck", ["Doanh thu môi giới chứng khoán"]),
    ("CP_moi_gioi_ck", ["Chi phí môi giới chứng khoán"]),
    ("CP_lai_vay_ck", ["4.2. Chi phí lãi vay"]),
]

CDKT_METRICS = [
    ("Tong_tai_san", ["TỔNG CỘNG TÀI SẢN"]),
    # "TỔNG NỢ PHẢI TRẢ" khong ton tai trong bao cao CTCK — Vietstock ghi
    # "A. NỢ PHẢI TRẢ (300=...)" khong co chu "TỔNG". Dung candidate ngan
    # hon "NỢ PHẢI TRẢ" de khop ca 2 kieu (da xac nhan duy nhat 1 dong
    # trong CDKT chua cum tu nay — khong dung nham dong "Phai tra nguoi
    # ban", "Du phong phai tra"... vi cac dong do khong co dung cum
    # "NỢ PHẢI TRẢ" lien tuc).
    ("Tong_no_phai_tra", ["NỢ PHẢI TRẢ"]),
    ("Von_dieu_le", ["Vốn điều lệ"]),
    # --- Rieng nganh Chung khoan (CTCK) — xac nhan nhan bang file that
    # VietstockFinance_SSI_..._CDKT (04/08/2026), doi chieu dung 10 o CA
    # trich trong tai lieu "Dinh gia SSI...". Suffix "_ck" de build_fund_pack
    # tu nhan dien va sinh section rieng, giong co che "_nganhang".
    ("Von_chu_so_huu_ck", ["VỐN CHỦ SỞ HỮU (400"]),
    ("FVTPL_ck", ["(FVTPL)"]),
    ("Cho_vay_ck", ["4. Các khoản cho vay"]),
    ("HTM_ngan_han_ck", ["3. Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)"]),
    ("HTM_dai_han_ck", ["2.1. Các khoản đầu tư nắm giữ đến ngày đáo hạn"]),
    ("Tien_va_tuong_duong_ck", ["Tiền và các khoản tương đương tiền"]),
    ("Vay_ngan_han_ck", ["1. Vay và nợ thuê tài chính ngắn hạn"]),
    ("LNST_chua_phan_phoi_ck", ["Lợi nhuận sau thuế chưa phân phối"]),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def find_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(15, len(df))):
        row = df.iloc[i]
        hits = sum(1 for v in row if isinstance(v, str) and QUARTER_RE.match(v.strip()))
        if hits >= 2:
            return i
    return None


def quarter_columns(df: pd.DataFrame, header_row: int) -> dict[int, str]:
    out = {}
    for col in range(1, df.shape[1]):
        v = df.iloc[header_row, col]
        if isinstance(v, str):
            m = QUARTER_RE.match(v.strip())
            if m:
                out[col] = f"Q{m.group(1)}/{m.group(2)}"
    return out


def find_row(df: pd.DataFrame, start_row: int, candidates: list[str]) -> int | None:
    """Thu tung candidate (tu cu the -> chung) tren TOAN BO cot, tranh khop
    nham dong chung khi dong cu the nam sau trong file (vd LNST cong ty me
    vs LNST truoc phan bo co dong thieu so)."""
    for cand in candidates:
        for i in range(start_row, len(df)):
            v = df.iloc[i, 0]
            if isinstance(v, str) and cand.lower() in v.lower():
                return i
    return None


def extract_series(df: pd.DataFrame, row_idx: int, qcols: dict[int, str]) -> dict[str, float]:
    out = {}
    for col, q in qcols.items():
        v = df.iloc[row_idx, col]
        if isinstance(v, (int, float)) and not pd.isna(v):
            out[q] = float(v)
    return out


def quarter_to_year_frac(q: str) -> float:
    m = QUARTER_RE.match(q)
    qn, yr = int(m.group(1)), int(m.group(2))
    return yr + (qn - 1) / 4


def sort_quarters(quarters) -> list[str]:
    return sorted(quarters, key=quarter_to_year_frac)


def parse_workbook(fp: Path, metrics: list[tuple[str, list[str]]]) -> dict[str, dict[str, float]]:
    df = pd.read_excel(fp, header=None)
    header_row = find_header_row(df)
    if header_row is None:
        log(f"  CANH BAO: khong tim thay dong tieu de quy trong {fp.name}")
        return {}
    qcols = quarter_columns(df, header_row)
    out = {}
    for label, candidates in metrics:
        row_idx = find_row(df, header_row + 1, candidates)
        if row_idx is None:
            continue
        series = extract_series(df, row_idx, qcols)
        if series:
            out[label] = series
    return out


def fmt(x, digits=2) -> str:
    return f"{x:,.{digits}f}" if x is not None else "N/A"


def build_fund_pack(ticker: str, cstc: dict, kqkd: dict, cdkt: dict, export_dates: list[str]) -> str:
    L = []
    latest_q = None
    if "EPS_TTM" in cstc and cstc["EPS_TTM"]:
        qs = sort_quarters(cstc["EPS_TTM"].keys())
        latest_q = qs[-1] if qs else None

    L.append("---")
    L.append(f"ma: {ticker}")
    L.append(f"quy_gan_nhat_co_du_lieu: {latest_q or 'N/A'}")
    if export_dates:
        L.append(f"ngay_xuat_file_vietstock: {', '.join(export_dates)}")
    L.append("---")
    L.append("")
    L.append(f"# Fundamental Pack — {ticker}")
    L.append("")
    L.append("Nguon: file BCTC Vietstock nguoi dung upload — KHONG tu dong cap "
             "nhat, can upload lai file moi vao data/fundamentals/{}/  de lam moi.".format(ticker))
    L.append("")

    if cstc:
        all_q = sort_quarters({q for s in cstc.values() for q in s})
        keys = list(cstc.keys())
        L.append("## Chi so dinh gia theo quy (CSTC)")
        L.append("Quy | " + " | ".join(keys))
        for q in all_q:
            row = [q] + [fmt(cstc[k].get(q)) if q in cstc.get(k, {}) else "N/A" for k in keys]
            L.append(" | ".join(row))
        L.append("")

    if "EPS_TTM" in cstc and "BVPS" in cstc and latest_q:
        eps = cstc["EPS_TTM"].get(latest_q)
        bvps = cstc["BVPS"].get(latest_q)
        pe = cstc.get("PE", {}).get(latest_q)
        L.append(f"## Graham block ({latest_q})")
        if eps is not None and bvps is not None:
            L.append(f"- EPS TTM: {fmt(eps, 0)} | BVPS: {fmt(bvps, 0)}")
            if eps > 0 and bvps > 0:
                graham_number = (22.5 * eps * bvps) ** 0.5
                L.append(f"- Graham Number = sqrt(22.5 x EPS x BVPS): {fmt(graham_number, 0)}")
                if pe:
                    price = pe * eps
                    L.append(f"- Gia dung tinh P/E tai bao cao ({latest_q}): {fmt(price, 0)} "
                             f"(CO THE cu hon gia CafeF hien tai — doi chieu lai truoc khi dung)")
                    L.append(f"- Gia / Graham Number: {fmt(price / graham_number, 2)}x")
                    L.append(f"- Earnings Yield: {fmt(100 / pe, 1)}%")
            else:
                L.append("- Graham Number: khong ap dung (EPS hoac BVPS <= 0)")

            qs = sort_quarters(cstc["EPS_TTM"].keys())
            if len(qs) >= 2:
                first_q, last_q = qs[0], qs[-1]
                eps0 = cstc["EPS_TTM"].get(first_q)
                years = quarter_to_year_frac(last_q) - quarter_to_year_frac(first_q)
                if eps0 and eps0 > 0 and eps and years > 0:
                    cagr = (eps / eps0) ** (1 / years) - 1
                    L.append(f"- EPS CAGR ({first_q} -> {last_q}, ~{years:.1f} nam): {fmt(cagr * 100, 1)}%")
                    if pe and cagr > 0:
                        L.append(f"- PEG = P/E / CAGR%: {fmt(pe / (cagr * 100), 2)}")
                    elif pe:
                        L.append("- PEG: khong ap dung (CAGR <= 0)")
        else:
            L.append("- Thieu EPS hoac BVPS cho quy gan nhat, khong tinh duoc Graham Number.")
        L.append("")

    bank_keys = [k for k in cstc if k.endswith("_nganhang")]
    if bank_keys and latest_q:
        L.append(f"## Chi so nganh Ngan hang ({latest_q})")
        L.append("LUU Y: so Vietstock la ty le THEO QUY, chua annualize — cot uoc "
                 "tinh nam chi la x4 don gian, khong phai so chinh thuc.")
        for k in bank_keys:
            v = cstc[k].get(latest_q)
            if v is not None:
                L.append(f"- {k.replace('_nganhang','')}: {fmt(v, 2)}%/quy "
                         f"(~uoc tinh nam: {fmt(v * 4, 2)}%)")
        L.append("")

    ck_cdkt_keys = [k for k in cdkt if k.endswith("_ck")]
    ck_kqkd_keys = [k for k in kqkd if k.endswith("_ck")]
    if (ck_cdkt_keys or ck_kqkd_keys) and latest_q:
        L.append(f"## Chi so nganh Chung khoan (CTCK) — {latest_q}")
        L.append("LUU Y: HTM tong = HTM ngan han + HTM dai han (2 dong rieng trong CDKT).")

        def qv(d, key, q):
            return d.get(key, {}).get(q)

        ts = qv(cdkt, "Tong_tai_san", latest_q)
        fvtpl = qv(cdkt, "FVTPL_ck", latest_q)
        cho_vay = qv(cdkt, "Cho_vay_ck", latest_q)
        htm_nh = qv(cdkt, "HTM_ngan_han_ck", latest_q)
        htm_dh = qv(cdkt, "HTM_dai_han_ck", latest_q)
        htm_tong = (htm_nh or 0) + (htm_dh or 0) if (htm_nh is not None or htm_dh is not None) else None
        tien = qv(cdkt, "Tien_va_tuong_duong_ck", latest_q)
        no_pt = qv(cdkt, "Tong_no_phai_tra", latest_q)
        vay_nh = qv(cdkt, "Vay_ngan_han_ck", latest_q)
        vcsh = qv(cdkt, "Von_chu_so_huu_ck", latest_q)
        lnst_cpp = qv(cdkt, "LNST_chua_phan_phoi_ck", latest_q)

        if cdkt and ck_cdkt_keys:
            L.append("")
            L.append("**Cau truc tai chinh (ty dong):**")
            for label, val in [("Tong tai san", ts), ("FVTPL", fvtpl), ("Cac khoan cho vay", cho_vay),
                               ("HTM (ngan + dai han)", htm_tong), ("Tien va tuong duong", tien),
                               ("Tong no phai tra", no_pt), ("Vay va no thue TC ngan han", vay_nh),
                               ("Von chu so huu", vcsh), ("LNST chua phan phoi", lnst_cpp)]:
                ty_trong = f" ({fmt(val/ts*100,1)}% tai san)" if (val is not None and ts) else ""
                L.append(f"- {label}: {fmt(val,0)}{ty_trong}")
            if ts and fvtpl is not None and cho_vay is not None:
                L.append(f"- FVTPL + Cho vay / Tong tai san: {fmt((fvtpl+cho_vay)/ts*100,1)}%")
            if vcsh and no_pt is not None:
                L.append(f"- Don bay No/VCSH: {fmt(no_pt/vcsh*100,2)}%")

        dt_mg = qv(kqkd, "DT_moi_gioi_ck", latest_q)
        cp_mg = qv(kqkd, "CP_moi_gioi_ck", latest_q)
        lai_cv = qv(kqkd, "Lai_cho_vay_ck", latest_q)
        lai_htm_kq = qv(kqkd, "Lai_HTM_ck", latest_q)
        cp_lv = qv(kqkd, "CP_lai_vay_ck", latest_q)
        tong_dt = qv(kqkd, "Tong_DT_hoat_dong_ck", latest_q)
        lai_fvtpl = qv(kqkd, "Lai_FVTPL_ck", latest_q)

        if kqkd and ck_kqkd_keys:
            L.append("")
            L.append(f"**Ket qua kinh doanh quy {latest_q} (ty dong):**")
            for label, val in [("Tong doanh thu hoat dong", tong_dt), ("Lai FVTPL", lai_fvtpl),
                               ("Lai cho vay va phai thu", lai_cv), ("Doanh thu moi gioi", dt_mg),
                               ("Chi phi moi gioi", cp_mg), ("Chi phi lai vay", cp_lv)]:
                L.append(f"- {label}: {fmt(val,0)}")
            if dt_mg is not None and cp_mg is not None:
                loi_nhuan_gop = dt_mg - cp_mg
                bien = fmt(loi_nhuan_gop/dt_mg*100,1) if dt_mg else "N/A"
                L.append(f"- Loi nhuan gop moi gioi = {fmt(dt_mg,0)} - {fmt(cp_mg,0)} = {fmt(loi_nhuan_gop,0)} (bien {bien}%)")
            if None not in (lai_cv, lai_htm_kq, cp_lv):
                nii = lai_cv + lai_htm_kq - cp_lv
                L.append(f"- Thu nhap lai thuan dai dien = {fmt(lai_cv,0)} + {fmt(lai_htm_kq,0)} - {fmt(cp_lv,0)} = {fmt(nii,0)} "
                         "(chua phan bo chi phi von cho tu doanh — chi dung kiem tra so bo)")
        L.append("")

    if kqkd:
        all_q = sort_quarters({q for s in kqkd.values() for q in s})[-8:]
        keys = list(kqkd.keys())
        L.append(f"## Ket qua kinh doanh — {len(all_q)} quy gan nhat (ty dong)")
        L.append("Quy | " + " | ".join(keys))
        for q in all_q:
            row = [q] + [fmt(kqkd[k].get(q), 0) if q in kqkd.get(k, {}) else "N/A" for k in keys]
            L.append(" | ".join(row))
        L.append("")

    if cdkt:
        all_q = sort_quarters({q for s in cdkt.values() for q in s})
        L.append(f"## Bang can doi ke toan — {len(all_q)} quy (ty dong)")
        L.append("Quy | Tong tai san | Tong no phai tra | Von dieu le | Von chu so huu (uoc tinh)")
        for q in all_q:
            ts = cdkt.get("Tong_tai_san", {}).get(q)
            npt = cdkt.get("Tong_no_phai_tra", {}).get(q)
            vdl = cdkt.get("Von_dieu_le", {}).get(q)
            vcsh = (ts - npt) if (ts is not None and npt is not None) else None
            L.append(" | ".join([q, fmt(ts, 0), fmt(npt, 0), fmt(vdl, 0), fmt(vcsh, 0)]))
        L.append("")

    L.append("## Gioi han")
    L.append(f"- Du lieu gia (CafeF) o file rieng data/packs/{ticker}.md; pack nay chi co BCTC/chi so tai chinh.")
    L.append("- Du lieu chi moi toi quy ghi tren frontmatter — upload lai file Vietstock moi de cap nhat.")

    return "\n".join(L) + "\n"


FILENAME_RE = re.compile(
    r"VietstockFinance_([A-Za-z0-9]{2,6})_Bao-cao-tai-chinh_(CSTC|KQKD|CDKT|LCTT)",
    re.IGNORECASE,
)


def find_all_source_files(root: Path) -> dict[str, dict[str, Path]]:
    """Quet TOAN BO file .xlsx duoi root (bat ke nam trong thu muc nao — phang,
    long theo nganh, hay lac cho) va nhan dien ma + loai file TU CHINH TEN FILE
    (Vietstock luon dat ten VietstockFinance_{MA}_Bao-cao-tai-chinh_{LOAI}_...).

    Thiet ke nay KHONG phu thuoc cau truc thu muc — day la sua loi thuc te da
    gap: 1 file lac vao dung thu muc nhom nganh (vd data/fundamentals/nganhang/
    thay vi nganhang/{MA}/) khien ban truoc day (dua theo TEN THU MUC) hieu
    nham "nganhang" la mot ma co phieu. Gio moi file duoc doc dung ma cua no
    bat ke dang nam o dau.

    Neu co nhieu file trung (cung ma + cung loai o nhieu noi — vd con sot file
    cu chua don), lay file sua doi gan nhat va CANH BAO ro cac file con lai
    can xoa, khong tu y chon ngau nhien."""
    found: dict[str, dict[str, list[Path]]] = {}
    skipped = []
    for fp in root.rglob("*.xlsx"):
        m = FILENAME_RE.search(fp.name)
        if not m:
            skipped.append(str(fp))
            continue
        ticker, ftype = m.group(1).upper(), m.group(2).upper()
        found.setdefault(ticker, {}).setdefault(ftype, []).append(fp)

    if skipped:
        log(f"  CANH BAO: {len(skipped)} file .xlsx khong dung dinh dang ten Vietstock, bo qua: {skipped}")

    result: dict[str, dict[str, Path]] = {}
    for ticker, types in found.items():
        result[ticker] = {}
        for ftype, paths in types.items():
            if len(paths) > 1:
                paths_sorted = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
                log(f"  CANH BAO: {ticker}/{ftype} co {len(paths)} file trung nhau — "
                    f"dung file moi nhat, CAC FILE CON LAI NEN XOA DE TRANH NHAM LAN: "
                    f"{[str(p) for p in paths_sorted]}")
                result[ticker][ftype] = paths_sorted[0]
            else:
                result[ticker][ftype] = paths[0]
    return result


def main() -> int:
    if not FUND_DIR.exists():
        log("Khong co thu muc data/fundamentals/ — khong co gi de lam.")
        return 0

    by_ticker = find_all_source_files(FUND_DIR)
    if not by_ticker:
        log("Khong tim thay file Vietstock hop le nao duoi data/fundamentals/.")
        return 0

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for ticker in sorted(by_ticker):
        log(f"\n=== Xu ly {ticker} ===")
        by_type = by_ticker[ticker]
        export_dates = []
        for fp in by_type.values():
            m = re.search(r"(\d{8})-(\d{6})", fp.name)
            if m:
                d = m.group(1)
                export_dates.append(f"{d[0:4]}-{d[4:6]}-{d[6:8]}")

        if "CSTC" not in by_type:
            log(f"  BO QUA {ticker}: thieu file CSTC (bat buoc de tinh Graham).")
            continue

        cstc = parse_workbook(by_type["CSTC"], CSTC_METRICS)
        kqkd = parse_workbook(by_type["KQKD"], KQKD_METRICS) if "KQKD" in by_type else {}
        cdkt = parse_workbook(by_type["CDKT"], CDKT_METRICS) if "CDKT" in by_type else {}

        log(f"  CSTC metrics tim thay: {list(cstc.keys())}")
        log(f"  KQKD metrics tim thay: {list(kqkd.keys())}")
        log(f"  CDKT metrics tim thay: {list(cdkt.keys())}")

        content = build_fund_pack(ticker, cstc, kqkd, cdkt, sorted(set(export_dates)))
        out_fp = PACKS_DIR / f"{ticker}-fund.md"
        out_fp.write_text(content, encoding="utf-8")
        log(f"  Da ghi {out_fp} ({out_fp.stat().st_size} bytes)")
        ok += 1

    log(f"\nKET QUA: da sinh {ok}/{len(by_ticker)} fund pack.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
