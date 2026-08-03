---
ma: MBB
loai: co-hoc-Q-G-V-T-D (T4c, tu dong)
---

# Diem co hoc Q-G-V-T-D — MBB

**Diem_tho: 74/100** — Tich cuc / tich luy co dieu kien
**Do tin cay du lieu (D): 55/100**
**Gia dung de tinh V: 24,000**

## Q — Chat luong (trong so 30%)
- ROE (annualize x4): gia tri 21.5% → diem 96/100 (trong so 0.20)
- ROA (annualize x4): gia tri 2.0% → diem 83/100 (trong so 0.10)
- NIM (annualize x4): gia tri 4.0% → diem 62/100 (trong so 0.15)
- CIR (khong annualize): gia tri 27.5% → diem 100/100 (trong so 0.10)
- LDR (khong annualize, Score_band): gia tri 81.5% → diem 90/100 (trong so 0.10)

## G — Tang truong (trong so 20%)
- g_LNST (YoY): gia tri 40.0% → diem 100/100 (trong so 0.30)
- g_LNTT (YoY): gia tri 40.7% → diem 100/100 (trong so 0.20)
- g_EPS (CAGR dai han, proxy): gia tri 7.5% → diem 44/100 (trong so 0.20)
- g_Tai_san (YoY): gia tri 34.4% → diem 100/100 (trong so 0.15)

## V — Dinh gia (trong so 25%)
- S_PE (tinh lai theo gia hien tai): gia tri 6.13x → diem 84/100 (trong so 0.30)
- S_PB (tinh lai theo gia hien tai): gia tri 1.23x → diem 69/100 (trong so 0.30)
- S_EY: gia tri 16.3% → diem 83/100 (trong so 0.20)

## T — Ky thuat va dong tien (trong so 20%)
- Trend (vi tri so MA20/50/200): gia tri 3/3 MA → diem 100/100 (trong so 0.25)
- Momentum (RSI+MFI): gia tri RSI 45.2 / MFI 34.5 → diem 25/100 (trong so 0.20)
- Volume (Vol/MA20 + huong OBV/VPT): gia tri 1.56x, OBV giam, VPT giam → diem 39/100 (trong so 0.20)

## Ghi chu / canh bao tu dong
- ⚠️ Fundamental Pack dang o dinh dang CU (CIR/LDR van bi annualize x4 sai). Chay lai T4b (workflow_dispatch 'Fundamental Pack (T4b)') voi fund_pack.py ban da sua truoc khi tin ket qua Q/D duoi day.
- ⚠️ Lech gia 5.0% giua Fundamental Pack (25,201) va Price Pack (24,000) — DA TU DONG dung gia Price Pack (moi hon) de tinh P/E, P/B, Earnings Yield duoi day.
- Q: THIEU NPL, LLCR, CAR (Fundamental Pack hien tai khong co) — chi cham tren 65% trong so, da renormalize ve thang 0-100.
- G: g_EPS dung CAGR dai han (Graham block) lam proxy vi khong co dong EPS rieng trong bang KQKD rut gon — neu can chinh xac hon, tinh YoY tu chuoi EPS_TTM trong bang CSTC (co san toan bo).
- V: S_MOS (Margin of Safety) BO QUA — can gia dinh Ke (chi phi von chu so huu) va g (tang truong ben vung) dang tin cay, chua co san mot cach khach quan. Neu muon tinh, dung cong thuc trong skill voi Ke/g nguoi dung tu cung cap.
- T: RelativeStrength BO QUA (can doc them data/packs/VNINDEX.md va so sanh %Δ cung giai doan — chua tu dong hoa trong script nay).
- T: chi cham tren 65% trong so co du lieu co hoc (thieu RelativeStrength).

## Phan CAN CLAUDE TONG HOP THEM (khong tu dong hoa)
- Nhan xet dinh tinh diem manh/diem yeu (dua tren cac gia tri tho o tren)
- Kich ban hanh dong (xac nhan tang / tich luy / giam rui ro) kem muc gia tu swing points
- So sanh voi cac ma ngan hang khac da co diem (khi co du lieu nhieu ma hon)
- Kiem tra chia tach/tang von truoc khi tin g_EPS, g_BVPS neu bat thuong

Day la ket qua co hoc tu dong, KHONG phai khuyen nghi mua ban. Hoi Claude truc tiep de co ban phan tich day du theo skill cham-diem-co-phieu-ngan-hang.
