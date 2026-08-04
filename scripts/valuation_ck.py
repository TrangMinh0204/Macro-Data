#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T4f — VALUATION PACK NGÀNH CHỨNG KHOÁN
=======================================
Đọc input YAML (data/fundamentals/chungkhoan/**/input_{MÃ}.yml) và
config/valuation_ck.yml, tính:

  1. Giá tham chiếu suy ra từ bội số (EPS x P/E, BVPS x P/B)
  2. Cấu trúc tài chính & các phép kiểm tra nhanh
     (biên gộp môi giới, NII đại diện, yield margin, funding rate)
  3. P/B hợp lý theo kịch bản:  P/B* = (ROE - g) / (Ke - g)
     -> giá trị/cp, giá trị kỳ vọng có trọng số, chênh lệch vs tham chiếu
  4. ROE hàm ý từ P/B thị trường: ROE* = g + P/B x (Ke - g)
  5. P/E hợp lý:  P/E* = (1 - g/ROE) / (Ke - g)   (kiểm tra chéo)
  6. Độ nhạy giá trị/cp theo lưới ROE x Ke (g cố định)
  7. Residual Income nhiều giai đoạn & DDM — CHỈ khi input có dự báo;
     nếu không, ghi rõ "chưa đủ dữ liệu dự báo" (không bịa số)

Nguyên tắc kế thừa từ T4c/T4d/T4e:
  - Nhận diện MÃ từ TÊN FILE (regex input_([A-Z0-9]+).yml), không
    phụ thuộc tên thư mục.
  - Không giả vờ tự động hóa phần cần phán đoán con người: các giả
    định ROE/g/Ke nằm trong config, RI/DDM để trống nếu chưa dự báo.
  - Đơn vị: chỉ tiêu /cp = đồng; chỉ tiêu tổng = tỷ đồng.

Chạy:  python scripts/valuation_ck.py
Output: data/packs/valuation_ck_{MÃ}.md
"""

import os
import re
import sys
import glob
import datetime

try:
    import yaml
except ImportError:
    sys.exit("Thiếu PyYAML: pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_GLOB = os.path.join(ROOT, "data", "fundamentals", "chungkhoan", "**", "input_*.y*ml")
CONFIG_PATH = os.path.join(ROOT, "config", "valuation_ck.yml")
OUT_DIR = os.path.join(ROOT, "data", "packs")

TICKER_RE = re.compile(r"input_([A-Z0-9]{2,10})\.ya?ml$")

TEN_KICH_BAN = {"than_trong": "Thận trọng", "co_so": "Cơ sở", "lac_quan": "Lạc quan"}


# ----------------------------------------------------------------- #
# Định dạng số kiểu Việt Nam: 26.752 | 1,43x | 87,7%
# ----------------------------------------------------------------- #
def vnd(x, dec=0):
    if x is None:
        return "—"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def pct(x, dec=2):
    return "—" if x is None else vnd(x * 100.0, dec) + "%"


def lan(x, dec=2):
    return "—" if x is None else vnd(x, dec) + "x"


def safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except TypeError:
        return None


def g(d, *keys):
    """Lấy giá trị lồng nhau, trả None nếu thiếu — không raise."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or cur.get(k) is None:
            return None
        cur = cur[k]
    return cur


# ----------------------------------------------------------------- #
# Các công thức lõi (đúng theo tài liệu)
# ----------------------------------------------------------------- #
def justified_pb(roe, gr, ke):
    """P/B hợp lý = (ROE - g) / (Ke - g). Điều kiện Ke > g."""
    if ke is None or gr is None or roe is None or ke <= gr:
        return None
    return (roe - gr) / (ke - gr)


def justified_pe(roe, gr, ke):
    """P/E hợp lý = (1 - g/ROE) / (Ke - g)."""
    if None in (roe, gr, ke) or roe == 0 or ke <= gr:
        return None
    return (1.0 - gr / roe) / (ke - gr)


def implied_roe(pb_mkt, gr, ke):
    """ROE hàm ý = g + P/B thị trường x (Ke - g)."""
    if None in (pb_mkt, gr, ke):
        return None
    return gr + pb_mkt * (ke - gr)


def residual_income_value(bvps0, roe_path, payout_path, ke, g_term):
    """
    V0 = BV0 + Σ RI_t/(1+Ke)^t + TV_T/(1+Ke)^T
    RI_t = NI_t - Ke x BV_{t-1};  NI_t = ROE_t x BV_{t-1}
    BV_t = BV_{t-1} + NI_t x (1 - payout_t)
    TV_T = RI_{T+1}/(Ke - g)  với RI_{T+1} = RI_T x (1 + g)
    Trả về (V0, bảng từng năm) — tất cả tính trên /cp (đồng).
    """
    if ke <= g_term:
        return None, []
    bv = bvps0
    pv_sum = 0.0
    rows = []
    ri_t = None
    for t, (roe_t, po_t) in enumerate(zip(roe_path, payout_path), start=1):
        ni = roe_t * bv
        ri_t = ni - ke * bv
        pv = ri_t / (1 + ke) ** t
        pv_sum += pv
        bv_next = bv + ni * (1 - po_t)
        rows.append((t, bv, roe_t, ni, ri_t, pv, bv_next))
        bv = bv_next
    T = len(roe_path)
    tv = (ri_t * (1 + g_term)) / (ke - g_term)
    pv_tv = tv / (1 + ke) ** T
    return bvps0 + pv_sum + pv_tv, rows + [("TV", None, None, None, tv, pv_tv, None)]


def ddm_value(dps_path, ke, g_term):
    """P0 = Σ DPS_t/(1+Ke)^t + DPS_{T+1} / ((Ke-g)(1+Ke)^T)"""
    if ke <= g_term:
        return None
    T = len(dps_path)
    pv = sum(d / (1 + ke) ** t for t, d in enumerate(dps_path, start=1))
    dps_next = dps_path[-1] * (1 + g_term)
    return pv + dps_next / ((ke - g_term) * (1 + ke) ** T)


# ----------------------------------------------------------------- #
# Sinh báo cáo cho 1 mã
# ----------------------------------------------------------------- #
def build_report(inp, cfg):
    ticker = inp["ticker"]
    ky = inp.get("ky_bao_cao", "—")
    thieu = []  # danh sách dữ liệu thiếu, in cuối báo cáo

    eps = g(inp, "chi_so", "eps_ttm")
    bvps = g(inp, "chi_so", "bvps")
    pe = g(inp, "chi_so", "pe")
    pb = g(inp, "chi_so", "pb")
    roe_vs = g(inp, "chi_so", "roe_ttm_vietstock")

    # --- 1. Giá tham chiếu suy ra từ bội số ---
    p_pe = eps * pe if None not in (eps, pe) else None
    p_pb = bvps * pb if None not in (bvps, pb) else None
    p_ref = None
    if p_pe and p_pb:
        p_ref = (p_pe + p_pb) / 2.0

    # --- 2. Cấu trúc tài chính ---
    ta = g(inp, "can_doi", "tong_tai_san")
    fvtpl = g(inp, "can_doi", "fvtpl")
    loans = g(inp, "can_doi", "cho_vay")
    htm = g(inp, "can_doi", "htm")
    tien = g(inp, "can_doi", "tien_va_tuong_duong")
    no_pt = g(inp, "can_doi", "no_phai_tra")
    vay_nh = g(inp, "can_doi", "vay_ngan_han")
    vcsh = g(inp, "can_doi", "von_chu_so_huu")
    loans_prev = g(inp, "can_doi", "cho_vay_ky_truoc")
    vay_prev = g(inp, "can_doi", "vay_ngan_han_ky_truoc")

    ty_trong = lambda x: safe_div(x, ta)
    fvtpl_loans_share = safe_div((fvtpl or 0) + (loans or 0), ta) if ta else None
    de_ratio = safe_div(no_pt, vcsh)
    loans_equity = safe_div(loans, vcsh)

    # --- 3. Kiểm tra nhanh KQKD quý ---
    dt_mg = g(inp, "kqkd_quy", "doanh_thu_moi_gioi")
    cp_mg = g(inp, "kqkd_quy", "chi_phi_moi_gioi")
    lai_cv = g(inp, "kqkd_quy", "lai_cho_vay")
    lai_htm = g(inp, "kqkd_quy", "lai_htm")
    cp_lai = g(inp, "kqkd_quy", "chi_phi_lai_vay")

    mg_gop = dt_mg - cp_mg if None not in (dt_mg, cp_mg) else None
    mg_bien = safe_div(mg_gop, dt_mg)
    nii_proxy = None
    if None not in (lai_cv, lai_htm, cp_lai):
        nii_proxy = lai_cv + lai_htm - cp_lai

    # Yield margin & funding rate quy đổi năm (x4, dư nợ bình quân quý)
    yield_margin = None
    if None not in (lai_cv, loans, loans_prev):
        yield_margin = lai_cv / ((loans + loans_prev) / 2.0) * 4
    funding_rate = None
    if None not in (cp_lai, vay_nh, vay_prev):
        funding_rate = cp_lai / ((vay_nh + vay_prev) / 2.0) * 4
    spread = None
    if None not in (yield_margin, funding_rate):
        spread = yield_margin - funding_rate

    # --- ROE trailing tính trực tiếp ---
    lnst_ttm = g(inp, "kqkd_ttm", "lnst_cty_me")
    vc_bq = g(inp, "kqkd_ttm", "von_chu_binh_quan")
    roe_truc_tiep = safe_div(lnst_ttm, vc_bq)

    # --- 4. Kịch bản P/B hợp lý ---
    kb_rows, ev = [], None
    if bvps:
        ev = 0.0
        w_sum = 0.0
        for key, kb in cfg["kich_ban"].items():
            pb_star = justified_pb(kb["roe"], kb["g"], kb["ke"])
            gia = bvps * pb_star if pb_star else None
            pe_star = justified_pe(kb["roe"], kb["g"], kb["ke"])
            kb_rows.append((TEN_KICH_BAN.get(key, key), kb, pb_star, gia, pe_star))
            if gia:
                ev += kb["trong_so"] * gia
                w_sum += kb["trong_so"]
        ev = ev / w_sum if w_sum else None
    else:
        thieu.append("BVPS (CSTC) — không thể tính giá trị theo P/B hợp lý")

    chenh_lech = safe_div(ev - p_ref, p_ref) if None not in (ev, p_ref) else None

    # --- 5. ROE hàm ý ---
    ir_g = g(cfg, "implied_roe", "g")
    ir_ke = g(cfg, "implied_roe", "ke")
    roe_ham_y = implied_roe(pb, ir_g, ir_ke)

    # --- 6. Độ nhạy ---
    sens = cfg.get("sensitivity", {})
    sg, s_roe, s_ke = sens.get("g"), sens.get("roe", []), sens.get("ke", [])

    # --- 7. RI & DDM (tùy chọn) ---
    ri_cfg = inp.get("residual_income")
    ddm_cfg = inp.get("ddm")

    # =============================================================
    # Render markdown
    # =============================================================
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    L = []
    A = L.append
    A(f"# VALUATION PACK — {ticker} (Ngành chứng khoán)")
    A("")
    A(f"- Kỳ báo cáo: **{ky}** | Sinh lúc: {now}")
    A(f"- Nguồn dữ liệu: {inp.get('nguon', '—')}")
    A("- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi có dự báo.")
    A("- Lưu ý: giá suy ra từ dữ liệu chỉ số, **không phải báo giá thời gian thực**. Đây là phân tích, không phải khuyến nghị mua/bán.")
    A("")

    A("## 1. Giá tham chiếu suy ra từ bội số")
    A("")
    A("| Cách tính | Công thức | Kết quả (đồng/cp) |")
    A("|---|---|---:|")
    A(f"| Theo P/E | {vnd(eps, 2)} × {vnd(pe, 2)} | **{vnd(p_pe)}** |")
    A(f"| Theo P/B | {vnd(bvps, 2)} × {vnd(pb, 2)} | **{vnd(p_pb)}** |")
    A(f"| Tham chiếu (trung bình) | — | **{vnd(p_ref)}** |")
    A("")

    A("## 2. Cấu trúc tài chính")
    A("")
    A("| Chỉ tiêu | Giá trị (tỷ đồng) | Tỷ trọng tài sản |")
    A("|---|---:|---:|")
    for label, val in [("Tổng tài sản", ta), ("FVTPL", fvtpl), ("Các khoản cho vay", loans),
                       ("HTM", htm), ("Tiền và tương đương", tien),
                       ("Tổng nợ phải trả", no_pt), ("Vay ngắn hạn", vay_nh),
                       ("Vốn chủ sở hữu", vcsh)]:
        A(f"| {label} | {vnd(val)} | {pct(ty_trong(val), 1)} |")
    A("")
    A(f"- FVTPL + Cho vay / Tổng tài sản = **{pct(fvtpl_loans_share, 1)}** → lợi nhuận nhạy với giá tài sản, thanh khoản, lãi suất và quản trị TSBĐ.")
    A(f"- Đòn bẩy Nợ/VCSH = **{pct(de_ratio, 2)}** | Dư nợ cho vay/VCSH = **{pct(loans_equity, 1)}**")
    A("")

    A("## 3. Kiểm tra nhanh hiệu quả (quý gần nhất)")
    A("")
    A(f"- Lợi nhuận gộp môi giới = {vnd(dt_mg)} − {vnd(cp_mg)} = **{vnd(mg_gop)} tỷ** → biên gộp **{pct(mg_bien, 1)}**")
    A(f"- Thu nhập lãi thuần đại diện = {vnd(lai_cv)} + {vnd(lai_htm)} − {vnd(cp_lai)} = **{vnd(nii_proxy)} tỷ** (chưa phân bổ chi phí vốn cho tự doanh — chỉ dùng kiểm tra sơ bộ)")
    A(f"- Suất sinh lời cho vay quy năm (dư nợ bình quân, ×4) = **{pct(yield_margin, 2)}**")
    A(f"- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **{pct(funding_rate, 2)}**")
    A(f"- Chênh lệch đại diện = **{vnd((spread or 0) * 100, 2) if spread is not None else '—'} điểm %** (không phải NIM kế toán — nợ vay còn tài trợ FVTPL/HTM)")
    A(f"- ROE trailing tính trực tiếp = {vnd(lnst_ttm)}/{vnd(vc_bq)} = **{pct(roe_truc_tiep, 2)}** so với ROEA Vietstock **{vnd(roe_vs, 2)}%**")
    A("")

    A("## 4. Định giá P/B hợp lý theo kịch bản")
    A("")
    A("Công thức: `P/B* = (ROE − g)/(Ke − g)` ; `Giá trị/cp = BVPS × P/B*` ; điều kiện `Ke > g`.")
    A("")
    A("| Kịch bản | ROE chuẩn hóa | g | Ke | Trọng số | P/B hợp lý | P/E hợp lý | Giá trị/cp (đồng) |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, kb, pb_star, gia, pe_star in kb_rows:
        A(f"| {name} | {pct(kb['roe'], 1)} | {pct(kb['g'], 1)} | {pct(kb['ke'], 1)} | "
          f"{pct(kb['trong_so'], 0)} | {lan(pb_star)} | {lan(pe_star, 1)} | **{vnd(gia)}** |")
    A("")
    A(f"- **Giá trị kỳ vọng có trọng số ≈ {vnd(ev)} đồng/cp**")
    if chenh_lech is not None:
        huong = "thấp hơn" if chenh_lech < 0 else "cao hơn"
        A(f"- So với giá tham chiếu {vnd(p_ref)} đồng/cp: **{huong} khoảng {pct(abs(chenh_lech), 1)}**")
    A("- Đây không phải kết luận mua/bán — chênh lệch phản ánh khoảng cách giữa ROE thị giá đang đòi hỏi và ROE trailing.")
    A("")

    A("## 5. ROE mà thị giá đang kỳ vọng")
    A("")
    A("Đảo công thức: `ROE hàm ý = g + P/B thị trường × (Ke − g)`")
    A("")
    A(f"- Với Ke = {pct(ir_ke, 1)}, g = {pct(ir_g, 1)}, P/B = {lan(pb)}: **ROE hàm ý = {pct(roe_ham_y, 2)}**")
    if None not in (roe_ham_y, roe_truc_tiep):
        so_sanh = "CAO hơn" if roe_ham_y > roe_truc_tiep else "THẤP hơn"
        A(f"- ROE hàm ý {so_sanh} ROE trailing trực tiếp ({pct(roe_truc_tiep, 2)}) → thị giá đang đặt cược vào khả năng "
          "nâng/giữ ROE qua thanh khoản thị trường, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.")
    A("")

    if sg and s_roe and s_ke and bvps:
        A(f"## 6. Độ nhạy giá trị/cp theo ROE × Ke (g = {pct(sg, 1)})")
        A("")
        A("| ROE \\ Ke | " + " | ".join(pct(k, 1) for k in s_ke) + " |")
        A("|---|" + "---:|" * len(s_ke))
        for r in s_roe:
            cells = []
            for k in s_ke:
                pbx = justified_pb(r, sg, k)
                cells.append(vnd(bvps * pbx) if pbx else "n/a")
            A(f"| {pct(r, 1)} | " + " | ".join(cells) + " |")
        A("")

    A("## 7. Residual Income & DDM")
    A("")
    if ri_cfg:
        v0, rows = residual_income_value(bvps, ri_cfg["roe_path"], ri_cfg["payout_path"],
                                         ri_cfg["ke"], ri_cfg["g_terminal"])
        A(f"**Residual Income** (Ke = {pct(ri_cfg['ke'], 1)}, g dài hạn = {pct(ri_cfg['g_terminal'], 1)}):")
        A("")
        A("| Năm | BV đầu kỳ | ROE | NI/cp | RI/cp | PV(RI) |")
        A("|---|---:|---:|---:|---:|---:|")
        for t, bv0_, roe_t, ni, ri, pv, _ in rows:
            A(f"| {t} | {vnd(bv0_)} | {pct(roe_t, 1) if roe_t else '—'} | {vnd(ni)} | {vnd(ri)} | {vnd(pv)} |")
        A("")
        A(f"→ **V0 = {vnd(v0)} đồng/cp**")
    else:
        A("- Residual Income: **chưa đủ dữ liệu dự báo** (cần ROE, tăng vốn, cổ tức, pha loãng theo từng năm 3–5 năm). "
          "Điền mục `residual_income` trong file input để kích hoạt.")
    if ddm_cfg:
        p0 = ddm_value(ddm_cfg["dps_path"], ddm_cfg["ke"], ddm_cfg["g_terminal"])
        A(f"- **DDM: P0 = {vnd(p0)} đồng/cp** (lưu ý: DDM dễ đánh giá thấp CTCK thường xuyên tăng vốn nếu payout hiện tại thấp hơn năng lực dài hạn).")
    else:
        A("- DDM: **chưa có kế hoạch cổ tức dự kiến** — điền mục `ddm` trong file input để kích hoạt.")
    A("")

    A("## 8. Dữ liệu cần bổ sung để nâng độ tin cậy")
    A("")
    for item in ["Chi tiết dư nợ margin, ứng trước và chất lượng tài sản bảo đảm",
                 "Cơ cấu danh mục FVTPL (cổ phiếu / trái phiếu / CCTG / khác)",
                 "Lãi suất cho vay margin, chi phí vốn bình quân, kỳ hạn nợ vay",
                 "Tỷ lệ vốn khả dụng và hạn mức cho vay còn lại",
                 "Số cổ phiếu pha loãng bình quân, ESOP, công cụ chuyển đổi",
                 "Cổ tức dự kiến, kế hoạch phát hành, mục đích sử dụng vốn",
                 "Kịch bản thanh khoản thị trường, thị phần môi giới, phí bình quân"]:
        A(f"- {item}")
    for t_ in thieu:
        A(f"- ⚠️ THIẾU TRONG INPUT: {t_}")
    A("")
    A("---")
    A("*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, CFO đơn kỳ, P/S — "
      "vì nợ vay và biến động tài sản tài chính là bộ phận vận hành cốt lõi.*")
    A("")
    A("*This is research and analysis only, not personalized financial advice.*")
    return "\n".join(L)


# ----------------------------------------------------------------- #
def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Sanity check config: Ke > g mọi kịch bản
    for key, kb in cfg["kich_ban"].items():
        if kb["ke"] <= kb["g"]:
            sys.exit(f"Config lỗi: kịch bản '{key}' có Ke <= g — vi phạm điều kiện áp dụng.")

    files = sorted(glob.glob(INPUT_GLOB, recursive=True))
    if not files:
        print("Không tìm thấy file input nào tại data/fundamentals/chungkhoan/**/input_*.yml")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    for path in files:
        m = TICKER_RE.search(os.path.basename(path))
        if not m:
            print(f"Bỏ qua (tên file không khớp mẫu input_{{MÃ}}.yml): {path}")
            continue
        ticker = m.group(1)
        with open(path, encoding="utf-8") as f:
            inp = yaml.safe_load(f)
        inp["ticker"] = ticker  # tên file là nguồn sự thật về mã
        report = build_report(inp, cfg)
        out = os.path.join(OUT_DIR, f"valuation_ck_{ticker}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✓ {ticker}: {out}")


if __name__ == "__main__":
    main()
