"""
T4e — Tinh Money Flow Score (chi so dong tien tong hop) cap ma va cap
nganh, theo cong thuc: MoneyFlowScore = 0.25*Z(Return) + 0.20*Z(GTGD) +
0.20*Z(CMF) + 0.20*Z(RS) + 0.15*Z(OBV_Change), Z-score chuan hoa tren
cua so 20 phien. Doc truc tiep bang "Daily 60 phien gan nhat" co san
trong Price Pack (data/packs/{MA}.md) — KHONG can tai lai du lieu tho.

Cap nganh (SectorLiquidityRatio, SectorShare, Breadth, RS_sector) dung
config/sectors.yml lam nguon nhom ma — file nay TRUOC DAY chi la tham
khao, TU SCRIPT NAY TRO DI duoc code doc that de gom nhom. Neu ban doi
danh sach ma trong file do, ket qua nganh se doi theo.

Quy tac xac nhan dong tien: dem so dieu kien dung trong 6 dieu kien
chuan (gia > MA20 va MA20 huong len, KL > 1.2x MA20, CMF20 > 0, OBV >
MA20(OBV), RS20 > 0, dong cua nam trong 30% tren bien do phien) — tu 4/6
tro len coi la da xac nhan.
"""

import re
import sys
import statistics
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

PACKS_DIR = Path("data/packs")
SECTORS_FILE = Path("config/sectors.yml")
ZSCORE_WINDOW = 20  # so phien dung de tinh MA/STDEV chuan hoa Z-score
CMF_WINDOW = 20


def log(msg: str) -> None:
    print(msg, flush=True)


def read_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def parse_daily_series(text: str) -> list[dict]:
    """Doc bang 'Daily N phien gan nhat' trong Price Pack, tra ve list
    dict {date, o, h, l, c, v} sap xep CU -> MOI (de tinh chuoi thuan)."""
    m = re.search(r"## Daily.*?\n(.*?)\n\n", text, re.S)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        parts = line.strip().split(",")
        if len(parts) != 6:
            continue
        date8, o, h, l, c, v_raw = parts
        try:
            v = float(v_raw[:-1]) * (1e6 if v_raw.endswith("M") else 1e3 if v_raw.endswith("K") else 1)
            rows.append({
                "date": date8, "o": float(o), "h": float(h),
                "l": float(l), "c": float(c), "v": v,
            })
        except ValueError:
            continue
    return rows  # da o dang cu -> moi tu file goc


def compute_daily_metrics(rows: list[dict]) -> list[dict]:
    """Tinh GTGD, Return, CLV, MFV, OBV cho tung phien tu chuoi O/H/L/C/V tho."""
    out = []
    obv = 0.0
    prev_close = None
    for r in rows:
        gtgd = r["c"] * r["v"]
        ret = (r["c"] / prev_close - 1) if prev_close else None
        rng = r["h"] - r["l"]
        clv = ((r["c"] - r["l"]) - (r["h"] - r["c"])) / rng if rng > 0 else 0.0
        mfv = clv * r["v"]
        if prev_close is not None:
            if r["c"] > prev_close:
                obv += r["v"]
            elif r["c"] < prev_close:
                obv -= r["v"]
        out.append({**r, "gtgd": gtgd, "return": ret, "clv": clv, "mfv": mfv, "obv": obv})
        prev_close = r["c"]
    return out


def zscore(series: list[float], window: int) -> float | None:
    """Z-score cua gia tri CUOI CUNG so voi MA/STDEV cua window gan nhat
    (khong tinh chinh no vao mau — dung n phien TRUOC do lam nen)."""
    if len(series) < window + 1:
        return None
    base = series[-(window + 1):-1]
    x_t = series[-1]
    mean = statistics.fmean(base)
    try:
        std = statistics.stdev(base)
    except statistics.StatisticsError:
        return None
    if std == 0:
        return None
    return (x_t - mean) / std


def compute_ma(series: list[float], window: int) -> float | None:
    if len(series) < window:
        return None
    return statistics.fmean(series[-window:])


def load_price_pack(ticker: str) -> list[dict] | None:
    fp = PACKS_DIR / f"{ticker}.md"
    if not fp.exists():
        return None
    rows = parse_daily_series(fp.read_text(encoding="utf-8"))
    if len(rows) < ZSCORE_WINDOW + 5:
        return None
    return compute_daily_metrics(rows)


def compute_rs(stock_metrics: list[dict], index_metrics: list[dict], n: int) -> float | None:
    """RS_n = (Close_stock,t/Close_stock,t-n) / (Index_t/Index_t-n) - 1.
    Can it nhat n+1 phien khop ngay o ca 2 chuoi."""
    if len(stock_metrics) < n + 1 or len(index_metrics) < n + 1:
        return None
    s_now, s_prev = stock_metrics[-1]["c"], stock_metrics[-1 - n]["c"]
    i_now, i_prev = index_metrics[-1]["c"], index_metrics[-1 - n]["c"]
    if s_prev == 0 or i_prev == 0 or i_now == 0:
        return None
    return (s_now / s_prev) / (i_now / i_prev) - 1


def compute_moneyflow_for_ticker(ticker: str, metrics: list[dict], index_metrics: list[dict] | None) -> dict:
    returns = [m["return"] for m in metrics if m["return"] is not None]
    gtgds = [m["gtgd"] for m in metrics]
    volumes = [m["v"] for m in metrics]
    obvs = [m["obv"] for m in metrics]

    # CMF cuon CMF_WINDOW phien
    cmf_series = []
    for i in range(len(metrics)):
        if i + 1 < CMF_WINDOW:
            continue
        window = metrics[i + 1 - CMF_WINDOW:i + 1]
        sum_mfv = sum(w["mfv"] for w in window)
        sum_vol = sum(w["v"] for w in window)
        cmf_series.append(sum_mfv / sum_vol if sum_vol else 0.0)

    obv_change_series = [obvs[i] - obvs[i - ZSCORE_WINDOW] for i in range(ZSCORE_WINDOW, len(obvs))]

    z_return = zscore(returns, ZSCORE_WINDOW) if len(returns) >= ZSCORE_WINDOW + 1 else None
    z_gtgd = zscore(gtgds, ZSCORE_WINDOW)
    z_cmf = zscore(cmf_series, ZSCORE_WINDOW) if len(cmf_series) >= ZSCORE_WINDOW + 1 else None
    z_obv_change = zscore(obv_change_series, ZSCORE_WINDOW) if len(obv_change_series) >= ZSCORE_WINDOW + 1 else None

    rs20 = compute_rs(metrics, index_metrics, 20) if index_metrics else None
    z_rs = None
    if index_metrics:
        rs_series = []
        for n_back in range(ZSCORE_WINDOW, 0, -1):
            sub_stock = metrics[:len(metrics) - n_back + 1] if n_back > 1 else metrics
            sub_index = index_metrics[:len(index_metrics) - n_back + 1] if n_back > 1 else index_metrics
            rs_v = compute_rs(sub_stock, sub_index, 20)
            if rs_v is not None:
                rs_series.append(rs_v)
        if len(rs_series) >= ZSCORE_WINDOW + 1:
            z_rs = zscore(rs_series, ZSCORE_WINDOW)

    weighted = [(z_return, 0.25), (z_gtgd, 0.20), (z_cmf, 0.20), (z_rs, 0.20), (z_obv_change, 0.15)]
    available = [(z, w) for z, w in weighted if z is not None]
    score = None
    weight_used = sum(w for _, w in available)
    if available:
        score = sum(z * w for z, w in available) / weight_used * weight_used
        score = sum(z * w for z, w in available)  # KHONG renormalize — thieu phan nao thi diem thap hon that

    # ---- Quy tac xac nhan 4/6 ----
    last = metrics[-1]
    ma20_close = compute_ma([m["c"] for m in metrics], 20)
    ma20_close_prev = compute_ma([m["c"] for m in metrics[:-1]], 20)
    vol_ma20 = compute_ma([m["v"] for m in metrics], 20)
    obv_ma20 = compute_ma(obvs, 20)
    rng = last["h"] - last["l"]
    close_pos = (last["c"] - last["l"]) / rng if rng > 0 else None

    conditions = {
        "Gia > MA20 va MA20 huong len": (
            ma20_close is not None and ma20_close_prev is not None
            and last["c"] > ma20_close and ma20_close > ma20_close_prev),
        "KL > 1.2x MA20(KL)": vol_ma20 is not None and last["v"] > 1.2 * vol_ma20,
        "CMF20 > 0": bool(cmf_series) and cmf_series[-1] > 0,
        "OBV > MA20(OBV)": obv_ma20 is not None and obvs[-1] > obv_ma20,
        "RS20 > 0": rs20 is not None and rs20 > 0,
        "Dong cua trong 30% tren bien do phien": close_pos is not None and close_pos >= 0.7,
    }
    so_dieu_kien_dung = sum(1 for v in conditions.values() if v)

    return {
        "ticker": ticker, "score": score, "weight_used": weight_used,
        "z_return": z_return, "z_gtgd": z_gtgd, "z_cmf": z_cmf, "z_rs": z_rs,
        "z_obv_change": z_obv_change, "rs20": rs20,
        "cmf20": cmf_series[-1] if cmf_series else None,
        "conditions": conditions, "so_dieu_kien_dung": so_dieu_kien_dung,
        "last_date": last["date"], "last_close": last["c"], "last_gtgd": last["gtgd"],
    }


def classify_score(score: float | None) -> str:
    if score is None:
        return "Khong du du lieu"
    if score > 1:
        return "Dong tien vao MANH"
    if score > 0.3:
        return "Dong tien vao cai thien"
    if score >= -0.3:
        return "Trung tinh hoac tich luy"
    if score >= -1:
        return "Dong tien suy yeu"
    return "Dong tien ra MANH"


def build_stock_output(r: dict) -> str:
    L = []
    L.append("---")
    L.append(f"ma: {r['ticker']}")
    L.append("loai: money-flow-score (T4e, tu dong)")
    L.append(f"ngay_du_lieu: {r['last_date']}")
    L.append("---")
    L.append("")
    L.append(f"# Money Flow Score — {r['ticker']}")
    L.append("")
    score_str = f"{r['score']:.2f}" if r["score"] is not None else "N/A"
    L.append(f"**MoneyFlowScore: {score_str}** — {classify_score(r['score'])}")
    if r["weight_used"] < 0.95:
        L.append(f"(chi tinh tren {r['weight_used']*100:.0f}% trong so co du lieu — "
                 f"xem ghi chu thanh phan thieu ben duoi)")
    L.append(f"**Xac nhan dong tien: {r['so_dieu_kien_dung']}/6 dieu kien** "
             f"({'DA XAC NHAN' if r['so_dieu_kien_dung'] >= 4 else 'CHUA du xac nhan'})")
    L.append("")

    L.append("## Cac cau phan Z-score")
    for label, val in (("Z(Return)", r["z_return"]), ("Z(GTGD)", r["z_gtgd"]),
                        ("Z(CMF20)", r["z_cmf"]), ("Z(RS20 vs VNINDEX)", r["z_rs"]),
                        ("Z(OBV Change 20 phien)", r["z_obv_change"])):
        L.append(f"- {label}: {val:.2f}" if val is not None else f"- {label}: N/A")
    L.append("")
    if r["z_rs"] is None:
        L.append("LUU Y: Z(RS) can data/packs/VNINDEX.md (Price Pack cua VNINDEX) de so sanh — "
                 "neu N/A, kiem tra file nay co ton tai va du >= 40 phien khong.")
        L.append("")

    L.append("## Gia tri tho quy chieu")
    L.append(f"- Dong cua gan nhat ({r['last_date']}): {r['last_close']}")
    L.append(f"- GTGD phien gan nhat: {r['last_gtgd']:,.0f}")
    if r["cmf20"] is not None:
        L.append(f"- CMF20: {r['cmf20']:.3f}")
    if r["rs20"] is not None:
        L.append(f"- RS20 vs VNINDEX: {r['rs20']*100:.2f}%")
    L.append("")

    L.append("## Chi tiet 6 dieu kien xac nhan")
    for cond, ok in r["conditions"].items():
        L.append(f"- [{'x' if ok else ' '}] {cond}")
    L.append("")

    L.append("Day la chi so dinh luong tu dong, KHONG phai khuyen nghi mua ban. Doi chieu voi "
             "phan tich dinh tinh (tin tuc, KQKD, nhom nganh dong pha) truoc khi hanh dong.")
    return "\n".join(L) + "\n"


def load_sectors() -> dict[str, list[str]]:
    if yaml is None:
        log("  CANH BAO: chua cai pyyaml, khong doc duoc config/sectors.yml — bo qua cap nganh.")
        return {}
    if not SECTORS_FILE.exists():
        log(f"  CANH BAO: khong thay {SECTORS_FILE} — bo qua cap nganh.")
        return {}
    with open(SECTORS_FILE, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {k: v for k, v in raw.items() if isinstance(v, list)}


def compute_sector_moneyflow(sector_name: str, tickers: list[str],
                              all_metrics: dict[str, list[dict]],
                              index_metrics: list[dict] | None,
                              all_gtgd_market: list[float]) -> dict | None:
    members = [(t, all_metrics[t]) for t in tickers if t in all_metrics]
    if len(members) < 2:
        return None

    sector_gtgd_series = []
    n_days = min(len(m) for _, m in members)
    for i in range(-n_days, 0):
        sector_gtgd_series.append(sum(m[i]["gtgd"] for _, m in members))

    ma20_sector_gtgd = compute_ma(sector_gtgd_series, 20)
    sector_liquidity_ratio = (sector_gtgd_series[-1] / ma20_sector_gtgd) if ma20_sector_gtgd else None

    sector_share_series = []
    for i in range(min(len(sector_gtgd_series), len(all_gtgd_market))):
        idx = -(i + 1)
        if all_gtgd_market[idx]:
            sector_share_series.insert(0, sector_gtgd_series[idx] / all_gtgd_market[idx])
    delta_sector_share = None
    if len(sector_share_series) >= 21:
        ma20_share = compute_ma(sector_share_series[:-1], 20)
        if ma20_share:
            delta_sector_share = sector_share_series[-1] - ma20_share

    above_ma20 = 0
    for t, m in members:
        closes = [x["c"] for x in m]
        ma20 = compute_ma(closes, 20)
        if ma20 and closes[-1] > ma20:
            above_ma20 += 1
    breadth = above_ma20 / len(members) * 100

    rs_sector = None
    if index_metrics and len(index_metrics) >= 21:
        sector_closes_now = sum(m[-1]["c"] for _, m in members)
        sector_closes_prev = sum(m[-21]["c"] for _, m in members if len(m) >= 21)
        if sector_closes_prev:
            sector_return = sector_closes_now / sector_closes_prev - 1
            idx_return = index_metrics[-1]["c"] / index_metrics[-21]["c"] - 1
            rs_sector = sector_return - idx_return

    z_liq = zscore(sector_gtgd_series, min(20, len(sector_gtgd_series) - 1)) if len(sector_gtgd_series) > 20 else None

    parts = [(z_liq, 0.25)]
    weight_used = sum(w for z, w in parts if z is not None)
    score = sum(z * w for z, w in parts if z is not None) if weight_used else None

    return {
        "sector": sector_name, "n_members": len(members),
        "tickers": [t for t, _ in members],
        "sector_liquidity_ratio": sector_liquidity_ratio,
        "delta_sector_share": delta_sector_share,
        "breadth": breadth, "rs_sector": rs_sector,
        "score_partial": score,
    }


def build_sector_output(r: dict) -> str:
    L = []
    L.append("---")
    L.append(f"nganh: {r['sector']}")
    L.append("loai: sector-money-flow-score (T4e, tu dong)")
    L.append("---")
    L.append("")
    L.append(f"# Sector Money Flow — {r['sector']}")
    L.append("")
    L.append(f"So ma co du lieu: {r['n_members']} ({', '.join(r['tickers'])})")
    L.append("")
    L.append("## Chi so")
    slr = r["sector_liquidity_ratio"]
    L.append(f"- SectorLiquidityRatio: {slr:.2f}" if slr is not None else "- SectorLiquidityRatio: N/A")
    dss = r["delta_sector_share"]
    L.append(f"- ΔSectorShare: {dss*100:.2f} diem %" if dss is not None else "- ΔSectorShare: N/A")
    L.append(f"- Breadth (>MA20): {r['breadth']:.0f}%")
    rss = r["rs_sector"]
    L.append(f"- RS_sector (vs VNINDEX): {rss*100:.2f} diem %" if rss is not None else "- RS_sector: N/A")
    L.append("")
    L.append("## Dieu kien xac nhan dong tien nganh (tham khao)")
    checks = []
    if slr is not None:
        checks.append(("SectorLiquidityRatio > 1", slr > 1))
    if dss is not None:
        checks.append(("ΔSectorShare > 0", dss > 0))
    if rss is not None:
        checks.append(("RS_sector > 0", rss > 0))
    checks.append(("Breadth > 50%", r["breadth"] > 50))
    for label, ok in checks:
        L.append(f"- [{'x' if ok else ' '}] {label}")
    L.append("")
    L.append("LUU Y: SectorShare tinh tren TONG GTGD CAC MA DANG THEO DOI trong he thong "
             "(VN30+HNX30+watchlist), KHONG PHAI GTGD toan thi truong that — la xap xi, khong "
             "phai ty trong chinh xac 100%.")
    L.append("")
    L.append("Day la chi so dinh luong tu dong, KHONG phai khuyen nghi mua ban.")
    return "\n".join(L) + "\n"


def main() -> int:
    if not PACKS_DIR.exists():
        log("Khong co data/packs/ — khong co gi de lam.")
        return 0

    price_packs = sorted(p.stem for p in PACKS_DIR.glob("*.md")
                          if not p.stem.endswith(("-fund", "-score", "-kcn", "-moneyflow"))
                          and p.stem not in ("VNINDEX", "HNXINDEX"))
    log(f"Tim thay {len(price_packs)} ma co Price Pack.")

    index_metrics = None
    idx_fp = PACKS_DIR / "VNINDEX.md"
    if idx_fp.exists():
        idx_rows = parse_daily_series(idx_fp.read_text(encoding="utf-8"))
        if len(idx_rows) >= ZSCORE_WINDOW + 25:
            index_metrics = compute_daily_metrics(idx_rows)
            log(f"  Da doc VNINDEX.md: {len(index_metrics)} phien.")
        else:
            log(f"  CANH BAO: VNINDEX.md chi co {len(idx_rows)} phien, thieu de tinh RS/Z-score day du.")
    else:
        log("  CANH BAO: khong co data/packs/VNINDEX.md — bo qua RS, chi tinh 4/5 thanh phan Z-score.")

    all_metrics = {}
    all_gtgd_market = None
    ok = 0
    for ticker in price_packs:
        metrics = load_price_pack(ticker)
        if metrics is None:
            continue
        all_metrics[ticker] = metrics
        r = compute_moneyflow_for_ticker(ticker, metrics, index_metrics)
        content = build_stock_output(r)
        out_fp = PACKS_DIR / f"{ticker}-moneyflow.md"
        out_fp.write_text(content, encoding="utf-8")
        score_str = f"{r['score']:.2f}" if r["score"] is not None else "N/A"
        log(f"  {ticker}: MoneyFlowScore={score_str}, xac nhan {r['so_dieu_kien_dung']}/6")
        ok += 1

    # ---- Tong GTGD toan bo ma dang theo doi (proxy cho "thi truong") ----
    if all_metrics:
        n_days = min(len(m) for m in all_metrics.values())
        all_gtgd_market = [sum(m[-n_days + i]["gtgd"] for m in all_metrics.values())
                           for i in range(n_days)]

    sectors = load_sectors()
    sector_ok = 0
    if sectors and all_gtgd_market:
        log(f"\nTinh Money Flow cap nganh cho {len(sectors)} nhom: {list(sectors.keys())}")
        for sector_name, tickers in sectors.items():
            r = compute_sector_moneyflow(sector_name, tickers, all_metrics, index_metrics, all_gtgd_market)
            if r is None:
                log(f"  {sector_name}: BO QUA — chua du 2 ma co Price Pack trong nhom.")
                continue
            content = build_sector_output(r)
            out_fp = PACKS_DIR / f"_sector-{sector_name}-moneyflow.md"
            out_fp.write_text(content, encoding="utf-8")
            log(f"  {sector_name}: {r['n_members']} ma, Breadth={r['breadth']:.0f}%, da ghi {out_fp}")
            sector_ok += 1

    log(f"\nKET QUA: {ok}/{len(price_packs)} ma cap ma, {sector_ok} nhom cap nganh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
