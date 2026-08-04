"""
T4d — Tinh phan CO HOC cua khung dinh gia BDS Khu Cong Nghiep (L-O-F-V-C-
T-G), xem skill dinh-gia-bds-khu-cong-nghiep. Doc Price Pack + Fundamental
Pack da co san (data/packs/{MA}.md va {MA}-fund.md), tinh CHI PHAN CO
CONG THUC RO RANG tu du lieu BCTC.

RANH GIOI RO RANG (quan trong hon ca script score_bank.py): L (25%),
O (20%), C (10%) — tong 55% trong so — LUON de trong, KHONG tinh, vi
can du lieu quy dat/ty le lap day/du an moi HOAN TOAN khong co trong
BCTC. Script CHU DICH khong gop S_raw gia (vd gia dinh L=O=C=100) vi se
gay hieu lam nghiem trong ve muc do "re/dat" cua co phieu KCN.

Nhan dien ma thuoc nhom BDS KCN: quet moi file .xlsx duoi
data/fundamentals/, ma nao co duong dan file chua chuoi "BDSKCN" (khong
phan biet hoa/thuong) o bat ky cap thu muc nao thi coi thuoc nhom nay —
khop dung cach nguoi dung da to chuc thu muc
(data/fundamentals/BDSKCN/{MA}/).

GIOI HAN DA BIET (04/08/2026): dieu chinh NCI (loi ich co dong khong
kiem soat) cho BVPS/P-B — phan quan trong nhat cua khung V — CHUA tinh
duoc vi fund_pack.py chua trich xuat dong NCI tu CDKT. Ket qua P/B duoi
day la CHUA dieu chinh, co the cao hon gia tri thuc thuoc co dong cong
ty me (xem canh bao trong tai lieu goc: VGC lech 40% giua P/B cong bo
va P/B dieu chinh NCI).
"""

import re
import sys
import unicodedata
from pathlib import Path

FUND_DIR = Path("data/fundamentals")
PACKS_DIR = Path("data/packs")
SECTOR_MARKER = "bdskcn"


def log(msg: str) -> None:
    print(msg, flush=True)


def to_float(s) -> float | None:
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "N/A", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def find_kcn_tickers() -> list[str]:
    """Ma nao co it nhat 1 file .xlsx nam duoi duong dan chua 'BDSKCN'
    (khong phan biet hoa/thuong) thi coi la thuoc nhom BDS KCN. Nhan
    dien ma tu TEN FILE (giong fund_pack.py), khong phai ten thu muc —
    ben vung neu file lo dat sai cho."""
    if not FUND_DIR.exists():
        return []
    filename_re = re.compile(
        r"VietstockFinance_([A-Za-z0-9]{2,6})_Bao-cao-tai-chinh_(CSTC|KQKD|CDKT|LCTT)",
        re.IGNORECASE,
    )
    tickers = set()
    for fp in FUND_DIR.rglob("*.xlsx"):
        if SECTOR_MARKER in str(fp).lower():
            m = filename_re.search(fp.name)
            if m:
                tickers.add(m.group(1).upper())
    return sorted(tickers)


def parse_price_pack(text: str) -> dict:
    fm = read_frontmatter(text)
    out = {"ma": fm.get("ma"), "ngay": fm.get("ngay_du_lieu_gan_nhat")}

    m = re.search(r"MA20/50/200:\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)", text)
    if m:
        out["ma20"], out["ma50"], out["ma200"] = (float(x) for x in m.groups())

    for key, pat in (("rsi", r"RSI14:\s*([\d.]+)"),
                      ("mfi", r"MFI14:\s*([\d.]+)"),
                      ("vol_ratio", r"Volume/MA20vol:\s*([\d.]+)x")):
        m = re.search(pat, text)
        out[key] = float(m.group(1)) if m else None

    m = re.search(r"OBV:.*?huong 20 phien:\s*(\w+)", text)
    out["obv_dir"] = m.group(1) if m else None
    m = re.search(r"VPT:.*?huong 20 phien:\s*(\w+)", text)
    out["vpt_dir"] = m.group(1) if m else None

    daily = re.search(r"## Daily.*?\n(.*?)\n\n", text, re.S)
    out["price"] = None
    if daily:
        lines = [l for l in daily.group(1).splitlines() if l.strip()]
        if lines:
            parts = lines[-1].split(",")
            if len(parts) >= 5:
                out["price"] = to_float(parts[4])

    pivots = []
    sw = re.search(r"## Swing points.*?\n(.*?)\n\n", text, re.S)
    if sw:
        for line in sw.group(1).splitlines():
            m = re.match(r"-\s*(\d{4}-\d{2}-\d{2})\s+([HL])\s+([\d.]+)", line.strip())
            if m:
                pivots.append((m.group(1), m.group(2), float(m.group(3))))
    out["pivots"] = pivots
    return out


def parse_fund_pack(text: str) -> dict:
    fm = read_frontmatter(text)
    out = {"ma": fm.get("ma"), "quy": fm.get("quy_gan_nhat_co_du_lieu")}

    m = re.search(r"EPS TTM:\s*([\d,]+)\s*\|\s*BVPS:\s*([\d,]+)", text)
    out["eps_ttm"] = to_float(m.group(1)) if m else None
    out["bvps"] = to_float(m.group(2)) if m else None

    m = re.search(r"Gia dung tinh P/E tai bao cao[^:]*:\s*([\d,]+)", text)
    out["gia_bao_cao"] = to_float(m.group(1)) if m else None

    # Bang can doi ke toan — lay dong QUY GAN NHAT (dong cuoi bang)
    cdkt = re.search(r"## Bang can doi ke toan[^\n]*\n(.*?)\n\n", text, re.S)
    out["cdkt"] = {}
    if cdkt:
        lines = [l for l in cdkt.group(1).splitlines() if l.strip()]
        if len(lines) >= 2:
            header = [h.strip() for h in lines[0].split("|")]
            last = [v.strip() for v in lines[-1].split("|")]
            for i, h in enumerate(header):
                if i < len(last) and h != "Quy":
                    out["cdkt"][h] = to_float(last[i])

    # KQKD — lay dong QUY GAN NHAT
    kqkd = re.search(r"## Ket qua kinh doanh[^\n]*\n(.*?)\n\n", text, re.S)
    out["kqkd"] = {}
    if kqkd:
        lines = [l for l in kqkd.group(1).splitlines() if l.strip()]
        if len(lines) >= 2:
            header = [h.strip() for h in lines[0].split("|")]
            last = [v.strip() for v in lines[-1].split("|")]
            for i, h in enumerate(header):
                if i < len(last) and h != "Quy":
                    out["kqkd"][h] = to_float(last[i])

    return out


def compute_kcn(ticker: str, pp: dict, fp: dict) -> dict:
    notes = []
    cdkt = fp.get("cdkt", {})
    kqkd = fp.get("kqkd", {})

    # ---- Gia dung: uu tien Price Pack, quy doi nghin dong -> dong day du ----
    gia_hien_tai = pp.get("price")
    if gia_hien_tai is not None:
        gia_hien_tai = gia_hien_tai * 1000
    gia_bao_cao = fp.get("gia_bao_cao")
    dung_gia = gia_hien_tai
    if gia_hien_tai and gia_bao_cao:
        lech_pct = abs(gia_bao_cao - gia_hien_tai) / gia_hien_tai * 100
        if lech_pct >= 5:
            notes.append(f"Lech gia {lech_pct:.1f}% giua Fundamental Pack ({gia_bao_cao:,.0f}) "
                         f"va Price Pack ({gia_hien_tai:,.0f}) — da tu dong dung gia Price Pack.")
    if dung_gia is None:
        dung_gia = gia_bao_cao

    # ================= F — Chat luong tai chinh (mot phan) =================
    f_parts = {}
    ts = cdkt.get("Tong tai san")
    npt = cdkt.get("Tong no phai tra")
    vdl = cdkt.get("Von dieu le")
    vay_nh = cdkt.get("Vay ngan han")
    vay_dh = cdkt.get("Vay dai han")
    tien = cdkt.get("Tien va tuong duong")
    no_vay_rong = cdkt.get("No vay rong")
    vcsh = (ts - npt) if (ts is not None and npt is not None) else None

    if vay_nh is not None and vay_dh is not None and ts:
        f_parts["No vay / Tong tai san"] = f"{(vay_nh + vay_dh) / ts * 100:.2f}%"
    if vay_nh is not None and vay_dh is not None and vcsh:
        f_parts["No vay / Von chu so huu"] = f"{(vay_nh + vay_dh) / vcsh * 100:.2f}%"
    if no_vay_rong is not None and vcsh:
        f_parts["No vay rong / Von chu so huu"] = f"{no_vay_rong / vcsh * 100:.2f}%"
    lntt = kqkd.get("LNTT")
    chi_phi_lai_vay = kqkd.get("Chi phi lai vay") if "Chi phi lai vay" in kqkd else None
    if lntt is not None and chi_phi_lai_vay:
        f_parts["Kha nang thanh toan lai vay"] = f"{(lntt + chi_phi_lai_vay) / chi_phi_lai_vay:.2f}x"
    if not f_parts:
        notes.append("F: khong tinh duoc chi so don bay nao — thieu du lieu No vay/Von chu so "
                     "huu tu Fundamental Pack (kiem tra da co du CDKT chua).")
    if not chi_phi_lai_vay:
        notes.append("F: khong co Chi phi lai vay trong KQKD — chua tinh duoc Kha nang thanh "
                     "toan lai vay.")
    notes.append("F: Dong tien (CFO/Cash Conversion) THUONG KHONG CO — nhieu cong ty KCN co "
                 "sheet LCTT Vietstock rong hoan toan o cac quy gan nhat (da xac nhan thuc te "
                 "voi VGC). Neu Fundamental Pack co muc Luu chuyen tien te, doc them thu cong.")

    # ================= V — Dinh gia (mot phan — CHUA dieu chinh NCI) =================
    v_parts = {}
    eps_ttm, bvps = fp.get("eps_ttm"), fp.get("bvps")
    so_co_phieu = None
    if vcsh and bvps:
        # vcsh doc tu bang CDKT dang don vi TY DONG, bvps la DONG THO —
        # quy doi truoc khi chia de ra dung so co phieu (khong phai ty le sai don vi)
        so_co_phieu = (vcsh * 1e9) / bvps
    if dung_gia and eps_ttm:
        v_parts["P/E TTM"] = f"{dung_gia / eps_ttm:.2f}x"
        v_parts["Earnings Yield"] = f"{eps_ttm / dung_gia * 100:.1f}%"
    if dung_gia and bvps:
        v_parts["P/B (CHUA dieu chinh NCI — xem canh bao)"] = f"{dung_gia / bvps:.2f}x"
    if dung_gia and so_co_phieu:
        von_hoa = dung_gia * so_co_phieu
        v_parts["Von hoa uoc tinh (trieu CP x gia)"] = f"{von_hoa / 1e9:,.0f} ty dong"
        if no_vay_rong is not None:
            ev = von_hoa + no_vay_rong * 1e9
            v_parts["EV uoc tinh"] = f"{ev / 1e9:,.0f} ty dong"
    notes.append("V: P/RNAV va SOTP KHONG tinh duoc — can dien tich du an, gia thue, WACC "
                 "gia dinh, hoan toan ngoai BCTC. Day la phan QUAN TRONG NHAT cua dinh gia KCN "
                 "theo tai lieu goc — dung dung P/E hay P/B o tren de ket luan re/dat.")
    notes.append("V: P/B tren CHUA tru Loi ich co dong khong kiem soat (NCI) — fund_pack.py "
                 "chua trich xuat dong nay. Theo tai lieu tham chieu, dieu chinh NCI co the "
                 "thay doi P/B toi 40% (vi du VGC: 1,46x cong bo vs 2,04x dieu chinh).")

    # ================= T — Ky thuat (tinh duoc day du) =================
    t_parts = {}
    ma20, ma50, ma200 = pp.get("ma20"), pp.get("ma50"), pp.get("ma200")
    if dung_gia and None not in (ma20, ma50, ma200):
        above = sum(1 for ma in (ma20, ma50, ma200) if dung_gia > ma * 1000)
        t_parts["Trend (vi tri so MA20/50/200)"] = f"{above}/3 MA"
    rsi, mfi = pp.get("rsi"), pp.get("mfi")
    if rsi is not None:
        t_parts["RSI14"] = f"{rsi}"
    if mfi is not None:
        t_parts["MFI14"] = f"{mfi}"
    vol_ratio = pp.get("vol_ratio")
    obv_dir, vpt_dir = pp.get("obv_dir"), pp.get("vpt_dir")
    if vol_ratio is not None:
        t_parts["Volume/MA20"] = f"{vol_ratio}x"
    if obv_dir and vpt_dir:
        t_parts["Huong OBV/VPT (20 phien)"] = f"{obv_dir} / {vpt_dir}"
    pivots = pp.get("pivots", [])
    if dung_gia and pivots:
        highs_above = [p for d, tp, p in pivots if tp == "H" and p * 1000 > dung_gia]
        lows_below = [p for d, tp, p in pivots if tp == "L" and p * 1000 < dung_gia]
        if highs_above and lows_below:
            khang_cu, ho_tro = min(highs_above), max(lows_below)
            if dung_gia - ho_tro * 1000 > 0:
                rr = (khang_cu * 1000 - dung_gia) / (dung_gia - ho_tro * 1000)
                t_parts["RiskReward (tu swing points)"] = (
                    f"{rr:.2f} (khang cu {khang_cu}, ho tro {ho_tro})")

    # ================= G — Quan tri (mot phan) =================
    g_parts = {}
    notes.append("G: Parent Capture (LNST co dong cong ty me / LNST hop nhat) CHUA tinh duoc "
                 "— fund_pack.py hien chi trich 1 dong LNST (uu tien cong ty me), thieu dong "
                 "LNST hop nhat rieng biet de so sanh.")

    # ================= L / O / C — KHONG tinh, luon de trong =================
    missing_note = ("KHONG tinh duoc — can du lieu hoan toan ngoai BCTC (quy dat/phap ly, ty le "
                    "lap day/backlog, du an moi/chat xuc tac). Hoi Claude truc tiep voi du lieu "
                    "bo sung tu nguoi dung hoac nguon rieng.")

    return {
        "ticker": ticker, "gia_dung": dung_gia,
        "f_parts": f_parts, "v_parts": v_parts, "t_parts": t_parts, "g_parts": g_parts,
        "missing_note": missing_note, "notes": notes,
        "cdkt": cdkt, "kqkd": kqkd,
    }


def build_output(r: dict) -> str:
    L = []
    L.append("---")
    L.append(f"ma: {r['ticker']}")
    L.append("loai: co-hoc-BDS-KCN-L-O-F-V-C-T-G (T4d, tu dong)")
    L.append("---")
    L.append("")
    L.append(f"# Diem co hoc dinh gia BDS KCN — {r['ticker']}")
    L.append("")
    L.append("**KHONG co S_raw tong hop** — thieu 55% trong so (L 25% + O 20% + C 10%), khong "
             "the cong gop mot cach co y nghia. Duoi day la cac cau phan da tinh duoc rieng le.")
    if r["gia_dung"]:
        L.append(f"**Gia dung de tinh:** {r['gia_dung']:,.0f} dong")
    L.append("")

    for label, key in (("F — Chat luong tai chinh (trong so 15%, mot phan)", "f_parts"),
                        ("V — Dinh gia (trong so 20%, mot phan — CHUA co P/RNAV)", "v_parts"),
                        ("T — Ky thuat (trong so 5%, day du)", "t_parts"),
                        ("G — Quan tri (trong so 5%, mot phan)", "g_parts")):
        L.append(f"## {label}")
        parts = r[key]
        if not parts:
            L.append("(khong tinh duoc — xem ghi chu ben duoi)")
        else:
            for name, val in parts.items():
                L.append(f"- {name}: {val}")
        L.append("")

    L.append("## L — Quy dat va phap ly (trong so 25%)")
    L.append(r["missing_note"])
    L.append("")
    L.append("## O — Hoat dong va backlog (trong so 20%)")
    L.append(r["missing_note"])
    L.append("")
    L.append("## C — Chat xuc tac (trong so 10%)")
    L.append(r["missing_note"])
    L.append("")

    L.append("## Ghi chu / canh bao tu dong")
    for n in r["notes"]:
        L.append(f"- {n}")
    L.append("")

    L.append("## Phan CAN CLAUDE TONG HOP THEM")
    L.append("- Toan bo L/O/C (55% trong so) — can du lieu quy dat/lap day/du an tu nguoi dung")
    L.append("- P/RNAV, SOTP — can dinh gia tung du an rieng")
    L.append("- P/B dieu chinh NCI — can fund_pack.py trich xuat them dong Loi ich co dong "
             "khong kiem soat")
    L.append("- Diem phat rui ro P (0-15) — can danh gia dinh tinh tung rui ro cu the")
    L.append("- Kich ban hanh dong va ket luan re/dat — CHI dua ra khi da co du L/O/C, khong "
             "duoc ket luan chi tu P/E hay P/B")
    L.append("")
    L.append("Day la ket qua co hoc tu dong, KHONG phai khuyen nghi mua ban. Hoi Claude truc "
             "tiep de co ban phan tich day du theo skill dinh-gia-bds-khu-cong-nghiep.")

    return "\n".join(L) + "\n"


def main() -> int:
    tickers = find_kcn_tickers()
    if not tickers:
        log("Khong tim thay ma nao trong nhom BDS KCN (duong dan chua 'BDSKCN').")
        return 0

    log(f"Tim thay {len(tickers)} ma BDS KCN: {tickers}")
    ok = 0
    for ticker in tickers:
        price_fp = PACKS_DIR / f"{ticker}.md"
        fund_fp = PACKS_DIR / f"{ticker}-fund.md"
        log(f"\n=== Tinh {ticker} ===")
        if not price_fp.exists():
            log(f"  BO QUA: thieu Price Pack {price_fp}")
            continue
        if not fund_fp.exists():
            log(f"  BO QUA: thieu Fundamental Pack {fund_fp}")
            continue

        pp = parse_price_pack(price_fp.read_text(encoding="utf-8"))
        fp = parse_fund_pack(fund_fp.read_text(encoding="utf-8"))
        r = compute_kcn(ticker, pp, fp)
        content = build_output(r)
        out_fp = PACKS_DIR / f"{ticker}-kcn.md"
        out_fp.write_text(content, encoding="utf-8")
        log(f"  Da ghi {out_fp}")
        for n in r["notes"]:
            log(f"  - {n}")
        ok += 1

    log(f"\nKET QUA: da tinh {ok}/{len(tickers)} ma BDS KCN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
