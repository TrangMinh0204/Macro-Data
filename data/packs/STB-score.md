---
ma: STB
loai: co-hoc-Q-G-V-T-D (T4c, tu dong)
---

# Diem co hoc Q-G-V-T-D — STB

**Diem_tho: 30/100** — Rui ro cao / luan diem chua du manh
**Do tin cay du lieu (D): 65/100**
**Gia dung de tinh V: 71,500**

## Q — Chat luong (trong so 30%)
- ROE (annualize x4): gia tri 8.7% → diem 0/100 (trong so 0.20)
- ROA (annualize x4): gia tri 0.6% → diem 0/100 (trong so 0.10)
- NIM (annualize x4): gia tri 2.8% → diem 12/100 (trong so 0.15)
- CIR (khong annualize): gia tri 28.4% → diem 100/100 (trong so 0.10)
- LDR (khong annualize, Score_band): gia tri 78.8% → diem 92/100 (trong so 0.10)

## G — Tang truong (trong so 20%)
- g_LNST (YoY): gia tri -53.5% → diem 0/100 (trong so 0.30)
- g_LNTT (YoY): gia tri -44.5% → diem 0/100 (trong so 0.20)
- g_EPS (CAGR dai han, proxy): gia tri 12.6% → diem 57/100 (trong so 0.20)

## V — Dinh gia (trong so 25%)
- S_PE (tinh lai theo gia hien tai): gia tri 43.76x → diem 0/100 (trong so 0.30)
- S_PB (tinh lai theo gia hien tai): gia tri 2.15x → diem 4/100 (trong so 0.30)
- S_EY: gia tri 2.3% → diem 0/100 (trong so 0.20)

## T — Ky thuat va dong tien (trong so 20%)
- Trend (vi tri so MA20/50/200): gia tri 3/3 MA → diem 100/100 (trong so 0.25)
- Momentum (RSI+MFI): gia tri RSI 54.6 / MFI 63.1 → diem 72/100 (trong so 0.20)
- Volume (Vol/MA20 + huong OBV/VPT): gia tri 0.76x, OBV tang, VPT tang → diem 69/100 (trong so 0.20)

## Ghi chu / canh bao tu dong
- ⚠️ Fundamental Pack dang o dinh dang CU (CIR/LDR van bi annualize x4 sai). Chay lai T4b (workflow_dispatch 'Fundamental Pack (T4b)') voi fund_pack.py ban da sua truoc khi tin ket qua Q/D duoi day.
- Q: THIEU NPL, LLCR, CAR (Fundamental Pack hien tai khong co) — chi cham tren 65% trong so, da renormalize ve thang 0-100.
- G: g_EPS dung CAGR dai han (Graham block) lam proxy vi khong co dong EPS rieng trong bang KQKD rut gon — neu can chinh xac hon, tinh YoY tu chuoi EPS_TTM trong bang CSTC (co san toan bo).
- G: chi cham tren 70% trong so co du lieu (thieu g_BVPS rieng biet — co the tinh tu chenh lech BVPS 2 quy cach nhau 4 ky trong bang CSTC).
- V: S_MOS (Margin of Safety) BO QUA — can gia dinh Ke (chi phi von chu so huu) va g (tang truong ben vung) dang tin cay, chua co san mot cach khach quan. Neu muon tinh, dung cong thuc trong skill voi Ke/g nguoi dung tu cung cap.
- T: RelativeStrength BO QUA (can doc them data/packs/VNINDEX.md va so sanh %Δ cung giai doan — chua tu dong hoa trong script nay).
- T: chi cham tren 65% trong so co du lieu co hoc (thieu RelativeStrength).

## Phan CAN CLAUDE TONG HOP THEM (khong tu dong hoa)
- Nhan xet dinh tinh diem manh/diem yeu (dua tren cac gia tri tho o tren)
- Kich ban hanh dong (xac nhan tang / tich luy / giam rui ro) kem muc gia tu swing points
- So sanh voi cac ma ngan hang khac da co diem (khi co du lieu nhieu ma hon)
- Kiem tra chia tach/tang von truoc khi tin g_EPS, g_BVPS neu bat thuong

Day la ket qua co hoc tu dong, KHONG phai khuyen nghi mua ban. Hoi Claude truc tiep de co ban phan tich day du theo skill cham-diem-co-phieu-ngan-hang.
