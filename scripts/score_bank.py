"""
T4c — Tinh phan CO HOC cua khung cham diem Q-G-V-T-D (xem skill
cham-diem-co-phieu-ngan-hang) cho moi ma ngan hang da co DU CA HAI
Price Pack (data/packs/{MA}.md) va Fundamental Pack (data/packs/{MA}-fund.md).

RANH GIOI RO RANG: script nay CHI tinh phan cong thuc/chuan hoa so —
KHONG viet nhan xet dinh tinh, KHONG tu suy doan Gia_hop_ly khi thieu
gia dinh Ke/g dang tin cay, KHONG so sanh nhom nganh (chua co du lieu
peer that). Phan con lai (kich ban hanh dong, nhan xet dinh tinh, so
sanh nhom nganh khi co du lieu) de trong, ghi ro "can Claude tong hop
them" — nguoi dung hoi Claude truc tiep de co phan do.

Tu dong phat hien Fundamental Pack cu (CIR/LDR con annualize sai — bug
da sua trong fund_pack.py) va CANH BAO thay vi tinh diem sai ma khong
biet.
"""

import re
import sys
from pathlib import Path

PACKS_DIR = Path("data/packs")

# Nguong tam thoi (xem skill cham-diem-co-phieu-ngan-hang — se thay bang
# phan vi that P20/P80 khi co du lieu nhieu ngan hang trong data/fundamentals/nganhang/)
THRESH = {
    "ROE": (10.0, 22.0, "+"),      # % annualize
    "ROA": (0.8, 2.2, "+"),        # % annualize
    "NIM": (2.5, 5.0, "+"),        # % annualize
    "CIR": (55.0, 30.0, "+"),      # % KHONG annualize — dao nguoc vi cang thap cang tot
    "PE": (12.0, 5.0, "+"),        # dao nguoc — cang thap cang tot
    "PB": (2.2, 0.8, "+"),         # dao nguoc
    "G_RATE": (-10.0, 30.0, "+"),  # % tang truong YoY, ap dung chung cho LNST/LNTT/EPS/BVPS/TaiSan
}
LDR_BAND = (80.0, 15.0)  # (m, w)


def log(msg: str) -> None:
    print(msg, flush=True)


def score_plus(x: float, l: float, u: float) -> float:
    return 100 * max(0.0, min(1.0, (x - l) / (u - l)))


def score_minus(x: float, u_bad: float, l_good: float) -> float:
    """u_bad = nguong kem (gia tri lon), l_good = nguong tot (gia tri nho)."""
    return 100 * max(0.0, min(1.0, (u_bad - x) / (u_bad - l_good)))


def score_band(x: float, m: float, w: float) -> float:
    return 100 * max(0.0, 1 - abs(x - m) / w)


def to_float(s: str) -> float | None:
    if s is None:
        return None
    s = s.replace(",", "").strip()
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


def parse_table(text: str, header_pattern: str) -> tuple[list[str], list[list[str]]] | None:
    m = re.search(header_pattern + r"\n(.*?)\n\n", text, re.S)
    if not m:
        return None
    lines = [l for l in m.group(1).splitlines() if l.strip()]
    if not lines:
        return None
    header = [h.strip() for h in lines[0].split("|")]
    rows = [[v.strip() for v in l.split("|")] for l in lines[1:]]
    return header, rows


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
                out["price"] = to_float(parts[4])  # close

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

    m = re.search(r"EPS CAGR.*?:\s*([\-\d.]+)%", text)
    out["eps_cagr"] = to_float(m.group(1)) if m else None

    bank_sec = re.search(r"## Chi so nganh Ngan hang.*?\n(.*?)\n\n", text, re.S)
    out["bank_section_raw"] = bank_sec.group(1) if bank_sec else ""
    out["fund_pack_outdated"] = False
    if bank_sec:
        body_after_note = bank_sec.group(1).split("\n", 1)[1] if "\n" in bank_sec.group(1) else ""
        cir_ldr_lines = [l for l in body_after_note.splitlines() if l.strip().startswith(("- CIR", "- LDR"))]
        if any("uoc tinh nam" in l for l in cir_ldr_lines):
            out["fund_pack_outdated"] = True

    cstc = parse_table(text, r"## Chi so dinh gia theo quy \(CSTC\)")
    out["cstc_latest"] = {}
    if cstc:
        header, rows = cstc
        if rows:
            last = rows[-1]
            for i, h in enumerate(header):
                if i < len(last):
                    out["cstc_latest"][h] = to_float(last[i])

    kqkd = parse_table(text, r"## Ket qua kinh doanh[^\n]*")
    out["kqkd_yoy"] = {}
    if kqkd:
        header, rows = kqkd
        if len(rows) >= 5:
            latest, yoy_ago = rows[-1], rows[-5]  # 4 quy truoc = cung ky nam truoc
            for i, h in enumerate(header):
                if h == "Quy" or i >= len(latest) or i >= len(yoy_ago):
                    continue
                v_latest, v_prev = to_float(latest[i]), to_float(yoy_ago[i])
                if v_latest is not None and v_prev not in (None, 0):
                    out["kqkd_yoy"][h] = (v_latest / v_prev - 1) * 100

    cdkt = parse_table(text, r"## Bang can doi ke toan[^\n]*")
    out["cdkt_yoy"] = {}
    if cdkt:
        header, rows = cdkt
        if len(rows) >= 5:
            latest, yoy_ago = rows[-1], rows[-5]
            for i, h in enumerate(header):
                if h == "Quy" or i >= len(latest) or i >= len(yoy_ago):
                    continue
                v_latest, v_prev = to_float(latest[i]), to_float(yoy_ago[i])
                if v_latest is not None and v_prev not in (None, 0):
                    out["cdkt_yoy"][h] = (v_latest / v_prev - 1) * 100
    return out


def compute_score(ticker: str, pp: dict, fp: dict) -> dict:
    notes = []
    d_penalty = 0.0

    # ---- Kiem tra du lieu cu (bug annualize CIR/LDR) ----
    if fp["fund_pack_outdated"]:
        notes.append("⚠️ Fundamental Pack dang o dinh dang CU (CIR/LDR van bi annualize x4 sai). "
                     "Chay lai T4b (workflow_dispatch 'Fundamental Pack (T4b)') voi fund_pack.py "
                     "ban da sua truoc khi tin ket qua Q/D duoi day.")
        d_penalty += 15

    # ---- Kiem tra lech gia giua 2 pack ----
    # QUAN TRONG: Price Pack luu gia theo don vi NGHIN DONG (vd 24.00 = 24.000d),
    # con Fundamental Pack (EPS_TTM/BVPS/gia bao cao) dung don vi DONG DAY DU
    # (vd 25,201 = 25.201d). Phai quy doi truoc khi so sanh/tinh toan, neu khong
    # se lech thang do ~1000 lan.
    gia_hien_tai = pp.get("price")
    if gia_hien_tai is not None:
        gia_hien_tai = gia_hien_tai * 1000
    gia_bao_cao = fp.get("gia_bao_cao")
    dung_gia = gia_hien_tai
    if gia_hien_tai and gia_bao_cao:
        lech_pct = abs(gia_bao_cao - gia_hien_tai) / gia_hien_tai * 100
        if lech_pct >= 5:
            notes.append(f"⚠️ Lech gia {lech_pct:.1f}% giua Fundamental Pack ({gia_bao_cao:,.0f}) "
                         f"va Price Pack ({gia_hien_tai:,.0f}) — DA TU DONG dung gia Price Pack "
                         "(moi hon) de tinh P/E, P/B, Earnings Yield duoi day.")
            d_penalty += 10
    if dung_gia is None:
        dung_gia = gia_bao_cao
        notes.append("CANH BAO: khong doc duoc gia tu Price Pack, dung tam gia bao cao trong Fundamental Pack.")

    cstc = fp.get("cstc_latest", {})

    # ================= Q — Chat luong =================
    q_parts = {}
    q_weight_used = 0.0
    roe = cstc.get("ROE")
    if roe is not None:
        roe_annual = roe * 4
        q_parts["ROE (annualize x4)"] = (score_plus(roe_annual, *THRESH["ROE"][:2]), 0.20, f"{roe_annual:.1f}%")
        q_weight_used += 0.20
    roa = cstc.get("ROA")
    if roa is not None:
        roa_annual = roa * 4
        q_parts["ROA (annualize x4)"] = (score_plus(roa_annual, *THRESH["ROA"][:2]), 0.10, f"{roa_annual:.1f}%")
        q_weight_used += 0.10
    nim = cstc.get("NIM_nganhang")
    if nim is not None:
        nim_annual = nim * 4
        q_parts["NIM (annualize x4)"] = (score_plus(nim_annual, *THRESH["NIM"][:2]), 0.15, f"{nim_annual:.1f}%")
        q_weight_used += 0.15
    cir = cstc.get("CIR_nganhang")
    if cir is not None:
        q_parts["CIR (khong annualize)"] = (score_minus(cir, THRESH["CIR"][0], THRESH["CIR"][1]), 0.10, f"{cir:.1f}%")
        q_weight_used += 0.10
    ldr = cstc.get("LDR_nganhang")
    if ldr is not None:
        q_parts["LDR (khong annualize, Score_band)"] = (score_band(ldr, *LDR_BAND), 0.10, f"{ldr:.1f}%")
        q_weight_used += 0.10
    notes.append("Q: THIEU NPL, LLCR, CAR (Fundamental Pack hien tai khong co) — "
                 "chi cham tren " + f"{q_weight_used*100:.0f}%" + " trong so, da renormalize ve thang 0-100.")
    d_penalty += 20  # luon tru vi thieu NPL/LLCR/CAR — quy dinh trong skill

    Q = (sum(s * w for s, w, _ in q_parts.values()) / q_weight_used) if q_weight_used > 0 else None

    # ================= G — Tang truong =================
    kqkd_yoy = fp.get("kqkd_yoy", {})
    cdkt_yoy = fp.get("cdkt_yoy", {})
    g_lnst = kqkd_yoy.get("LNST")
    g_lntt = kqkd_yoy.get("LNTT")
    g_eps = fp.get("eps_cagr")  # dung CAGR da co san lam proxy neu can, uu tien YoY tu CSTC neu co
    g_tai_san = cdkt_yoy.get("Tong tai san")

    # g_EPS YoY tu chuoi EPS_TTM trong CSTC (chinh xac hon CAGR 10 nam cho tang truong ngan han)
    g_parts = {}
    g_weight_used = 0.0
    if g_lnst is not None:
        g_parts["g_LNST (YoY)"] = (score_plus(g_lnst, *THRESH["G_RATE"][:2]), 0.30, f"{g_lnst:.1f}%")
        g_weight_used += 0.30
    if g_lntt is not None:
        g_parts["g_LNTT (YoY)"] = (score_plus(g_lntt, *THRESH["G_RATE"][:2]), 0.20, f"{g_lntt:.1f}%")
        g_weight_used += 0.20
    if g_eps is not None:
        g_parts["g_EPS (CAGR dai han, proxy)"] = (score_plus(g_eps, *THRESH["G_RATE"][:2]), 0.20, f"{g_eps:.1f}%")
        g_weight_used += 0.20
        notes.append("G: g_EPS dung CAGR dai han (Graham block) lam proxy vi khong co dong EPS "
                     "rieng trong bang KQKD rut gon — neu can chinh xac hon, tinh YoY tu chuoi "
                     "EPS_TTM trong bang CSTC (co san toan bo).")
    if g_tai_san is not None:
        g_parts["g_Tai_san (YoY)"] = (score_plus(g_tai_san, *THRESH["G_RATE"][:2]), 0.15, f"{g_tai_san:.1f}%")
        g_weight_used += 0.15
    G = (sum(s * w for s, w, _ in g_parts.values()) / g_weight_used) if g_weight_used > 0 else None
    if g_weight_used > 0 and g_weight_used < 0.85:
        notes.append(f"G: chi cham tren {g_weight_used*100:.0f}% trong so co du lieu (thieu g_BVPS "
                     "rieng biet — co the tinh tu chenh lech BVPS 2 quy cach nhau 4 ky trong bang CSTC).")

    # ================= V — Dinh gia =================
    v_parts = {}
    v_weight_used = 0.0
    eps_ttm, bvps = fp.get("eps_ttm"), fp.get("bvps")
    pe_now = pb_now = ey_now = None
    if dung_gia and eps_ttm:
        pe_now = dung_gia / eps_ttm
        ey_now = eps_ttm / dung_gia * 100
    if dung_gia and bvps:
        pb_now = dung_gia / bvps
    if pe_now is not None:
        v_parts["S_PE (tinh lai theo gia hien tai)"] = (
            score_minus(pe_now, THRESH["PE"][0], THRESH["PE"][1]), 0.30, f"{pe_now:.2f}x")
        v_weight_used += 0.30
    if pb_now is not None:
        v_parts["S_PB (tinh lai theo gia hien tai)"] = (
            score_minus(pb_now, THRESH["PB"][0], THRESH["PB"][1]), 0.30, f"{pb_now:.2f}x")
        v_weight_used += 0.30
    if ey_now is not None:
        # EY quy doi truc tiep sang thang diem: xem 8% la kem, 18% la tot (nguong tam thoi)
        v_parts["S_EY"] = (score_plus(ey_now, 8.0, 18.0), 0.20, f"{ey_now:.1f}%")
        v_weight_used += 0.20
    notes.append("V: S_MOS (Margin of Safety) BO QUA — can gia dinh Ke (chi phi von chu so huu) "
                 "va g (tang truong ben vung) dang tin cay, chua co san mot cach khach quan. "
                 "Neu muon tinh, dung cong thuc trong skill voi Ke/g nguoi dung tu cung cap.")
    V = (sum(s * w for s, w, _ in v_parts.values()) / v_weight_used) if v_weight_used > 0 else None

    # ================= T — Ky thuat va dong tien =================
    t_parts = {}
    ma20, ma50, ma200 = pp.get("ma20"), pp.get("ma50"), pp.get("ma200")
    if dung_gia and None not in (ma20, ma50, ma200):
        above = sum(1 for ma in (ma20, ma50, ma200) if dung_gia > ma)
        trend_score = above / 3 * 100
        t_parts["Trend (vi tri so MA20/50/200)"] = (trend_score, 0.25, f"{above}/3 MA")
    rsi, mfi = pp.get("rsi"), pp.get("mfi")
    if rsi is not None and mfi is not None:
        rsi_score = max(0.0, min(100.0, (rsi - 30) / 40 * 100))
        mfi_score = max(0.0, min(100.0, (mfi - 30) / 40 * 100))
        t_parts["Momentum (RSI+MFI)"] = ((rsi_score + mfi_score) / 2, 0.20, f"RSI {rsi} / MFI {mfi}")
    vol_ratio = pp.get("vol_ratio")
    obv_dir, vpt_dir = pp.get("obv_dir"), pp.get("vpt_dir")
    if vol_ratio is not None and obv_dir and vpt_dir:
        vol_score = max(0.0, min(100.0, vol_ratio * 50))
        dir_score = {"tang": 100, "giam": 0}.get(obv_dir, 50) / 2 + {"tang": 100, "giam": 0}.get(vpt_dir, 50) / 2
        t_parts["Volume (Vol/MA20 + huong OBV/VPT)"] = ((vol_score + dir_score) / 2, 0.20,
                                                          f"{vol_ratio}x, OBV {obv_dir}, VPT {vpt_dir}")
    notes.append("T: RelativeStrength BO QUA (can doc them data/packs/VNINDEX.md va so sanh %Δ "
                 "cung giai doan — chua tu dong hoa trong script nay).")
    pivots = pp.get("pivots", [])
    if dung_gia and pivots:
        highs_above = [p for d, t, p in pivots if t == "H" and p > dung_gia]
        lows_below = [p for d, t, p in pivots if t == "L" and p < dung_gia]
        if highs_above and lows_below:
            khang_cu = min(highs_above)
            ho_tro = max(lows_below)
            if dung_gia - ho_tro > 0:
                rr = (khang_cu - dung_gia) / (dung_gia - ho_tro)
                rr_score = max(0.0, min(100.0, (rr - 0.5) / (3 - 0.5) * 100))
                t_parts["RiskReward (tu swing points)"] = (rr_score, 0.15,
                                                             f"RR={rr:.2f} (khang cu {khang_cu}, ho tro {ho_tro})")
    t_weight_used = sum(w for _, w, _ in t_parts.values())
    T = (sum(s * w for s, w, _ in t_parts.values()) / t_weight_used) if t_weight_used > 0 else None
    if t_weight_used > 0 and t_weight_used < 0.85:
        notes.append(f"T: chi cham tren {t_weight_used*100:.0f}% trong so co du lieu co hoc "
                     "(thieu RelativeStrength).")

    # ================= Tong hop =================
    diem_tho = None
    components = {"Q": (Q, 0.30), "G": (G, 0.20), "V": (V, 0.25), "T": (T, 0.20)}
    total_w = sum(w for s, w in components.values() if s is not None)
    if total_w > 0:
        diem_tho = sum(s * w for s, w in components.values() if s is not None) / total_w * total_w
        # Neu thieu 1 cau phan, KHONG renormalize tong (giu nguyen trong so goc, tru diem qua D)
        diem_tho = sum((s * w) for s, w in components.values() if s is not None)

    D = max(0.0, 100.0 - d_penalty)

    return {
        "ticker": ticker, "diem_tho": diem_tho, "D": D,
        "Q": Q, "G": G, "V": V, "T": T,
        "q_parts": q_parts, "g_parts": g_parts, "v_parts": v_parts, "t_parts": t_parts,
        "notes": notes, "gia_dung": dung_gia,
    }


def classify(diem: float | None) -> str:
    if diem is None:
        return "Khong du du lieu de phan loai"
    if diem >= 80:
        return "Hap dan"
    if diem >= 65:
        return "Tich cuc / tich luy co dieu kien"
    if diem >= 50:
        return "Trung lap"
    return "Rui ro cao / luan diem chua du manh"


def build_output(r: dict) -> str:
    L = []
    L.append("---")
    L.append(f"ma: {r['ticker']}")
    L.append(f"loai: co-hoc-Q-G-V-T-D (T4c, tu dong)")
    L.append("---")
    L.append("")
    L.append(f"# Diem co hoc Q-G-V-T-D — {r['ticker']}")
    L.append("")
    diem_str = f"{r['diem_tho']:.0f}/100" if r["diem_tho"] is not None else "N/A"
    L.append(f"**Diem_tho: {diem_str}** — {classify(r['diem_tho'])}")
    L.append(f"**Do tin cay du lieu (D): {r['D']:.0f}/100**")
    if r["gia_dung"]:
        L.append(f"**Gia dung de tinh V: {r['gia_dung']:,.0f}**")
    L.append("")

    for label, key in (("Q — Chat luong (trong so 30%)", "q_parts"),
                        ("G — Tang truong (trong so 20%)", "g_parts"),
                        ("V — Dinh gia (trong so 25%)", "v_parts"),
                        ("T — Ky thuat va dong tien (trong so 20%)", "t_parts")):
        comp_val = r.get(label[0])
        L.append(f"## {label}")
        parts = r[key]
        if not parts:
            L.append("(khong du du lieu)")
        else:
            for name, (score, w, raw) in parts.items():
                L.append(f"- {name}: gia tri {raw} → diem {score:.0f}/100 (trong so {w:.2f})")
        L.append("")

    L.append("## Ghi chu / canh bao tu dong")
    for n in r["notes"]:
        L.append(f"- {n}")
    L.append("")

    L.append("## Phan CAN CLAUDE TONG HOP THEM (khong tu dong hoa)")
    L.append("- Nhan xet dinh tinh diem manh/diem yeu (dua tren cac gia tri tho o tren)")
    L.append("- Kich ban hanh dong (xac nhan tang / tich luy / giam rui ro) kem muc gia tu swing points")
    L.append("- So sanh voi cac ma ngan hang khac da co diem (khi co du lieu nhieu ma hon)")
    L.append("- Kiem tra chia tach/tang von truoc khi tin g_EPS, g_BVPS neu bat thuong")
    L.append("")
    L.append("Day la ket qua co hoc tu dong, KHONG phai khuyen nghi mua ban. Hoi Claude truc tiep "
             "de co ban phan tich day du theo skill cham-diem-co-phieu-ngan-hang.")

    return "\n".join(L) + "\n"


def find_bank_pairs() -> list[tuple[str, Path, Path]]:
    """Tim moi ma co DU price pack + fund pack, va fund pack co du lieu ngan hang
    (co section Chi so nganh Ngan hang — day la tin hieu day la ngan hang)."""
    pairs = []
    if not PACKS_DIR.exists():
        return pairs
    for fund_fp in sorted(PACKS_DIR.glob("*-fund.md")):
        ticker = fund_fp.stem.replace("-fund", "")
        price_fp = PACKS_DIR / f"{ticker}.md"
        if not price_fp.exists():
            continue
        text = fund_fp.read_text(encoding="utf-8")
        if "## Chi so nganh Ngan hang" not in text:
            continue  # khong phai ngan hang, bo qua
        pairs.append((ticker, price_fp, fund_fp))
    return pairs


def main() -> int:
    pairs = find_bank_pairs()
    if not pairs:
        log("Khong tim thay ma ngan hang nao co du Price Pack + Fundamental Pack.")
        return 0

    log(f"Tim thay {len(pairs)} ma ngan hang co du 2 pack: {[t for t, _, _ in pairs]}")
    ok = 0
    for ticker, price_fp, fund_fp in pairs:
        log(f"\n=== Tinh diem {ticker} ===")
        pp = parse_price_pack(price_fp.read_text(encoding="utf-8"))
        fp = parse_fund_pack(fund_fp.read_text(encoding="utf-8"))
        r = compute_score(ticker, pp, fp)
        content = build_output(r)
        out_fp = PACKS_DIR / f"{ticker}-score.md"
        out_fp.write_text(content, encoding="utf-8")
        diem_str = f"{r['diem_tho']:.0f}" if r["diem_tho"] is not None else "N/A"
        log(f"  Diem_tho: {diem_str}/100 | D: {r['D']:.0f}/100 | Da ghi {out_fp}")
        for n in r["notes"]:
            log(f"  - {n}")
        ok += 1

    log(f"\nKET QUA: da tinh diem {ok}/{len(pairs)} ma ngan hang.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
