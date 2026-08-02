"""
T4 — Sinh Price Pack data/packs/{MA}.md cho moi ma trong universe
(VN30 + HNX30 + watchlist + VNINDEX/HNXINDEX).

Doc lai CSV da duoc T2 ghi trong data/prices/ (khong tai lai gi tu CafeF).
Tu tinh moi chi bao/pattern-ready metric bang thu vien chuan Python
(khong dung pandas/TA-lib) de giu nhe va nhat quan voi cac script truoc.

Muc tieu: moi pack la nguyen lieu do san cho 10 skill pattern da cai
(harmonic x4, cloudbank, cup-with-handle, barr, broadening, volume-
analysis-master) — VIEC NHAN DIEN PATTERN VAN THUOC VE SKILL TRONG
CLAUDE, script nay chi tinh so, khong ket luan pattern nao dang xay ra.

Rieng graham-foundation can EPS/BVPS/BCTC — KHONG co trong file gia
CafeF, xu ly rieng o T4b (doc file Excel Vietstock).

Chi chay SAU khi T2 da PASS trong cung job (dat sau buoc T3, khong dung
if:always() -> tu dong bi skip neu T2 fail).
"""

import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import parse_prices as p2  # noqa: E402  (tai su dung load_universe)

PRICES_DIR = Path("data/prices")
PACKS_DIR = Path("data/packs")
ANOMALY_FILE = Path("output/ohlc-anomalies.md")

ZIGZAG_THRESHOLD_PCT = 5.0
MAX_PIVOTS = 30
FIB_PIVOT_COUNT = 7
PACK_SIZE_WARN_BYTES = 24_000  # ~6k token


def log(msg: str) -> None:
    print(msg, flush=True)


def load_anomalies() -> dict[str, list[str]]:
    """Doc output/ohlc-anomalies.md (T2 ghi), tra ve {ticker: [mo ta bat thuong]}."""
    if not ANOMALY_FILE.exists():
        return {}
    out: dict[str, list[str]] = {}
    pattern = re.compile(r"^- (\S+) (\d{4}-\d{2}-\d{2}): (.+)$")
    for line in ANOMALY_FILE.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            ticker, date_iso, reason = m.groups()
            out.setdefault(ticker, []).append(f"{date_iso}: {reason}")
    return out


# ---------------- doc du lieu ----------------

def read_series(ticker: str) -> list[dict] | None:
    fp = PRICES_DIR / f"{ticker}.csv"
    if not fp.exists():
        return None
    rows = []
    with fp.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d").date()
                o, h, l, c, v = (float(r["open"]), float(r["high"]),
                                  float(r["low"]), float(r["close"]), float(r["volume"]))
            except (ValueError, KeyError):
                continue
            c_raw = None
            raw_str = r.get("close_raw", "")
            if raw_str:
                try:
                    c_raw = float(raw_str)
                except ValueError:
                    pass
            rows.append({"date": d, "o": o, "h": h, "l": l, "c": c, "v": v, "c_raw": c_raw})
    rows.sort(key=lambda r: r["date"])
    return rows


def resample(rows: list[dict], period: str) -> list[dict]:
    """period: 'W' (tuan ISO) hoac 'M' (thang)."""
    buckets: dict = {}
    order = []
    for r in rows:
        key = r["date"].isocalendar()[:2] if period == "W" else (r["date"].year, r["date"].month)
        if key not in buckets:
            buckets[key] = {"date": r["date"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": 0.0}
            order.append(key)
        b = buckets[key]
        b["h"] = max(b["h"], r["h"])
        b["l"] = min(b["l"], r["l"])
        b["c"] = r["c"]
        b["date"] = r["date"]
        b["v"] += r["v"]
    return [buckets[k] for k in order]


# ---------------- chi bao co ban ----------------

def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def rsi14(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def obv_series(rows: list[dict]) -> list[float]:
    val = 0.0
    out = []
    for i in range(len(rows)):
        if i > 0:
            if rows[i]["c"] > rows[i - 1]["c"]:
                val += rows[i]["v"]
            elif rows[i]["c"] < rows[i - 1]["c"]:
                val -= rows[i]["v"]
        out.append(val)
    return out


def vpt_series(rows: list[dict]) -> list[float]:
    val = 0.0
    out = []
    for i in range(len(rows)):
        if i > 0 and rows[i - 1]["c"] != 0:
            val += rows[i]["v"] * (rows[i]["c"] - rows[i - 1]["c"]) / rows[i - 1]["c"]
        out.append(val)
    return out


def mfi14(rows: list[dict], period: int = 14) -> float | None:
    if len(rows) < period + 1:
        return None
    tp = [(r["h"] + r["l"] + r["c"]) / 3 for r in rows]
    mf = [tp[i] * rows[i]["v"] for i in range(len(rows))]
    pos = neg = 0.0
    start = len(rows) - period
    for i in range(max(start, 1), len(rows)):
        if tp[i] > tp[i - 1]:
            pos += mf[i]
        elif tp[i] < tp[i - 1]:
            neg += mf[i]
    if neg == 0:
        return 100.0
    return 100 - 100 / (1 + pos / neg)


# ---------------- ZigZag + Fibonacci ----------------

def zigzag(rows: list[dict], threshold_pct: float = ZIGZAG_THRESHOLD_PCT) -> list[dict]:
    if len(rows) < 2:
        return []
    pivots = []
    trend = None
    ext_idx, ext_price = 0, rows[0]["c"]
    last_pivot_price = rows[0]["c"]
    for i in range(1, len(rows)):
        c = rows[i]["c"]
        if trend is None:
            if c >= last_pivot_price * (1 + threshold_pct / 100):
                trend, ext_idx, ext_price = "up", i, c
            elif c <= last_pivot_price * (1 - threshold_pct / 100):
                trend, ext_idx, ext_price = "down", i, c
            continue
        if trend == "up":
            if c > ext_price:
                ext_price, ext_idx = c, i
            elif c <= ext_price * (1 - threshold_pct / 100):
                pivots.append({"date": rows[ext_idx]["date"], "price": ext_price, "type": "H"})
                trend, ext_price, ext_idx = "down", c, i
        else:
            if c < ext_price:
                ext_price, ext_idx = c, i
            elif c >= ext_price * (1 + threshold_pct / 100):
                pivots.append({"date": rows[ext_idx]["date"], "price": ext_price, "type": "L"})
                trend, ext_price, ext_idx = "up", c, i
    if trend is not None:
        pivots.append({
            "date": rows[ext_idx]["date"], "price": ext_price,
            "type": "H" if trend == "up" else "L", "unconfirmed": True,
        })
    return pivots


def fib_leg_ratios(pivots: list[dict], n: int = FIB_PIVOT_COUNT) -> list[dict]:
    """Tra ve ty le % giua cac chan lien tiep tu n pivot gan nhat."""
    pts = pivots[-n:]
    if len(pts) < 3:
        return []
    legs = []
    for i in range(1, len(pts)):
        length = abs(pts[i]["price"] - pts[i - 1]["price"])
        legs.append({"from": pts[i - 1], "to": pts[i], "length": length})
    ratios = []
    for i in range(1, len(legs)):
        prev, cur = legs[i - 1], legs[i]
        if prev["length"] == 0:
            continue
        ratios.append({
            "label": f"L{i+1}/L{i}",
            "from_date": cur["from"]["date"], "from_type": cur["from"]["type"],
            "to_date": cur["to"]["date"], "to_type": cur["to"]["type"],
            "ratio_pct": cur["length"] / prev["length"] * 100,
        })
    return ratios


# ---------------- pattern-ready metrics rieng ----------------

def cloudbank_metrics(weekly_rows: list[dict]) -> dict:
    closes = [w["c"] for w in weekly_rows]
    sma30w = sma(closes, 30)
    latest = closes[-1] if closes else None
    ath = max((w["h"] for w in weekly_rows), default=None)
    atl = min((w["l"] for w in weekly_rows), default=None)
    return {
        "sma30w": sma30w,
        "vs_sma30w_pct": ((latest - sma30w) / sma30w * 100) if (sma30w and latest) else None,
        "ath": ath,
        "drawdown_from_ath_pct": ((latest - ath) / ath * 100) if (ath and latest) else None,
        "atl": atl,
        "recovery_from_atl_pct": ((latest - atl) / atl * 100) if (atl and latest) else None,
    }


def cup_metrics(daily_rows: list[dict]) -> dict | None:
    closes = [r["c"] for r in daily_rows]
    highs = [r["h"] for r in daily_rows]
    if len(closes) < 90:
        return None
    latest = closes[-1]
    high_52w = max(highs[-252:]) if len(highs) >= 252 else max(highs)
    rim = max(closes[-90:])
    out = {
        "dist_to_52w_high_pct": (latest - high_52w) / high_52w * 100 if high_52w else None,
        "depth_from_rim_90d_pct": (latest - rim) / rim * 100 if rim else None,
        "uptrend_6m_proxy_pct": None,
    }
    if len(closes) >= 190:
        base = closes[-190]
        peak_before = max(closes[-190:-90])
        if base:
            out["uptrend_6m_proxy_pct"] = (peak_before - base) / base * 100
    return out


def fmt_vol(v: float) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return f"{v:.0f}"


def fmt_num(x: float | None, digits: int = 2) -> str:
    return f"{x:.{digits}f}" if x is not None else "N/A"


# ---------------- lap rap pack ----------------

def build_pack(ticker: str, rows: list[dict], ticker_anomalies: list[str] | None = None) -> str:
    daily60 = rows[-60:]
    weekly_all = resample(rows, "W")
    monthly_all = resample(rows, "M")
    weekly52 = weekly_all[-52:]
    monthly60 = monthly_all[-60:]
    closes_all = [r["c"] for r in rows]
    vols_all = [r["v"] for r in rows]

    ma20 = sma(closes_all, 20)
    ma50 = sma(closes_all, 50)
    ma200 = sma(closes_all, 200)
    rsi = rsi14(closes_all)
    vol_ma20 = sma(vols_all, 20)
    vol_ratio = (rows[-1]["v"] / vol_ma20) if vol_ma20 else None
    highs_all = [r["h"] for r in rows]
    lows_all = [r["l"] for r in rows]
    high52w = max(highs_all[-252:]) if len(highs_all) >= 252 else max(highs_all)
    low52w = min(lows_all[-252:]) if len(lows_all) >= 252 else min(lows_all)

    c_raw_vals = [r["c_raw"] for r in rows if r["c_raw"] is not None]
    raw_high = max(c_raw_vals[-252:]) if len(c_raw_vals) >= 252 else (max(c_raw_vals) if c_raw_vals else None)
    raw_low = min(c_raw_vals[-252:]) if len(c_raw_vals) >= 252 else (min(c_raw_vals) if c_raw_vals else None)

    pivots = zigzag(rows)
    pivots_recent = pivots[-MAX_PIVOTS:]
    fib_ratios = fib_leg_ratios(pivots)

    cb = cloudbank_metrics(weekly_all) if len(weekly_all) >= 5 else None
    cup = cup_metrics(rows)

    obv = obv_series(rows)
    vpt = vpt_series(rows)
    mfi = mfi14(rows)
    obv_dir = None
    vpt_dir = None
    if len(obv) > 20:
        obv_dir = "tang" if obv[-1] > obv[-20] else ("giam" if obv[-1] < obv[-20] else "di ngang")
    if len(vpt) > 20:
        vpt_dir = "tang" if vpt[-1] > vpt[-20] else ("giam" if vpt[-1] < vpt[-20] else "di ngang")

    L = []
    last_date = rows[-1]["date"].isoformat()
    L.append("---")
    L.append(f"ma: {ticker}")
    L.append(f"ngay_du_lieu_gan_nhat: {last_date}")
    L.append(f"so_phien_daily: {len(rows)}")
    if len(rows) < 252:
        L.append("canh_bao: lich su duoi 1 nam — mot so chi bao (52w, cloudbank) co the khong day du")
    L.append("---")
    L.append("")
    L.append(f"# Price Pack — {ticker}")
    L.append("")

    if ticker_anomalies:
        L.append("## ⚠️ Canh bao du lieu")
        L.append("Phat hien dong O/H/L/C bat thuong tu nguon CafeF cho ma nay — "
                 "KHONG dung cac ngay duoi day cho phan tich nen/order flow "
                 "(cac chi bao khac trong pack khong bi anh huong dang ke):")
        for a in ticker_anomalies:
            L.append(f"- {a}")
        L.append("")

    L.append("## Chi bao tinh san")
    L.append(f"- MA20/50/200: {fmt_num(ma20)} / {fmt_num(ma50)} / {fmt_num(ma200)}")
    L.append(f"- RSI14: {fmt_num(rsi, 1)}")
    L.append(f"- Volume/MA20vol: {fmt_num(vol_ratio, 2)}x")
    L.append(f"- 52w High/Low (dieu chinh): {fmt_num(high52w)} / {fmt_num(low52w)}")
    if raw_high is not None:
        L.append(f"- Dinh/day 52w (CHUA dieu chinh, muc gia tam ly): {fmt_num(raw_high)} / {fmt_num(raw_low)}")
    L.append(f"- OBV: {fmt_num(obv[-1] if obv else None, 0)} (huong 20 phien: {obv_dir or 'N/A'})")
    L.append(f"- VPT: {fmt_num(vpt[-1] if vpt else None, 0)} (huong 20 phien: {vpt_dir or 'N/A'})")
    L.append(f"- MFI14: {fmt_num(mfi, 1)}")
    L.append("")

    if cb:
        L.append("## Cloudbank metrics (Bulkowski Ch.18)")
        L.append(f"- 30-week SMA: {fmt_num(cb['sma30w'])} | Gia hien tai vs SMA: {fmt_num(cb['vs_sma30w_pct'])}%")
        L.append(f"- ATH (theo lich su co du lieu): {fmt_num(cb['ath'])} | Drawdown tu ATH: {fmt_num(cb['drawdown_from_ath_pct'])}%")
        L.append(f"- ATL: {fmt_num(cb['atl'])} | Hoi phuc tu ATL: {fmt_num(cb['recovery_from_atl_pct'])}%")
        L.append("")

    if cup:
        L.append("## Cup with Handle metrics (proxy)")
        L.append(f"- Khoang cach toi 52w high: {fmt_num(cup['dist_to_52w_high_pct'])}%")
        L.append(f"- Do sau tu rim (dinh 90 phien gan nhat): {fmt_num(cup['depth_from_rim_90d_pct'])}%")
        L.append(f"- Uptrend 6 thang truoc (proxy, ~190->90 phien truoc): {fmt_num(cup['uptrend_6m_proxy_pct'])}%")
        L.append("")

    L.append(f"## Swing points (ZigZag {ZIGZAG_THRESHOLD_PCT:.0f}%) — {len(pivots_recent)} pivot gan nhat")
    for p in pivots_recent:
        tag = " (chua xac nhan)" if p.get("unconfirmed") else ""
        L.append(f"- {p['date'].isoformat()} {p['type']} {fmt_num(p['price'])}{tag}")
    L.append("")

    if fib_ratios:
        L.append(f"## Ma tran ty le Fibonacci ({FIB_PIVOT_COUNT} pivot gan nhat)")
        L.append("Ty le do dai chan sau / chan lien truoc — doi chieu voi 38.2/50/61.8/78.6/88.6/127.2/161.8% de nhan dien harmonic (viec nay thuoc skill, khong phai script).")
        for r in fib_ratios:
            L.append(f"- {r['label']} ({r['from_type']}{r['from_date'].isoformat()} -> "
                     f"{r['to_type']}{r['to_date'].isoformat()}): {fmt_num(r['ratio_pct'], 1)}%")
        L.append("")

    L.append(f"## Daily — 60 phien gan nhat (date,O,H,L,C,V)")
    for r in daily60:
        L.append(f"{r['date'].strftime('%y%m%d')},{fmt_num(r['o'])},{fmt_num(r['h'])},"
                 f"{fmt_num(r['l'])},{fmt_num(r['c'])},{fmt_vol(r['v'])}")
    L.append("")

    L.append(f"## Weekly — {len(weekly52)} tuan gan nhat (date,O,H,L,C,V)")
    for r in weekly52:
        L.append(f"{r['date'].strftime('%y%m%d')},{fmt_num(r['o'])},{fmt_num(r['h'])},"
                 f"{fmt_num(r['l'])},{fmt_num(r['c'])},{fmt_vol(r['v'])}")
    L.append("")

    L.append(f"## Monthly — {len(monthly60)} thang gan nhat (date,O,H,L,C,V)")
    for r in monthly60:
        L.append(f"{r['date'].strftime('%y%m%d')},{fmt_num(r['o'])},{fmt_num(r['h'])},"
                 f"{fmt_num(r['l'])},{fmt_num(r['c'])},{fmt_vol(r['v'])}")
    L.append("")

    L.append("## Gioi han")
    L.append("- Pack nay CHI co du lieu gia (khong co EPS/BVPS/BCTC) — phan dinh gia Graham "
             "dung file rieng data/packs/{MA}-fund.md (T4b, doc tu file Excel Vietstock user upload).")

    return "\n".join(L) + "\n"


def main() -> int:
    price_date = os.environ.get("PRICE_DATE")
    if not price_date:
        log("LOI: khong co PRICE_DATE.")
        return 1

    log(f"=== T4 — Sinh Price Pack === ngay: {p2.d8_to_iso(price_date)}")

    universe = p2.load_universe()
    universe |= {"VNINDEX", "HNXINDEX"}
    log(f"  Tong so ma can sinh pack: {len(universe)}")

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    anomalies = load_anomalies()
    if anomalies:
        log(f"  Doc duoc canh bao O/H/L/C cho {len(anomalies)} ma tu {ANOMALY_FILE}: {sorted(anomalies.keys())}")

    ok, skipped, oversized = 0, [], []
    for ticker in sorted(universe):
        rows = read_series(ticker)
        if not rows or len(rows) < 10:
            skipped.append(ticker)
            continue
        content = build_pack(ticker, rows, anomalies.get(ticker))
        out_fp = PACKS_DIR / f"{ticker}.md"
        out_fp.write_text(content, encoding="utf-8")
        size = out_fp.stat().st_size
        if size > PACK_SIZE_WARN_BYTES:
            oversized.append((ticker, size))
        ok += 1

    log(f"\nDa sinh {ok}/{len(universe)} pack vao {PACKS_DIR}/")
    if skipped:
        log(f"  Bo qua (khong du du lieu, co the vua them vao watchlist): {skipped}")
    if oversized:
        log(f"  CANH BAO vuot nguong {PACK_SIZE_WARN_BYTES} bytes: {oversized}")

    log("\nKET QUA: PASS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
