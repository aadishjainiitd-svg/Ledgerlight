"""Generate three demo GST tax invoices for Ledgerlight (all vendors and banks are fictional).

    backend/.venv/Scripts/python demo_invoices/make_demo_invoices.py

Upload them via New run -> upload:
  01  Brightline  BLS/26-27/0801  PO-2026-0985  clean, matches PO and bank   -> Auto-approve
  02  Greenleaf   GPS/26-27/0227  PO-2026-1007  paper cups 5% above PO price -> Needs review (R10)
  03  Meridian    MLX/26-27/2146  PO-2026-1009  new bank account + notice    -> On hold (R05)

It reuses the drawing helpers from samples/make_samples.py (imported, not modified).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "samples"))
from make_samples import BUYER, RUPEE, SANS, SANS_B, Pdf, amt, qty, wrap, words_in_rupees  # noqa: E402


def tax_invoice(path, *, vendor, accent, number, date, po, lines, gst_rate, bank, notice=None,
                code_hdr="Item Code", hsn_hdr="HSN"):
    v = vendor
    p = Pdf(path, f"Invoice {number}")
    p.rect(40, 40, 34, 34, fill=accent, stroke=None)
    p.t(57, 63, v["name"][0], SANS_B, 20, "#ffffff", "center")
    p.t(84, 54, v["name"], SANS_B, 15, accent)
    p.t(84, 68, v["addr"], SANS, 8.5, "#4a5568")
    p.t(84, 80, f"GSTIN: {v['gstin']}   Phone: {v['phone']}", SANS, 8.5, "#4a5568")
    p.t(84, 92, v["email"], SANS, 8.5, "#4a5568")
    p.t(555, 56, "TAX INVOICE", SANS_B, 18, accent, "right")
    y = 74
    for k, val in [("Invoice No:", number), ("Invoice Date:", date), ("PO Number:", po),
                   ("Terms:", f"Net {v['terms']}")]:
        p.t(420, y, k, SANS, 8.5, "#4a5568")
        p.t(555, y, val, SANS_B, 8.5, "#1d2433", "right")
        y += 13
    p.line(40, 132, 555, 132, accent, 1.2)
    p.t(40, 150, "BILL TO", SANS_B, 8, accent)
    p.t(40, 163, BUYER[0], SANS_B, 9.5)
    p.t(40, 175, BUYER[1], SANS, 8.5, "#4a5568")
    p.t(40, 187, f"GSTIN: {BUYER[2]}", SANS, 8.5, "#4a5568")
    p.t(330, 150, "PLACE OF SUPPLY", SANS_B, 8, accent)
    p.t(330, 163, "Maharashtra (27)", SANS, 9)
    cols = [("#", 40, 58, "left"), (code_hdr, 60, 128, "left"), ("Description", 130, 300, "left"),
            (hsn_hdr, 302, 345, "left"), ("Qty", 347, 395, "right"), ("Unit", 399, 432, "left"),
            (f"Rate ({RUPEE})", 434, 488, "right"), (f"Amount ({RUPEE})", 490, 555, "right")]
    ty = 210
    p.rect(40, ty, 515, 20, fill="#eef1f6", stroke="#9aa7c0")
    for name, x0, x1, al in cols:
        p.t(x1 - 3 if al == "right" else x0 + 3, ty + 13.5, name, SANS_B, 8, accent, al)
    y = ty + 20
    sub = 0.0
    for i, ln in enumerate(lines, 1):
        dl = wrap(ln["desc"], SANS, 8.5, 164)
        h = 8 + 11 * len(dl)
        p.rect(40, y, 515, h, stroke="#c9cfdb")
        for _, x0, _x1, _al in cols[1:]:
            p.line(x0, y, x0, y + h)
        base = y + 13
        p.t(43, base, str(i), SANS, 8.5)
        p.t(63, base, ln["code"], SANS, 8.5)
        for j, d in enumerate(dl):
            p.t(133, base + 11 * j, d, SANS, 8.5)
        p.t(305, base, ln["hsn"], SANS, 8.5)
        p.t(392, base, qty(ln["qty"]), SANS, 8.5, align="right")
        p.t(402, base, ln["uom"], SANS, 8.5)
        p.t(485, base, amt(ln["rate"]), SANS, 8.5, align="right")
        a = round(ln["qty"] * ln["rate"], 2)
        sub += a
        p.t(552, base, amt(a), SANS, 8.5, align="right")
        y += h
    half = gst_rate / 2
    cg = round(sub * half / 100, 2)
    total = round(sub + 2 * cg, 2)
    y += 16
    for k, val in [("Taxable Value", amt(sub)), (f"CGST @ {half:g}%", amt(cg)), (f"SGST @ {half:g}%", amt(cg))]:
        p.t(420, y, k, SANS, 9, "#4a5568")
        p.t(552, y, val, SANS, 9, align="right")
        y += 14
    p.rect(410, y - 4, 145, 20, fill=accent, stroke=None)
    p.t(420, y + 10, f"Total ({RUPEE})", SANS_B, 10, "#ffffff")
    p.t(552, y + 10, amt(total), SANS_B, 10, "#ffffff", "right")
    p.t(40, y - 26, "Amount in words:", SANS_B, 8, accent)
    for j, wl in enumerate(wrap(words_in_rupees(int(round(total))), SANS, 8, 330)):
        p.t(40, y - 14 + 11 * j, wl, SANS, 8, "#4a5568")
    y += 50
    p.t(40, y, "BANK DETAILS", SANS_B, 8, accent)
    p.t(40, y + 13, f"Bank: {bank['bank']}   A/c No: {bank['acct']}   IFSC: {bank['ifsc']}   "
                    f"Branch: {bank['branch']}", SANS, 8.5)
    yy = y + 27
    if notice:
        p.t(40, yy, notice, SANS_B, 8.5, "#9b1c1c")
        yy += 13
    p.t(40, yy + 14, f"Terms: Payment due within {v['terms']} days of invoice date. Goods and services once "
                     f"supplied will not be taken back.", SANS, 7.5, "#6b7280")
    p.t(555, yy + 44, f"For {v['name']}", SANS, 8, "#4a5568", "right")
    p.t(555, yy + 74, "Authorised Signatory", SANS_B, 8, "#1d2433", "right")
    p.t(297, 815, "This is a computer generated invoice.", SANS, 7, "#9aa3b2", "center")
    p.save()
    return sub, 2 * cg, total


BRIGHTLINE = dict(name="Brightline Office Supplies Pvt Ltd", gstin="27AAFCB4821K1Z3",
                  addr="14 Dockyard Road, Mumbai 400010", phone="+91 22 4018 2290",
                  email="accounts@brightline-supplies.example", terms=30)
GREENLEAF = dict(name="Greenleaf Pantry Supplies", gstin="27AAJFG9054R1Z2", addr="5 Market Yard, Pune 411037",
                 phone="+91 20 4410 6035", email="orders@greenleafpantry.example", terms=15)
MERIDIAN = dict(name="Meridian Logistics Pvt Ltd", gstin="27AABCM6620D1Z9",
                addr="Gala 12, Andheri East, Mumbai 400093", phone="+91 22 6120 5544",
                email="billing@meridian-logistics.example", terms=30)


def main():
    jobs = [
        ("01_happy_brightline_BLS-26-27-0801.pdf", dict(
            vendor=BRIGHTLINE, accent="#1f3a68", number="BLS/26-27/0801", date="14 Nov 2026", po="PO-2026-0985",
            gst_rate=18,
            lines=[dict(code="TNR-BK", desc="Black toner cartridge", hsn="8443", qty=20, uom="nos", rate=3450)],
            bank=dict(bank="Harbor Union Bank", acct="0123 4567 8901", ifsc="HUBK0000214", branch="Fort, Mumbai"))),
        ("02_price_over_po_greenleaf_GPS-26-27-0227.pdf", dict(
            vendor=GREENLEAF, accent="#2f6b3a", number="GPS/26-27/0227", date="15 Nov 2026", po="PO-2026-1007",
            gst_rate=12,
            lines=[dict(code="PNT-CUP", desc="Paper cup 150 ml", hsn="4823", qty=10000, uom="nos", rate=1.68),
                   dict(code="PNT-STR", desc="Wooden stirrer", hsn="4421", qty=8000, uom="nos", rate=0.40)],
            bank=dict(bank="Lakeview Bank", acct="3300 1275 5508", ifsc="LKVB0000318",
                      branch="Shivajinagar, Pune"))),
        ("03_bank_change_meridian_MLX-26-27-2146.pdf", dict(
            vendor=MERIDIAN, accent="#245c3a", number="MLX/26-27/2146", date="16 Nov 2026", po="PO-2026-1009",
            gst_rate=18, code_hdr="Service Code", hsn_hdr="SAC",
            lines=[dict(code="FR-MUM-PUN", desc="Full-truck haulage Mumbai to Pune (1-15 Nov 2026)", hsn="996511",
                        qty=5, uom="trips", rate=14500)],
            bank=dict(bank="Summit Mercantile Bank", acct="6104 2275 8830", ifsc="SMBK0000377",
                      branch="Andheri East, Mumbai"),
            notice="Please note: our bank details have changed. Kindly remit all payments to the account above.")),
    ]
    for f, kw in jobs:
        sub, tax, tot = tax_invoice(HERE / f, **kw)
        print(f"{f}  taxable {sub:,.2f}  tax {tax:,.2f}  total {tot:,.2f}")


if __name__ == "__main__":
    main()
