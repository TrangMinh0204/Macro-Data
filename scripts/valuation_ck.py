#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T4f — VALUATION PACK NGÀNH CHỨNG KHOÁN (v2 — doc trang tu file Vietstock)
===========================================================================
Doc THANG file Vietstock CSTC/KQKD/CDKT goc duoi data/fundamentals/CK/**
qua thu vien dung chung scripts/fund_pack.py (khong doc lai file .md da
sinh ra — tranh phu thuoc thu tu chay giua workflow fund-pack va workflow
nay; fund_pack.py va valuation_ck.py cung nam trong scripts/ nen import
truc tiep duoc).

Ap dung DAI TRA: bat ky ma nao co du 3 file CSTC+KQKD+CDKT hop le duoi
data/fundamentals/CK/{MA}/ deu tu dong duoc dinh gia — khong can tao
input_{MA}.yml thu cong nua.

Tinh:
  1. Gia tham chieu suy ra tu boi so (EPS x P/E, BVPS x P/B)
  2. Cau truc tai chinh & kiem tra nhanh (bien gop moi gioi, NII dai dien,
     yield margin, funding rate — dung so du BINH QUAN quy hien tai +
     quy lien truoc, quy doi nam x4)
  3. P/B hop ly theo kich ban:  P/B* = (ROE - g) / (Ke - g)
  4. ROE ham y tu P/B thi truong; P/E hop ly (kiem tra cheo)
  5. Do nhay gia tri/cp theo luoi ROE x Ke
  6. Residual Income / DDM — CHI khi config/valuation_ck.yml co du bao
     rieng cho ma do (muc du_bao_{MA}); khong bia so.

Chay:  python scripts/valuation_ck.py
Output: data/packs/valuation_ck_{MA}.md
"""

import os
import sys
import datetime

try:
    import yaml
except ImportError:
    sys.exit("Thieu PyYAML: pip install pyyaml")

# fund_pack.py nam cung thu muc scripts/ — import truc tiep de dung chung
# ham doc file Vietstock va danh sach chi tieu, khong lap lai logic.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fund_pack as fp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "valuation_ck.yml")
DIVIDENDS_PATH = os.path.join(ROOT, "config", "dividends_ck.yml")
OUT_DIR = os.path.join(ROOT, "data", "packs")

TEN_KICH_BAN = {"than_trong": "Thận trọng", "co_so": "Cơ sở", "lac_quan": "Lạc quan"}


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


def qv(series_dict, key, q):
    """Lay gia tri 1 quy tu 1 metric trong dict {metric: {quy: value}}."""
    return series_dict.get(key, {}).get(q)


def g(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or cur.get(k) is None:
            return None
        cur = cur[k]
    return cur


# ----------------------------------------------------------------- #
def justified_pb(roe, gr, ke):
    if ke is None or gr is None or roe is None or ke <= gr:
        return None
    return (roe - gr) / (ke - gr)


def justified_pe(roe, gr, ke):
    if None in (roe, gr, ke) or roe == 0 or ke <= gr:
        return None
    return (1.0 - gr / roe) / (ke - gr)


def implied_roe(pb_mkt, gr, ke):
    if None in (pb_mkt, gr, ke):
        return None
    return gr + pb_mkt * (ke - gr)


def residual_income_value(bvps0, roe_path, payout_path, ke, g_term):
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
    if ke <= g_term:
        return None
    T = len(dps_path)
    pv = sum(d / (1 + ke) ** t for t, d in enumerate(dps_path, start=1))
    dps_next = dps_path[-1] * (1 + g_term)
    return pv + dps_next / ((ke - g_term) * (1 + ke) ** T)


# ----------------------------------------------------------------- #
def build_report(ticker, cstc, cdkt, kqkd, cfg, dividends=None):
    thieu = []

    all_q_cstc = fp.sort_quarters(cstc.get("EPS_TTM", {}).keys()) if cstc.get("EPS_TTM") else []
    if not all_q_cstc:
        return None, "thieu EPS_TTM trong CSTC — khong the dinh gia"
    latest_q = all_q_cstc[-1]

    eps = qv(cstc, "EPS_TTM", latest_q)
    bvps = qv(cstc, "BVPS", latest_q)
    pe = qv(cstc, "PE", latest_q)
    pb = qv(cstc, "PB", latest_q)
    roe_vs = qv(cstc, "ROE", latest_q)

    p_pe = eps * pe if None not in (eps, pe) else None
    p_pb = bvps * pb if None not in (bvps, pb) else None
    p_ref = (p_pe + p_pb) / 2.0 if (p_pe and p_pb) else None

    all_q_cdkt = fp.sort_quarters(cdkt.get("Tong_tai_san", {}).keys()) if cdkt.get("Tong_tai_san") else []
    if len(all_q_cdkt) < 2:
        thieu.append("CDKT chua du 2 quy — khong tinh duoc so du binh quan")
    q_now = all_q_cdkt[-1] if all_q_cdkt else None
    q_prev = all_q_cdkt[-2] if len(all_q_cdkt) >= 2 else None

    ta = qv(cdkt, "Tong_tai_san", q_now) if q_now else None
    fvtpl = qv(cdkt, "FVTPL_ck", q_now) if q_now else None
    loans = qv(cdkt, "Cho_vay_ck", q_now) if q_now else None
    htm_nh = qv(cdkt, "HTM_ngan_han_ck", q_now) if q_now else None
    htm_dh = qv(cdkt, "HTM_dai_han_ck", q_now) if q_now else None
    htm = (htm_nh or 0) + (htm_dh or 0) if (htm_nh is not None or htm_dh is not None) else None
    tien = qv(cdkt, "Tien_va_tuong_duong_ck", q_now) if q_now else None
    no_pt = qv(cdkt, "Tong_no_phai_tra", q_now) if q_now else None
    vay_nh = qv(cdkt, "Vay_ngan_han_ck", q_now) if q_now else None
    vcsh = qv(cdkt, "Von_chu_so_huu_ck", q_now) if q_now else None

    loans_prev = qv(cdkt, "Cho_vay_ck", q_prev) if q_prev else None
    vay_prev = qv(cdkt, "Vay_ngan_han_ck", q_prev) if q_prev else None

    ty_trong = lambda x: safe_div(x, ta)
    fvtpl_loans_share = safe_div((fvtpl or 0) + (loans or 0), ta) if ta else None
    de_ratio = safe_div(no_pt, vcsh)

    dt_mg = qv(kqkd, "DT_moi_gioi_ck", q_now) if q_now else None
    cp_mg = qv(kqkd, "CP_moi_gioi_ck", q_now) if q_now else None
    lai_cv = qv(kqkd, "Lai_cho_vay_ck", q_now) if q_now else None
    lai_htm_kq = qv(kqkd, "Lai_HTM_ck", q_now) if q_now else None
    cp_lv = qv(kqkd, "CP_lai_vay_ck", q_now) if q_now else None

    mg_gop = dt_mg - cp_mg if None not in (dt_mg, cp_mg) else None
    mg_bien = safe_div(mg_gop, dt_mg)
    nii_proxy = (lai_cv + lai_htm_kq - cp_lv) if None not in (lai_cv, lai_htm_kq, cp_lv) else None

    yield_margin = None
    if None not in (lai_cv, loans, loans_prev):
        yield_margin = lai_cv / ((loans + loans_prev) / 2.0) * 4
    funding_rate = None
    if None not in (cp_lv, vay_nh, vay_prev):
        funding_rate = cp_lv / ((vay_nh + vay_prev) / 2.0) * 4

    all_q_kqkd = fp.sort_quarters(kqkd.get("LNST", {}).keys()) if kqkd.get("LNST") else []
    ttm_qs = all_q_kqkd[-4:] if len(all_q_kqkd) >= 4 else all_q_kqkd
    if len(ttm_qs) < 4:
        thieu.append(f"KQKD chi co {len(ttm_qs)} quy — TTM chua du 4 quy chuan")

    def ttm_sum(series_dict, key):
        vals = [series_dict.get(key, {}).get(q) for q in ttm_qs]
        if any(v is None for v in vals) or not vals:
            return None
        return sum(vals)

    lnst_ttm = ttm_sum(kqkd, "LNST")

    vc_bq = None
    if len(all_q_cdkt) >= 5 and len(ttm_qs) == 4:
        try:
            idx_first_ttm = all_q_cdkt.index(ttm_qs[0])
            q_start = all_q_cdkt[idx_first_ttm - 1] if idx_first_ttm >= 1 else None
        except ValueError:
            q_start = None
        vcsh_start = qv(cdkt, "Von_chu_so_huu_ck", q_start) if q_start else None
        if None not in (vcsh_start, vcsh):
            vc_bq = (vcsh_start + vcsh) / 2.0
    if vc_bq is None:
        thieu.append("Chua tinh duoc Von chu binh quan TTM (thieu du lieu CDKT lui 5 quy)")
    roe_truc_tiep = safe_div(lnst_ttm, vc_bq)

    kb_rows, ev = [], None
    if bvps:
        ev, w_sum = 0.0, 0.0
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
        thieu.append("BVPS (CSTC) — khong tinh duoc gia tri theo P/B hop ly")

    chenh_lech = safe_div(ev - p_ref, p_ref) if None not in (ev, p_ref) else None

    ir_g = g(cfg, "implied_roe", "g")
    ir_ke = g(cfg, "implied_roe", "ke")
    roe_ham_y = implied_roe(pb, ir_g, ir_ke)

    sens = cfg.get("sensitivity", {})
    sg, s_roe, s_ke = sens.get("g"), sens.get("roe", []), sens.get("ke", [])

    du_bao_ma = g(cfg, "du_bao", ticker) or {}
    ri_cfg = du_bao_ma.get("residual_income")
    ddm_cfg = du_bao_ma.get("ddm")

    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    L = []
    A = L.append
    A(f"# VALUATION PACK — {ticker} (Ngành chứng khoán)")
    A("")
    A(f"- Kỳ báo cáo: **{latest_q}** | Sinh lúc: {now}")
    A("- Nguồn dữ liệu: file Vietstock gốc (CSTC/KQKD/CDKT) dưới `data/fundamentals/CK/"
      f"{ticker}/`, đọc qua `fund_pack.py` — không cần input thủ công.")
    A("- Phương pháp chính: **P/B hợp lý** `(ROE − g)/(Ke − g)`; kiểm tra chéo P/E hợp lý, ROE hàm ý; RI/DDM khi config có dự báo.")
    A("- Lưu ý: đây là phân tích, không phải khuyến nghị mua/bán.")
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
    A(f"Số dư cuối kỳ {q_now}, tỷ đồng (kỳ trước {q_prev or '—'} dùng để tính bình quân):")
    A("")
    A("| Chỉ tiêu | Giá trị | Tỷ trọng tài sản |")
    A("|---|---:|---:|")
    for label, val in [("Tổng tài sản", ta), ("FVTPL", fvtpl), ("Các khoản cho vay", loans),
                       ("HTM (ngắn + dài hạn)", htm), ("Tiền và tương đương", tien),
                       ("Tổng nợ phải trả", no_pt), ("Vay và nợ thuê TC ngắn hạn", vay_nh),
                       ("Vốn chủ sở hữu", vcsh)]:
        A(f"| {label} | {vnd(val)} | {pct(ty_trong(val), 1)} |")
    A("")
    A(f"- FVTPL + Cho vay / Tổng tài sản = **{pct(fvtpl_loans_share, 1)}**")
    A(f"- Đòn bẩy Nợ/VCSH = **{pct(de_ratio, 2)}**")
    A("")

    A(f"## 3. Kiểm tra nhanh hiệu quả ({q_now})")
    A("")
    A(f"- Lợi nhuận gộp môi giới = {vnd(dt_mg)} − {vnd(cp_mg)} = **{vnd(mg_gop)} tỷ** → biên gộp **{pct(mg_bien, 1)}**")
    A(f"- Thu nhập lãi thuần đại diện = {vnd(lai_cv)} + {vnd(lai_htm_kq)} − {vnd(cp_lv)} = **{vnd(nii_proxy)} tỷ**")
    A(f"- Suất sinh lời cho vay quy năm (dư nợ bình quân {q_prev}→{q_now}, ×4) = **{pct(yield_margin, 2)}**")
    A(f"- Chi phí vốn quy năm (nợ vay bình quân, ×4) = **{pct(funding_rate, 2)}**")
    A(f"- ROE trailing TTM ({', '.join(ttm_qs) if ttm_qs else '—'}) = {vnd(lnst_ttm)}/{vnd(vc_bq)} = "
      f"**{pct(roe_truc_tiep, 2)}** so với ROE quý Vietstock **{vnd(roe_vs, 2)}%**")
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
    A("")

    A("## 5. ROE mà thị giá đang kỳ vọng")
    A("")
    A(f"- Với Ke = {pct(ir_ke, 1)}, g = {pct(ir_g, 1)}, P/B = {lan(pb)}: **ROE hàm ý = {pct(roe_ham_y, 2)}**")
    if None not in (roe_ham_y, roe_truc_tiep):
        so_sanh = "CAO hơn" if roe_ham_y > roe_truc_tiep else "THẤP hơn"
        A(f"- ROE hàm ý {so_sanh} ROE trailing ({pct(roe_truc_tiep, 2)}) → chênh lệch phản ánh kỳ vọng thị trường "
          "về thanh khoản, dư nợ margin, hiệu quả tự doanh hoặc tốc độ triển khai vốn mới.")
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

    dividend_rows = (dividends or {}).get(ticker) or []
    if dividend_rows:
        A("**Lịch chia cổ tức đã công bố (tham khảo — không tự động đưa vào DDM):**")
        A("")
        A("| Năm | Loại | Giá trị | Ngày chốt | Ngày thanh toán | Ghi chú |")
        A("|---|---|---|---|---|---|")
        for d in dividend_rows:
            loai = d.get("loai", "—")
            if loai == "tien_mat":
                gia_tri = f"{vnd(d.get('dong_cp'))} đ/cp" if d.get("dong_cp") is not None else "—"
            elif loai == "co_phieu":
                gia_tri = d.get("ty_le", "—")
            else:
                gia_tri = "—"
            A(f"| {d.get('nam', '—')} | {loai} | {gia_tri} | {d.get('ngay_chot', '—')} | "
              f"{d.get('ngay_thanh_toan', '—')} | {d.get('ghi_chu', '')} |")
        A("")
        A(f"*Nguồn: config/dividends.yml, mục `co_tuc.{ticker}` — do người dùng tự ghi lại từ nghị quyết/thông báo.*")
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
        A(f"- Residual Income: **chưa có dự báo**. Thêm mục `du_bao.{ticker}.residual_income` "
          "trong config/valuation_ck.yml để kích hoạt.")
    if ddm_cfg:
        p0 = ddm_value(ddm_cfg["dps_path"], ddm_cfg["ke"], ddm_cfg["g_terminal"])
        A(f"- **DDM: P0 = {vnd(p0)} đồng/cp**")
    else:
        A(f"- DDM: **chưa có kế hoạch cổ tức dự kiến**. Thêm mục `du_bao.{ticker}.ddm` để kích hoạt"
          + (f" (tham khảo lịch sử ở bảng trên)." if dividend_rows else "."))
    A("")

    if thieu:
        A("## 8. Cảnh báo dữ liệu")
        A("")
        for t_ in thieu:
            A(f"- ⚠️ {t_}")
        A("")

    A("---")
    A("*Phương pháp KHÔNG dùng làm chính cho CTCK: EV/EBITDA, FCFF truyền thống, P/S.*")
    A("")
    A("*This is research and analysis only, not personalized financial advice.*")
    return "\n".join(L), None


# ----------------------------------------------------------------- #
def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for key, kb in cfg["kich_ban"].items():
        if kb["ke"] <= kb["g"]:
            sys.exit(f"Config lỗi: kịch bản '{key}' có Ke <= g.")

    # config/dividends.yml la file rieng, TUY CHON — khong bat buoc phai
    # ton tai. Neu chua tao hoac chua co muc "co_tuc" thi coi nhu rong,
    # khong lam gian doan cac ma khac.
    dividends = {}
    if os.path.exists(DIVIDENDS_PATH):
        with open(DIVIDENDS_PATH, encoding="utf-8") as f:
            div_cfg = yaml.safe_load(f) or {}
        dividends = div_cfg.get("co_tuc") or {}

    os.makedirs(OUT_DIR, exist_ok=True)

    by_ticker = fp.find_all_source_files(fp.FUND_DIR)
    if not by_ticker:
        print("Không tìm thấy file Vietstock nào dưới data/fundamentals/.")
        return

    ok = 0
    for ticker in sorted(by_ticker):
        by_type = by_ticker[ticker]
        missing = [t for t in ("CSTC", "KQKD", "CDKT") if t not in by_type]
        if missing:
            print(f"BỎ QUA {ticker}: thiếu file {', '.join(missing)} (định giá CTCK cần đủ cả 3).")
            continue

        cstc = fp.parse_workbook(by_type["CSTC"], fp.CSTC_METRICS)
        kqkd = fp.parse_workbook(by_type["KQKD"], fp.KQKD_METRICS)
        cdkt = fp.parse_workbook(by_type["CDKT"], fp.CDKT_METRICS)

        if not any(k.endswith("_ck") for k in cdkt) or not any(k.endswith("_ck") for k in kqkd):
            print(f"BỎ QUA {ticker}: không phải hồ sơ ngành chứng khoán (thiếu chỉ tiêu _ck).")
            continue

        report, err = build_report(ticker, cstc, cdkt, kqkd, cfg, dividends)
        if err:
            print(f"BỎ QUA {ticker}: {err}")
            continue

        out = os.path.join(OUT_DIR, f"valuation_ck_{ticker}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✓ {ticker}: {out}")
        ok += 1

    print(f"\nKẾT QUẢ: đã định giá {ok}/{len(by_ticker)} mã.")



if __name__ == "__main__":
    main()
