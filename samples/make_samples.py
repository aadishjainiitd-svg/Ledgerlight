"""Generate Ledgerlight's sample invoice PDFs (spec section 9.4 / 9.5).

    python samples/make_samples.py          (use the backend venv: backend/.venv/Scripts/python)

Writes SI-01..SI-07, the three history PDFs (history/), and expected.json. Every vendor, GSTIN,
bank account and person is fictional. Layouts are deliberately different (classic grid, compact
tax-inclusive, modern card, boxed dot-matrix, freight, handwritten carbon copy) so the extractor
cannot depend on one template.

SI-05 (Greenleaf, EC3) is an image-only degraded scan with NO text layer: it can only be read by the
vision model. SI-04 (Brightline re-scan, EC2) is a phone photo saved by a scanning app, which embeds
an invisible OCR text layer under the photo (a common real-world format); the visible page is a
skewed, blurred photo.
"""
from __future__ import annotations

import io
import json
import math
import os
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent
HIST = OUT / "history"
W, H = A4
BUYER = ("Halcyon Foods Pvt Ltd", "Unit 4, Kalina Business Park, Santacruz East, Mumbai 400098",
         "27AAGCH5521L1Z7")

# ------------------------------------------------------------------ fonts
FONT_DIRS = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu"),
             Path("/Library/Fonts"), Path("/usr/share/fonts")]


def _find(*names):
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                return str(p)
    return None


def _reg(alias, *names, fallback="Helvetica"):
    p = _find(*names)
    if p:
        try:
            pdfmetrics.registerFont(TTFont(alias, p))
            return alias, True
        except Exception:
            pass
    return fallback, False


SANS, HAS_TTF = _reg("LL-Sans", "arial.ttf", "DejaVuSans.ttf")
SANS_B, _ = _reg("LL-Sans-B", "arialbd.ttf", "DejaVuSans-Bold.ttf", fallback="Helvetica-Bold")
MONO, _ = _reg("LL-Mono", "cour.ttf", "DejaVuSansMono.ttf", fallback="Courier")
MONO_B, _ = _reg("LL-Mono-B", "courbd.ttf", "DejaVuSansMono-Bold.ttf", fallback="Courier-Bold")
SERIF, _ = _reg("LL-Serif", "georgia.ttf", "DejaVuSerif.ttf", fallback="Times-Roman")
SERIF_B, _ = _reg("LL-Serif-B", "georgiab.ttf", "DejaVuSerif-Bold.ttf", fallback="Times-Bold")
HAND, _ = _reg("LL-Hand", "segoepr.ttf", "Inkfree.ttf", "comic.ttf", fallback="Helvetica-Oblique")
RUPEE = "₹" if HAS_TTF else "Rs."


def amt(rupees: float) -> str:
    """Indian grouping: 118000 -> '1,18,000.00'."""
    neg = rupees < 0
    s = f"{abs(rupees):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + "." + frac


def qty(q: float) -> str:
    q = int(q) if float(q).is_integer() else q
    return amt(q)[:-3] if isinstance(q, int) else str(q)


class Pdf:
    def __init__(self, path: Path | io.BytesIO, title: str):
        self.c = canvas.Canvas(path if isinstance(path, io.BytesIO) else str(path), pagesize=A4)
        self.c.setTitle(title)
        self.c.setAuthor("Ledgerlight sample generator (fictional data)")

    def t(self, x, y, s, font=None, size=9, color="#1d2433", align="left"):
        c = self.c
        c.setFillColor(HexColor(color))
        c.setFont(font or SANS, size)
        yy = H - y
        if align == "right":
            c.drawRightString(x, yy, s)
        elif align == "center":
            c.drawCentredString(x, yy, s)
        else:
            c.drawString(x, yy, s)

    def line(self, x0, y0, x1, y1, color="#c9cfdb", width=0.6):
        self.c.setStrokeColor(HexColor(color))
        self.c.setLineWidth(width)
        self.c.line(x0, H - y0, x1, H - y1)

    def rect(self, x, y, w, h, fill=None, stroke="#c9cfdb", width=0.6, radius=0):
        c = self.c
        c.setLineWidth(width)
        if stroke:
            c.setStrokeColor(HexColor(stroke))
        if fill:
            c.setFillColor(HexColor(fill))
        if radius:
            c.roundRect(x, H - y - h, w, h, radius, stroke=1 if stroke else 0, fill=1 if fill else 0)
        else:
            c.rect(x, H - y - h, w, h, stroke=1 if stroke else 0, fill=1 if fill else 0)

    def save(self):
        self.c.showPage()
        self.c.save()


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    out, cur = [], ""
    for wd in text.split():
        trial = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            if cur:
                out.append(cur)
            cur = wd
    if cur:
        out.append(cur)
    return out


def words_in_rupees(n: int) -> str:
    ones = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    tens = "  twenty thirty forty fifty sixty seventy eighty ninety".split(" ")

    def two(x):
        return ones[x] if x < 20 else tens[x // 10] + ("-" + ones[x % 10] if x % 10 else "")

    def three(x):
        h, r = divmod(x, 100)
        return ((ones[h] + " hundred" + (" " if r else "")) if h else "") + (two(r) if r else "")

    parts = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thou, n = divmod(n, 1000)
    if crore:
        parts.append(three(crore) + " crore")
    if lakh:
        parts.append(two(lakh) + " lakh")
    if thou:
        parts.append(two(thou) + " thousand")
    if n:
        parts.append(three(n))
    return ("Rupees " + " ".join(parts) + " only").replace("  ", " ").capitalize()


# ------------------------------------------------------------------ vendors (master data mirror)
BRIGHTLINE = dict(name="Brightline Office Supplies Pvt Ltd", gstin="27AAFCB4821K1Z3",
                  addr="14 Dockyard Road, Mumbai 400010", phone="+91 22 4018 2290",
                  email="accounts@brightline-supplies.example", bank="Harbor Union Bank",
                  acct="0123 4567 8901", ifsc="HUBK0000214")
COREVOLT = dict(name="Corevolt Electronics Pvt Ltd", gstin="29AAHCC7710M1Z8",
                addr="22 Electronic City Phase 1, Bengaluru 560100", phone="+91 80 4125 7700",
                email="billing@corevolt-electronics.example", bank="Harbor Union Bank",
                acct="0001 2345 6789", ifsc="HUBK0000101")
KESTREL = dict(name="Kestrel Print & Pack", gstin="24AAMFK3302Q1Z6", addr="Plot 88, GIDC Vatva, Ahmedabad 382445",
               phone="+91 79 4003 1182", email="accounts@kestrelpack.example", bank="Delta Savings Bank",
               acct="7712 0034 2214", ifsc="DLSB0000220")
GREENLEAF = dict(name="Greenleaf Pantry Supplies", gstin="27AAJFG9054R1Z2", addr="5 Market Yard, Pune 411037",
                 phone="+91 20 4410 6035")
MERIDIAN = dict(name="Meridian Logistics Pvt Ltd", gstin="27AABCM6620D1Z9",
                addr="Gala 12, Andheri East, Mumbai 400093", phone="+91 22 6120 5544",
                email="billing@meridian-logistics.example", bank="Delta Savings Bank", acct="7712 0098 4410",
                ifsc="DLSB0000220")


# ------------------------------------------------------------------ layout A: classic grid (Brightline)
def layout_classic(path, *, number, date, po, lines, cgst_rate=9.0, title="TAX INVOICE"):
    v = BRIGHTLINE
    p = Pdf(path, f"Invoice {number}")
    navy = "#1f3a68"
    p.rect(40, 40, 34, 34, fill=navy, stroke=None)
    p.t(57, 63, "B", SANS_B, 20, "#ffffff", "center")
    p.t(84, 54, v["name"], SANS_B, 15, navy)
    p.t(84, 68, v["addr"], SANS, 8.5, "#4a5568")
    p.t(84, 80, f"GSTIN: {v['gstin']}   Phone: {v['phone']}", SANS, 8.5, "#4a5568")
    p.t(84, 92, v["email"], SANS, 8.5, "#4a5568")
    p.t(555, 56, title, SANS_B, 18, navy, "right")
    meta = [("Invoice No:", number), ("Invoice Date:", date), ("PO Number:", po), ("Terms:", "Net 30")]
    y = 74
    for k, val in meta:
        p.t(420, y, k, SANS, 8.5, "#4a5568")
        p.t(555, y, val, SANS_B, 8.5, "#1d2433", "right")
        y += 13
    p.line(40, 132, 555, 132, navy, 1.2)
    p.t(40, 150, "BILL TO", SANS_B, 8, navy)
    p.t(40, 163, BUYER[0], SANS_B, 9.5)
    p.t(40, 175, BUYER[1], SANS, 8.5, "#4a5568")
    p.t(40, 187, f"GSTIN: {BUYER[2]}", SANS, 8.5, "#4a5568")
    p.t(330, 150, "PLACE OF SUPPLY", SANS_B, 8, navy)
    p.t(330, 163, "Maharashtra (27)", SANS, 9)
    # table
    cols = [("#", 40, 58, "left"), ("Item Code", 60, 120, "left"), ("Description", 122, 300, "left"),
            ("HSN", 302, 340, "left"), ("Qty", 342, 390, "right"), ("Unit", 396, 430, "left"),
            (f"Rate ({RUPEE})", 432, 488, "right"), (f"Amount ({RUPEE})", 490, 555, "right")]
    ty = 210
    p.rect(40, ty, 515, 20, fill="#e8edf6", stroke="#9aa7c0")
    for name, x0, x1, al in cols:
        p.t(x1 - 3 if al == "right" else x0 + 3, ty + 13.5, name, SANS_B, 8, navy, al)
    y = ty + 20
    sub = 0.0
    for i, ln in enumerate(lines, 1):
        dl = wrap(ln["desc"], SANS, 8.5, 172)
        h = 8 + 11 * len(dl)
        p.rect(40, y, 515, h, stroke="#c9cfdb")
        for _, x0, x1, _al in cols[1:]:
            p.line(x0, y, x0, y + h)
        base = y + 13
        p.t(43, base, str(i), SANS, 8.5)
        p.t(63, base, ln["code"], SANS, 8.5)
        for j, dline in enumerate(dl):
            p.t(125, base + 11 * j, dline, SANS, 8.5)
        p.t(305, base, ln.get("hsn", ""), SANS, 8.5)
        p.t(387, base, qty(ln["qty"]), SANS, 8.5, align="right")
        p.t(399, base, ln["uom"], SANS, 8.5)
        p.t(485, base, amt(ln["rate"]), SANS, 8.5, align="right")
        a = ln["qty"] * ln["rate"]
        sub += a
        p.t(552, base, amt(a), SANS, 8.5, align="right")
        y += h
    cg = round(sub * cgst_rate / 100, 2)
    total = sub + 2 * cg
    y += 16
    rows = [("Taxable Value", amt(sub)), (f"CGST @ {cgst_rate:g}%", amt(cg)), (f"SGST @ {cgst_rate:g}%", amt(cg))]
    for k, val in rows:
        p.t(420, y, k, SANS, 9, "#4a5568")
        p.t(552, y, val, SANS, 9, align="right")
        y += 14
    p.rect(410, y - 4, 145, 20, fill="#1f3a68", stroke=None)
    p.t(420, y + 10, f"Total ({RUPEE})", SANS_B, 10, "#ffffff")
    p.t(552, y + 10, amt(total), SANS_B, 10, "#ffffff", "right")
    p.t(40, y - 26, "Amount in words:", SANS_B, 8, navy)
    for j, wl in enumerate(wrap(words_in_rupees(int(total)), SANS, 8, 330)):
        p.t(40, y - 14 + 11 * j, wl, SANS, 8, "#4a5568")
    y += 50
    p.t(40, y, "BANK DETAILS", SANS_B, 8, navy)
    p.t(40, y + 13, f"Bank: {v['bank']}   A/c No: {v['acct']}   IFSC: {v['ifsc']}   Branch: Fort, Mumbai", SANS, 8.5)
    p.t(40, y + 40, "Terms: Payment due within 30 days of invoice date. Goods once sold will not be taken back.",
        SANS, 7.5, "#6b7280")
    p.t(555, y + 70, f"For {v['name']}", SANS, 8, "#4a5568", "right")
    p.t(555, y + 100, "Authorised Signatory", SANS_B, 8, "#1d2433", "right")
    p.t(297, 815, "This is a computer generated invoice.", SANS, 7, "#9aa3b2", "center")
    p.save()
    return dict(subtotal=sub, tax=2 * cg, total=total)


# ------------------------------------------------------------------ layout B: compact, tax inclusive (Corevolt)
def layout_compact(path):
    v = COREVOLT
    p = Pdf(path, "Invoice CV-8841")
    p.t(40, 52, "COREVOLT ELECTRONICS PVT LTD", SERIF_B, 15, "#14213d")
    p.t(40, 66, f"GSTIN {v['gstin']}  |  {v['addr']}  |  {v['phone']}", SERIF, 8, "#555")
    p.line(40, 74, 555, 74, "#14213d", 1.5)
    p.t(40, 94, "Invoice # CV-8841", SERIF_B, 11)
    p.t(555, 94, "Date: 09-Nov-2026", SERIF, 10, align="right")
    p.t(40, 114, f"To: {BUYER[0]}, {BUYER[1]}", SERIF, 9)
    p.t(40, 126, f"Buyer GSTIN: {BUYER[2]}   Place of supply: Maharashtra (27)", SERIF, 9)
    p.t(40, 150, "Ref your PO 1002/2026 dated 12 Oct 2026. Supplied as per your order, delivered 7 Nov 2026.",
        SERIF, 9.5)
    ty = 172
    p.line(40, ty, 555, ty, "#14213d", 0.8)
    p.t(44, ty + 13, "Particulars", SERIF_B, 9)
    p.t(372, ty + 13, "Qty", SERIF_B, 9, align="right")
    p.t(470, ty + 13, "Rate incl. GST (Rs.)", SERIF_B, 9, align="right")
    p.t(552, ty + 13, "Amount (Rs.)", SERIF_B, 9, align="right")
    p.line(40, ty + 19, 555, ty + 19, "#14213d", 0.8)
    desc = "IT peripherals supply: docking stations and wireless keyboard-mouse sets, 30 each"
    for j, dl in enumerate(wrap(desc, SERIF, 9.5, 260)):
        p.t(44, ty + 35 + 12 * j, dl, SERIF, 9.5)
    p.t(372, ty + 35, "30 sets", SERIF, 9.5, align="right")
    p.t(470, ty + 35, amt(10779.30), SERIF, 9.5, align="right")
    p.t(552, ty + 35, amt(323379), SERIF, 9.5, align="right")
    p.line(40, ty + 64, 555, ty + 64, "#14213d", 0.8)
    p.t(330, ty + 84, "Amount payable", SERIF_B, 10.5)
    p.t(552, ty + 84, "Rs. " + amt(323379), SERIF_B, 10.5, align="right")
    p.t(40, ty + 112, "All prices are inclusive of IGST @ 18%. IGST included in the amount: Rs. 49,329.00",
        SERIF, 8.5, "#333")
    p.t(40, ty + 124, "(Rupees three lakh twenty-three thousand three hundred seventy-nine only)", SERIF, 8.5, "#333")
    p.t(40, ty + 150, f"Payment: {v['bank']}, A/c {v['acct']}, IFSC {v['ifsc']}. Terms: Net 45.", SERIF, 8.5)
    p.t(40, ty + 162, "Warranty: 12 months from delivery. Please quote the invoice number with any query.", SERIF, 8, "#666")
    p.t(555, ty + 200, "for Corevolt Electronics Pvt Ltd", SERIF, 8.5, "#333", "right")
    p.t(555, ty + 226, "Authorised signatory", SERIF, 8.5, "#333", "right")
    p.save()


# ------------------------------------------------------------------ layout C: modern card (Corevolt)
def layout_card(path):
    v = COREVOLT
    p = Pdf(path, "Invoice CV-8902")
    teal = "#0f4c5c"
    p.rect(0, 0, W, 96, fill=teal, stroke=None)
    p.t(40, 46, "Corevolt Electronics", SANS_B, 22, "#ffffff")
    p.t(40, 64, f"{v['name']}  ·  GSTIN {v['gstin']}", SANS, 8.5, "#cfe3e8")
    p.t(40, 77, f"{v['addr']}  ·  {v['phone']}", SANS, 8.5, "#cfe3e8")
    p.t(555, 52, "INVOICE", SANS_B, 26, "#ffffff", "right")
    cards = [("INVOICE NO", "CV-8902"), ("DATE", "13 Nov 2026"), ("PURCHASE ORDER", "PO-2026-1008"),
             ("AMOUNT DUE", "INR 1,66,380.00")]
    x = 40
    for lab, val in cards:
        p.rect(x, 116, 120, 46, fill="#f2f7f8", stroke="#d5e3e7", radius=5)
        p.t(x + 10, 132, lab, SANS_B, 7, "#5b7c86")
        p.t(x + 10, 150, val, SANS_B, 10.5, "#11252b")
        x += 131
    p.t(40, 190, "BILLED TO", SANS_B, 7.5, "#5b7c86")
    p.t(40, 203, BUYER[0], SANS_B, 9.5)
    p.t(40, 215, BUYER[1], SANS, 8.5, "#4a5568")
    p.t(40, 227, f"GSTIN {BUYER[2]}", SANS, 8.5, "#4a5568")
    p.t(330, 190, "SHIP TO", SANS_B, 7.5, "#5b7c86")
    p.t(330, 203, "Halcyon Foods - IT Store, Mumbai", SANS, 9)
    ty = 252
    p.t(44, ty, "ITEM", SANS_B, 7.5, "#5b7c86")
    p.t(110, ty, "DESCRIPTION", SANS_B, 7.5, "#5b7c86")
    p.t(380, ty, "QTY", SANS_B, 7.5, "#5b7c86", "right")
    p.t(462, ty, "PRICE (INR)", SANS_B, 7.5, "#5b7c86", "right")
    p.t(552, ty, "TOTAL (INR)", SANS_B, 7.5, "#5b7c86", "right")
    items = [("NS-24P", "24-port managed switch, layer 2+, rack mount", 6, 21000),
             ("PC-CAT6", "Cat6 patch cable 2 m, blue", 60, 250)]
    y = ty + 8
    sub = 0
    for i, (code, desc, q, r) in enumerate(items):
        p.rect(40, y, 515, 24, fill="#f7fafb" if i % 2 == 0 else "#ffffff", stroke=None)
        p.t(44, y + 15.5, code, SANS, 9)
        p.t(110, y + 15.5, desc, SANS, 9)
        p.t(380, y + 15.5, f"{q} nos", SANS, 9, align="right")
        p.t(462, y + 15.5, amt(r), SANS, 9, align="right")
        p.t(552, y + 15.5, amt(q * r), SANS, 9, align="right")
        sub += q * r
        y += 24
    tax = round(sub * 0.18, 2)
    y += 22
    for k, val in [("Subtotal", amt(sub)), ("IGST 18%", amt(tax))]:
        p.t(400, y, k, SANS, 9, "#4a5568")
        p.t(552, y, val, SANS, 9, align="right")
        y += 15
    p.line(400, y - 6, 555, y - 6, teal, 1)
    p.t(400, y + 8, "Total due", SANS_B, 11, teal)
    p.t(552, y + 8, "INR " + amt(sub + tax), SANS_B, 11, teal, "right")
    y += 60
    p.rect(40, y, 515, 56, fill="#f2f7f8", stroke="#d5e3e7", radius=5)
    p.t(52, y + 16, "PAYMENT DETAILS", SANS_B, 7.5, "#5b7c86")
    p.t(52, y + 31, "Remit to: Riverbend Co-operative Bank   A/c No: 5020 0091 2334 7   IFSC: RBCB0000412",
        SANS_B, 9, "#11252b")
    p.t(52, y + 45, "Payment terms: Net 45. Please quote CV-8902 as the payment reference.", SANS, 8, "#4a5568")
    p.t(40, y + 84, "Our bank details have changed with effect from 1 Nov 2026. Please remit to Riverbend "
                    "Co-operative Bank, A/c 5020 0091 2334 7.", SANS, 6.8, "#6b7280")
    p.t(40, y + 94, "Kindly update your records. Payments made to the old account after this date may be delayed.",
        SANS, 6.8, "#6b7280")
    p.t(297, 812, "Thank you for your business  ·  billing@corevolt-electronics.example", SANS, 7.5, "#9aa3b2", "center")
    p.save()


# ------------------------------------------------------------------ layout D: boxed dot-matrix (Kestrel)
def layout_boxed(path, *, number, date, lot, lines):
    v = KESTREL
    p = Pdf(path, f"Invoice {number}")
    ink = "#202020"
    p.rect(36, 36, 523, 770, stroke=ink, width=1.2)
    p.rect(40, 40, 515, 762, stroke=ink, width=0.5)
    p.t(297, 66, "KESTREL PRINT & PACK", MONO_B, 17, ink, "center")
    p.t(297, 80, v["addr"], MONO, 8.5, ink, "center")
    p.t(297, 92, f"GSTIN: {v['gstin']}  Ph: {v['phone']}", MONO, 8.5, ink, "center")
    p.line(40, 102, 555, 102, ink, 0.8)
    p.t(297, 118, "TAX INVOICE", MONO_B, 12, ink, "center")
    p.line(40, 126, 555, 126, ink, 0.8)
    p.line(297, 126, 297, 196, ink, 0.8)
    left = [("Inv No", number), ("Inv Date", date), ("Order Ref", "PO-2026-1004"), ("Lot", lot)]
    y = 142
    for k, val in left:
        p.t(48, y, f"{k:<10}: {val}", MONO, 9, ink)
        y += 14
    p.t(305, 142, "Buyer:", MONO_B, 9, ink)
    p.t(305, 156, BUYER[0], MONO, 9, ink)
    p.t(305, 170, "Santacruz East, Mumbai 400098", MONO, 9, ink)
    p.t(305, 184, f"GSTIN: {BUYER[2]}", MONO, 9, ink)
    p.line(40, 196, 555, 196, ink, 0.8)
    cols = [("Code", 44), ("Description", 120), ("Qty", 352), ("UOM", 362), ("Rate", 456), ("Amount", 551)]
    p.t(44, 212, "Code", MONO_B, 9, ink)
    p.t(120, 212, "Description", MONO_B, 9, ink)
    p.t(350, 212, "Qty", MONO_B, 9, ink, "right")
    p.t(362, 212, "UOM", MONO_B, 9, ink)
    p.t(456, 212, "Rate", MONO_B, 9, ink, "right")
    p.t(551, 212, "Amount", MONO_B, 9, ink, "right")
    p.line(40, 218, 555, 218, ink, 0.5)
    y = 234
    sub = 0
    for ln in lines:
        dl = wrap(ln["desc"], MONO, 8.5, 168)
        p.t(44, y, ln["code"], MONO, 8.5, ink)
        for j, d in enumerate(dl):
            p.t(120, y + 12 * j, d, MONO, 8.5, ink)
        p.t(350, y, qty(ln["qty"]), MONO, 8.5, ink, "right")
        p.t(362, y, ln["uom"], MONO, 8.5, ink)
        p.t(456, y, amt(ln["rate"]), MONO, 8.5, ink, "right")
        a = ln["qty"] * ln["rate"]
        sub += a
        p.t(551, y, amt(a), MONO, 8.5, ink, "right")
        y += 12 * len(dl) + 10
    p.line(40, 420, 555, 420, ink, 0.5)
    tax = round(sub * 0.18, 2)
    y = 438
    for k, val in [("Taxable Amt", amt(sub)), ("IGST 18%", amt(tax))]:
        p.t(330, y, k, MONO, 9, ink)
        p.t(551, y, val, MONO, 9, ink, "right")
        y += 14
    p.line(325, y - 6, 555, y - 6, ink, 0.5)
    p.t(330, y + 8, "Grand Total Rs.", MONO_B, 10, ink)
    p.t(551, y + 8, amt(sub + tax), MONO_B, 10, ink, "right")
    p.t(48, 438, "E. & O.E.", MONO, 8, ink)
    p.t(48, 452, "Goods dispatched by road,", MONO, 8, ink)
    p.t(48, 464, "LR enclosed.", MONO, 8, ink)
    p.line(40, 520, 555, 520, ink, 0.5)
    p.t(48, 538, "Bank:", MONO_B, 9, ink)
    p.t(48, 552, f"{v['bank']}  A/c No. {v['acct']}  IFSC {v['ifsc']}", MONO, 8.5, ink)
    p.t(551, 620, "For KESTREL PRINT & PACK", MONO, 8.5, ink, "right")
    p.t(551, 660, "Proprietor", MONO, 8.5, ink, "right")
    p.t(297, 790, "SUBJECT TO AHMEDABAD JURISDICTION", MONO, 7.5, ink, "center")
    p.save()


# ------------------------------------------------------------------ layout E: freight (Meridian)
def layout_freight(path):
    v = MERIDIAN
    p = Pdf(path, "Invoice MX-5530")
    green = "#245c3a"
    p.t(40, 56, "MERIDIAN", SANS_B, 24, green)
    p.t(40, 72, "LOGISTICS PVT LTD", SANS_B, 10, "#3d7a55")
    p.t(40, 88, f"{v['addr']}  ·  {v['phone']}", SANS, 8, "#555")
    p.t(40, 99, f"GSTIN {v['gstin']}  ·  PAN AABCM6620D", SANS, 8, "#555")
    p.t(555, 56, "TAX INVOICE", SANS_B, 14, "#222", "right")
    p.t(555, 70, "Original for Recipient", SANS, 8, "#777", "right")
    p.rect(40, 116, 515, 62, fill="#f4f8f5", stroke="#cfe0d5")
    grid = [("Invoice No.", "MX-5530", 52, 134), ("Invoice Date", "11 November 2026", 52, 152),
            ("PO Reference", "PO-2026-1009", 52, 170), ("Customer", BUYER[0], 300, 134),
            ("Customer GSTIN", BUYER[2], 300, 152), ("Place of Supply", "Maharashtra (27)", 300, 170)]
    for k, val, x, y in grid:
        p.t(x, y, k, SANS, 8.5, "#557")
        p.t(x + 88, y, val, SANS_B, 8.5, "#222")
    ty = 200
    p.rect(40, ty, 515, 20, fill=green, stroke=None)
    hdr = [("S.No", 46, "left"), ("Description of Service", 80, "left"), ("SAC", 300, "left"),
           ("Trips", 372, "right"), (f"Rate per Trip ({RUPEE})", 470, "right"), (f"Amount ({RUPEE})", 551, "right")]
    for n, x, al in hdr:
        p.t(x, ty + 13.5, n, SANS_B, 8, "#ffffff", al)
    y = ty + 36
    p.t(46, y, "1", SANS, 9)
    p.t(80, y, "Full-truck freight Mumbai to Pune", SANS, 9)
    p.t(80, y + 12, "(32 ft MXL, 1-30 Nov 2026)", SANS, 7.5, "#666")
    p.t(300, y, "996511", SANS, 9)
    p.t(372, y, "12", SANS, 9, align="right")
    p.t(470, y, amt(14500), SANS, 9, align="right")
    p.t(551, y, amt(174000), SANS, 9, align="right")
    p.line(40, y + 26, 555, y + 26, "#cfe0d5")
    y += 50
    for k, val in [("Total Taxable Value", amt(174000)), ("CGST @ 9%", amt(10660)), ("SGST @ 9%", amt(10660))]:
        p.t(360, y, k, SANS, 9, "#444")
        p.t(551, y, val, SANS, 9, align="right")
        y += 15
    p.rect(355, y - 5, 200, 22, fill="#e3efe7", stroke=None)
    p.t(360, y + 10, "Invoice Total", SANS_B, 10.5, green)
    p.t(551, y + 10, f"{RUPEE} " + amt(195320), SANS_B, 10.5, green, "right")
    y += 50
    p.t(40, y, "Amount in words: Rupees one lakh ninety-five thousand three hundred twenty only", SANS, 8, "#444")
    p.t(40, y + 24, f"Bank: {v['bank']}, Account No. {v['acct']}, IFSC {v['ifsc']}", SANS, 8.5)
    p.t(40, y + 36, "Whether tax is payable on reverse charge: No", SANS, 8, "#666")
    p.t(555, y + 80, "For Meridian Logistics Pvt Ltd", SANS, 8.5, "#444", "right")
    p.t(555, y + 108, "Authorised Signatory", SANS_B, 8.5, "#222", "right")
    p.save()


# ------------------------------------------------------------------ layout F: handwritten carbon copy (Greenleaf)
def layout_greenleaf_form(buf):
    v = GREENLEAF
    p = Pdf(buf, "GL-2291")
    blue = "#2b4a8b"
    p.rect(30, 30, 535, 520, stroke=blue, width=1)
    p.t(297, 58, "GREENLEAF PANTRY SUPPLIES", SANS_B, 16, blue, "center")
    p.t(297, 73, f"{v['addr']}  ·  Ph {v['phone']}", SANS, 8.5, blue, "center")
    p.t(297, 86, f"GSTIN: {v['gstin']}", SANS_B, 9, blue, "center")
    p.line(30, 96, 565, 96, blue, 1)
    p.t(297, 112, "TAX INVOICE / CASH MEMO", SANS_B, 10, blue, "center")
    p.t(40, 136, "No.", SANS, 9, blue)
    p.t(64, 137, "GL-2291", HAND, 12, "#1a2a6c")
    p.t(380, 136, "Date", SANS, 9, blue)
    p.t(412, 137, "12/11/26", HAND, 12, "#1a2a6c")
    p.t(40, 160, "M/s", SANS, 9, blue)
    p.t(66, 161, "Halcyon Foods Pvt Ltd, Santacruz East, Mumbai", HAND, 11, "#1a2a6c")
    p.t(40, 182, "P.O. No.", SANS, 9, blue)
    p.line(84, 184, 250, 184, blue, 0.5)
    p.t(300, 182, "Buyer GSTIN", SANS, 9, blue)
    p.t(364, 183, "27AAGCH5521L1Z7", HAND, 10.5, "#1a2a6c")
    ty = 200
    p.rect(30, ty, 535, 20, fill="#e9eef8", stroke=blue)
    for name, x, al in [("Sr.", 38, "left"), ("Particulars", 70, "left"), ("Qty", 330, "right"), ("Rate", 420, "right"),
                        ("Amount", 552, "right")]:
        p.t(x, ty + 14, name, SANS_B, 9, blue, al)
    for xx in (60, 280, 340, 430):
        p.line(xx, ty, xx, ty + 200, blue, 0.5)
    p.rect(30, ty, 535, 200, stroke=blue)
    rows = [("1", "Tea premix (masala)", "150 kg", "420", "63,000"), ("2", "Sugar", "250 kg", "48", "12,000")]
    y = ty + 42
    for sr, d, q, r, a in rows:
        p.t(40, y, sr, HAND, 11.5, "#1a2a6c")
        p.t(70, y, d, HAND, 12, "#1a2a6c")
        p.t(334, y, q, HAND, 12, "#1a2a6c", "right")
        p.t(424, y, r, HAND, 12, "#1a2a6c", "right")
        p.t(556, y, a, HAND, 12, "#1a2a6c", "right")
        y += 28
    y = ty + 222
    for k, val in [("Sub Total", "75,000"), ("CGST 2.5%", "1,875"), ("SGST 2.5%", "1,875")]:
        p.t(360, y, k, SANS, 9.5, blue)
        p.t(556, y + 1, val, HAND, 12, "#1a2a6c", "right")
        y += 22
    p.t(360, y + 4, "TOTAL Rs.", SANS_B, 10.5, blue)
    p.t(556, y + 5, "78,750", HAND, 14, "#1a2a6c", "right")
    p.t(40, ty + 250, "Rupees Seventy eight thousand", HAND, 11, "#1a2a6c")
    p.t(40, ty + 268, "seven hundred fifty only", HAND, 11, "#1a2a6c")
    p.t(40, 520, "Goods once sold will not be taken back. E.&O.E.", SANS, 7.5, blue)
    p.t(555, 520, "For Greenleaf Pantry Supplies", SANS, 8.5, blue, "right")
    p.save()
    return {"total_xy": (556, ty + 222 + 66 + 5), "po_xy": (150, 182)}


# ------------------------------------------------------------------ scan degradation (Pillow)
def _render(pdf_bytes: bytes, dpi: int) -> Image.Image:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def _noise(img: Image.Image, amount: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    import numpy as np  # noqa: PLC0415 (only needed for sample generation)
    arr = np.asarray(img).astype("int16")
    rng = np.random.default_rng(seed)
    arr = arr + rng.normal(0, amount, arr.shape).astype("int16")
    # sparse dark speckles
    h, w = arr.shape[:2]
    for _ in range(int(w * h / 3500)):
        y, x = rnd.randrange(h), rnd.randrange(w)
        arr[y:y + 2, x:x + 2] -= rnd.randrange(60, 140)
    return Image.fromarray(arr.clip(0, 255).astype("uint8"))


def _image_pdf(img: Image.Image, quality: int) -> tuple[pymupdf.Document, bytes]:
    jb = io.BytesIO()
    img.save(jb, "JPEG", quality=quality)
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(page.rect, stream=jb.getvalue())
    return doc, jb.getvalue()


def make_greenleaf_scan(path: Path):
    buf = io.BytesIO()
    marks = layout_greenleaf_form(buf)
    dpi = 150
    s = dpi / 72
    img = _render(buf.getvalue(), dpi).convert("RGB")
    # carbon-copy tint
    img = Image.blend(img, Image.new("RGB", img.size, (236, 232, 214)), 0.18)
    d = ImageDraw.Draw(img, "RGBA")
    # ink smudge over the total
    tx, ty = marks["total_xy"]
    cx, cy = int((tx - 22) * s), int((ty - 6) * s)
    smudge = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(smudge)
    sd.ellipse([cx - 52, cy - 16, cx + 40, cy + 18], fill=(70, 80, 120, 115))
    sd.ellipse([cx - 10, cy - 10, cx + 30, cy + 14], fill=(40, 50, 90, 80))
    smudge = smudge.filter(ImageFilter.GaussianBlur(7))
    img = Image.alpha_composite(img.convert("RGBA"), smudge).convert("RGB")
    # RECEIVED stamp over the PO field
    stamp = Image.new("RGBA", (int(250 * s / 1.6), int(60 * s / 1.6)), (0, 0, 0, 0))
    st = ImageDraw.Draw(stamp)
    try:
        f = ImageFont.truetype(_find("arialbd.ttf", "DejaVuSans-Bold.ttf") or "arial.ttf", int(26 * s / 1.6))
        f2 = ImageFont.truetype(_find("arial.ttf", "DejaVuSans.ttf") or "arial.ttf", int(11 * s / 1.6))
    except Exception:
        f = f2 = ImageFont.load_default()
    st.rectangle([2, 2, stamp.width - 3, stamp.height - 3], outline=(200, 30, 40, 210), width=4)
    st.text((14, 6), "RECEIVED", fill=(200, 30, 40, 210), font=f)
    st.text((16, stamp.height - int(18 * s / 1.6)), "13 NOV 2026  ACCOUNTS", fill=(200, 30, 40, 200), font=f2)
    stamp = stamp.rotate(-8, expand=True)
    px, py = marks["po_xy"]
    img.paste(stamp, (int((px - 70) * s), int((py - 30) * s)), stamp)
    # scan artefacts: rotation, blur, noise, JPEG
    img = img.rotate(1.5, resample=Image.BICUBIC, expand=False, fillcolor=(245, 243, 236))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    img = _noise(img, 9, seed=2291)
    doc, _ = _image_pdf(img, 45)
    doc.set_metadata({"title": "Scan 2026-11-13 GL-2291", "producer": "FlatbedScan 4.2 (fictional)"})
    doc.save(str(path), garbage=3, deflate=True)
    doc.close()


def make_photo_rescan(path: Path):
    """EC2: phone photo of the Brightline invoice, with the number printed as BL-0377-26.
    A scanning app saved it with an invisible OCR text layer."""
    buf = io.BytesIO()
    layout_classic(buf, number="BL-0377-26", date="20 Oct 2026", po="PO-2026-0998",
                   lines=[dict(code="CP-A4-75", desc="Copier paper A4 75gsm, 500 sheets per ream", hsn="4802",
                               qty=400, uom="reams", rate=250)], title="TAX INVOICE (COPY)")
    vec = buf.getvalue()
    dpi = 130
    img = _render(vec, dpi).convert("RGB")
    w, h = img.size
    # perspective (top edge narrower, as if photographed from below)
    coeffs = _perspective_coeffs([(0, 0), (w, 0), (w, h), (0, h)],
                                 [(w * 0.035, h * 0.02), (w * 0.965, 0), (w, h), (0, h * 0.985)])
    img = img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(120, 112, 98))
    img = img.rotate(3, resample=Image.BICUBIC, expand=False, fillcolor=(120, 112, 98))
    # vignette and warm cast of indoor light
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    for i in range(40):
        a = int(150 * (1 - i / 40))
        vd.rectangle([i * w / 90, i * h / 90, w - i * w / 90, h - i * h / 90], outline=a)
    vig = vig.filter(ImageFilter.GaussianBlur(40))
    dark = Image.new("RGB", (w, h), (40, 34, 26))
    img = Image.composite(dark, img, vig)
    img = Image.blend(img, Image.new("RGB", (w, h), (255, 236, 200)), 0.08)
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    img = _noise(img, 7, seed=377)
    doc, _ = _image_pdf(img, 50)
    # invisible OCR text layer, positioned like the original words
    src = pymupdf.open(stream=vec, filetype="pdf")
    page = doc[0]
    for b in src[0].get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                t = sp["text"]
                if not t.strip():
                    continue
                t = t.replace("₹", "Rs.")
                page.insert_text(pymupdf.Point(sp["origin"]), t, fontsize=sp["size"], fontname="helv",
                                 render_mode=3)
    src.close()
    doc.set_metadata({"title": "IMG_20261116_0932", "producer": "PocketScan OCR 7.1 (fictional)"})
    doc.save(str(path), garbage=3, deflate=True)
    doc.close()


def _perspective_coeffs(src, dst):
    import numpy as np  # noqa: PLC0415
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    A = np.array(m, dtype=float)
    B = np.array([c for p in src for c in p], dtype=float)
    return list(np.linalg.solve(A, B))


# ------------------------------------------------------------------ main
SAMPLES = [
    dict(id="SI-01", file="SI-01_brightline_BL-2026-0412.pdf", vendor="Brightline Office Supplies Pvt Ltd",
         vendor_id="V-101", title="Brightline: happy path", description="Clean PDF, tax separate, PO printed on the invoice",
         tags=["text PDF", "itemised", "explicit PO"], expected_outcome="auto_approve", driving_rules=[],
         invoice_no="BL/2026/0412", gross_paise=59000000, edge_case=None, requires_llm=False),
    dict(id="SI-02", file="SI-02_corevolt_CV-8841.pdf", vendor="Corevolt Electronics Pvt Ltd", vendor_id="V-102",
         title="Corevolt: bundled, tax inclusive", description="Compact layout, one bundled line, prices include GST",
         tags=["text PDF", "bundled line", "tax inclusive", "PO in narrative"], expected_outcome="approve_with_note",
         driving_rules=["R10", "R12"], invoice_no="CV-8841", gross_paise=32337900, edge_case=None, requires_llm=False),
    dict(id="SI-03", file="SI-03_kestrel_K-1241.pdf", vendor="Kestrel Print & Pack", vendor_id="V-103",
         title="Kestrel: split PO, third lot", description="Third invoice against a split PO, same template as before",
         tags=["text PDF", "split PO", "EC1"], expected_outcome="route_for_review", driving_rules=["R11", "R12"],
         invoice_no="K/1241", gross_paise=14160000, edge_case="EC1", requires_llm=False),
    dict(id="SI-04", file="SI-04_brightline_rescan_BL-0377-26.pdf", vendor="Brightline Office Supplies Pvt Ltd",
         vendor_id="V-101", title="Brightline: re-scanned copy", description="Phone photo of an invoice we already paid, skewed",
         tags=["scanned photo", "OCR layer", "EC2"], expected_outcome="reject", driving_rules=["R06"],
         invoice_no="BL-0377-26", gross_paise=11800000, edge_case="EC2", requires_llm=False),
    dict(id="SI-05", file="SI-05_greenleaf_GL-2291_scan.pdf", vendor="Greenleaf Pantry Supplies", vendor_id="V-104",
         title="Greenleaf: blurry scan, no PO", description="Degraded scan, no PO number, smudged total",
         tags=["scanned", "image only", "no PO", "EC3"], expected_outcome="approve_with_note",
         driving_rules=["R07", "R02"], invoice_no="GL-2291", gross_paise=7875000, edge_case="EC3", requires_llm=True),
    dict(id="SI-06", file="SI-06_corevolt_CV-8902_bank-change.pdf", vendor="Corevolt Electronics Pvt Ltd",
         vendor_id="V-102", title="Corevolt: new bank details", description="Perfect numbers, new bank details in the footer",
         tags=["text PDF", "bank change", "EC4"], expected_outcome="hold_request_info", driving_rules=["R05"],
         invoice_no="CV-8902", gross_paise=16638000, edge_case="EC4", requires_llm=False),
    dict(id="SI-07", file="SI-07_meridian_MX-5530_tax-error.pdf", vendor="Meridian Logistics Pvt Ltd",
         vendor_id="V-105", title="Meridian: GST slip", description="Clean PDF with a wrong GST amount (a digit slip)",
         tags=["text PDF", "tax error"], expected_outcome="reject", driving_rules=["R13"], invoice_no="MX-5530",
         gross_paise=19532000, edge_case=None, requires_llm=False),
]


def main():
    HIST.mkdir(exist_ok=True)
    layout_classic(OUT / SAMPLES[0]["file"], number="BL/2026/0412", date="14 Nov 2026", po="PO-2026-1001",
                   lines=[dict(code="CH-ERG-01", desc="Ergonomic mesh chair, adjustable lumbar support", hsn="9401",
                               qty=40, uom="nos", rate=6500),
                          dict(code="DK-STD-02", desc="Height-adjustable standing desk, 140 x 70 cm", hsn="9403",
                               qty=20, uom="nos", rate=12000)])
    layout_compact(OUT / SAMPLES[1]["file"])
    layout_boxed(OUT / SAMPLES[2]["file"], number="K/1241", date="10 Nov 2026", lot="3 of 3",
                 lines=[dict(code="CTN-L", desc="Corrugated shipping carton, large (lot 3 of 3)", qty=3000, uom="nos",
                             rate=40)])
    make_photo_rescan(OUT / SAMPLES[3]["file"])
    make_greenleaf_scan(OUT / SAMPLES[4]["file"])
    layout_card(OUT / SAMPLES[5]["file"])
    layout_freight(OUT / SAMPLES[6]["file"])
    # history PDFs (already in the seeded database)
    layout_classic(HIST / "BL-2026-0377.pdf", number="BL/2026/0377", date="20 Oct 2026", po="PO-2026-0998",
                   lines=[dict(code="CP-A4-75", desc="Copier paper A4 75gsm, 500 sheets per ream", hsn="4802",
                               qty=400, uom="reams", rate=250)])
    layout_boxed(HIST / "K-1187.pdf", number="K/1187", date="6 Oct 2026", lot="1 of 3",
                 lines=[dict(code="CTN-L", desc="Corrugated shipping carton, large (lot 1 of 3)", qty=4000, uom="nos",
                             rate=40),
                        dict(code="SETUP-01", desc="Custom print setup, plates and die", qty=1, uom="lot", rate=20000)])
    layout_boxed(HIST / "K-1203.pdf", number="K/1203", date="27 Oct 2026", lot="2 of 3",
                 lines=[dict(code="CTN-L", desc="Corrugated shipping carton, large (lot 2 of 3)", qty=3500, uom="nos",
                             rate=40)])
    (OUT / "expected.json").write_text(json.dumps({"as_of": "2026-11-16", "samples": SAMPLES}, indent=2,
                                                  ensure_ascii=False), encoding="utf-8")
    for s in SAMPLES:
        print(f"{s['id']}  {s['file']}  ({(OUT / s['file']).stat().st_size // 1024} KB)  expect {s['expected_outcome']}")
    print("history:", ", ".join(p.name for p in sorted(HIST.glob("*.pdf"))))


if __name__ == "__main__":
    main()
