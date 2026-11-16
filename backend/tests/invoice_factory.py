"""Generates small, fresh text-layer invoice PDFs with different line-table heading wordings, for the
header-variation tests. Layout is driven by a column spec, never by a file name."""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

W, H = A4


def build_invoice(*, vendor: str, gstin: str, address: str, meta: list[tuple[str, str]], columns: list[dict],
                  rows: list[list[str]], totals: list[tuple[str, str]], bank_line: str,
                  buyer: str = "Halcyon Foods Pvt Ltd", buyer_gstin: str = "27AAGCH5521L1Z7") -> bytes:
    """columns: [{"x": 40, "head": "Description" or "Taxable\\nValue", "align": "l"|"r", "xr": right edge for 'r'}]"""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H - 50, vendor)
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(W - 40, H - 50, "TAX INVOICE")
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 64, f"{address}  |  GSTIN {gstin}")
    y = H - 100
    for k, v in meta:
        c.drawString(330, y, f"{k}: {v}")
        y -= 14
    c.drawString(40, H - 100, f"Billed to: {buyer}")
    c.drawString(40, H - 114, f"Buyer GSTIN {buyer_gstin}, Place of supply Maharashtra (27)")

    y = H - 200
    c.setFont("Helvetica-Bold", 9)
    two_line = any("\n" in col["head"] for col in columns)
    for col in columns:
        parts = col["head"].split("\n")
        for i, part in enumerate(parts):
            yy = y - i * 11 if two_line else y
            if col.get("align") == "r":
                c.drawRightString(col["xr"], yy, part)
            else:
                c.drawString(col["x"], yy, part)
    if two_line:
        y -= 11
    c.setFont("Helvetica", 9)
    for r in rows:
        y -= 16
        for col, text in zip(columns, r):
            if col.get("align") == "r":
                c.drawRightString(col["xr"], y, text)
            else:
                c.drawString(col["x"], y, text)
    y -= 36
    for k, v in totals:
        c.drawRightString(480, y, k)
        c.drawRightString(570, y, v)
        y -= 14
    c.drawString(40, 90, bank_line)
    c.save()
    return buf.getvalue()


def greenleaf_taxable_amt() -> bytes:
    """Greenleaf Pantry, PO-2026-1007: Sl | Item | Quantity | Rate | Taxable Amt (the GL-2317 shape)."""
    cols = [{"x": 40, "head": "Sl"}, {"x": 60, "head": "Item"}, {"x": 280, "head": "Quantity"},
            {"x": 360, "head": "Rate"}, {"x": 440, "head": "Taxable Amt", "align": "r", "xr": 500}]
    rows = [["1", "Paper cup 150 ml (PNT-CUP)", "10,000 nos", "1.65", "16,500.00"],
            ["2", "Wooden stirrer (PNT-STR)", "5,000 nos", "0.40", "2,000.00"]]
    return build_invoice(
        vendor="GREENLEAF PANTRY SUPPLIES", gstin="27AAJFG9054R1Z2", address="Pune 411001",
        meta=[("Invoice Number", "GL-2317"), ("Invoice Date", "12 Nov 2026"), ("Purchase Order", "PO-2026-1007")],
        columns=cols, rows=rows,
        totals=[("Taxable amount", "18,500.00"), ("CGST 6%", "1,110.00"), ("SGST 6%", "1,110.00"),
                ("Grand Total Rs.", "20,720.00")],
        bank_line="Bank: Lakeview Bank  A/c No: 3300 1275 5508  IFSC: LKVB0000318")


def brightline_line_total() -> bytes:
    """Brightline, PO-2026-0985: S.No | Particulars | HSN/SAC | Qty | Unit Price | Line Total."""
    cols = [{"x": 40, "head": "S.No."}, {"x": 80, "head": "Particulars"}, {"x": 270, "head": "HSN/SAC"},
            {"x": 335, "head": "Qty", "align": "r", "xr": 360}, {"x": 400, "head": "Unit Price", "align": "r", "xr": 460},
            {"x": 500, "head": "Line Total", "align": "r", "xr": 570}]
    rows = [["1", "Black toner cartridge (TNR-BK)", "84439959", "30", "3,450.00", "1,03,500.00"]]
    return build_invoice(
        vendor="Brightline Office Supplies Pvt Ltd", gstin="27AAFCB4821K1Z3", address="14 Dockyard Road, Mumbai 400010",
        meta=[("Bill No.", "BLS/26-27/0519"), ("Dated", "13/11/2026"), ("Order Ref.", "PO-2026-0985")],
        columns=cols, rows=rows,
        totals=[("Sub Total", "1,03,500.00"), ("Add: CGST 9%", "9,315.00"), ("Add: SGST 9%", "9,315.00"),
                ("Invoice Total (INR)", "1,22,130.00")],
        bank_line="Remit to Harbor Union Bank, account 0123 4567 8901, IFSC HUBK0000214")


def corevolt_igst_two_line_headings() -> bytes:
    """Corevolt (Karnataka) billing a Maharashtra buyer: two-line headings, HSN, Tax Rate and IGST columns
    sit next to the Taxable Value column, and a gross Total column follows it."""
    cols = [{"x": 40, "head": "Item\nDescription"}, {"x": 215, "head": "HSN"},
            {"x": 250, "head": "Qty", "align": "r", "xr": 275}, {"x": 285, "head": "Rate\n(Rs.)", "align": "r", "xr": 340},
            {"x": 350, "head": "Taxable\nValue", "align": "r", "xr": 410},
            {"x": 420, "head": "Tax Rate", "align": "r", "xr": 462},
            {"x": 470, "head": "IGST\nAmt", "align": "r", "xr": 510},
            {"x": 520, "head": "Total", "align": "r", "xr": 570}]
    rows = [["24-port managed switch (NS-24P)", "85176290", "6", "21,000.00", "1,26,000.00", "18%", "22,680.00", "1,48,680.00"],
            ["Cat6 patch cable 2 m (PC-CAT6)", "85444299", "60", "250.00", "15,000.00", "18%", "2,700.00", "17,700.00"]]
    return build_invoice(
        vendor="Corevolt Electronics Pvt Ltd", gstin="29AAHCC7710M1Z8", address="Bengaluru 560001",
        meta=[("Invoice No", "CV-9120"), ("Invoice Date", "11/11/2026"), ("PO Ref", "PO-2026-1008")],
        columns=cols, rows=rows,
        totals=[("Sub Total", "1,41,000.00"), ("IGST 18%", "25,380.00"), ("Grand Total Rs.", "1,66,380.00")],
        bank_line="Remit to Harbor Union Bank, account 0001 2345 6789, IFSC HUBK0000101")


def brightline_gst_pct_units() -> bytes:
    """Brightline, PO-2026-1001: Sr. | Product Name | Units | Price | GST % | Net Amt."""
    cols = [{"x": 40, "head": "Sr."}, {"x": 65, "head": "Product Name"}, {"x": 290, "head": "Units", "align": "r", "xr": 325},
            {"x": 350, "head": "Price", "align": "r", "xr": 410}, {"x": 430, "head": "GST %", "align": "r", "xr": 470},
            {"x": 490, "head": "Net Amt", "align": "r", "xr": 570}]
    rows = [["1", "Ergonomic mesh chair (CH-ERG-01)", "10", "6,500.00", "18%", "65,000.00"],
            ["2", "Height-adjustable standing desk (DK-STD-02)", "5", "12,000.00", "18%", "60,000.00"]]
    return build_invoice(
        vendor="Brightline Office Supplies Pvt Ltd", gstin="27AAFCB4821K1Z3", address="14 Dockyard Road, Mumbai 400010",
        meta=[("Invoice No", "BLS/26-27/0533"), ("Invoice Date", "13/11/2026"), ("PO", "PO-2026-1001")],
        columns=cols, rows=rows,
        totals=[("Sub Total", "1,25,000.00"), ("CGST 9%", "11,250.00"), ("SGST 9%", "11,250.00"),
                ("Grand Total Rs.", "1,47,500.00")],
        bank_line="Remit to Harbor Union Bank, account 0123 4567 8901, IFSC HUBK0000214")


def unreadable_headings() -> bytes:
    """A real table whose headings carry no recognisable meaning (Col A, Col B ...)."""
    cols = [{"x": 40, "head": "Col A"}, {"x": 280, "head": "Col B", "align": "r", "xr": 330},
            {"x": 350, "head": "Col C", "align": "r", "xr": 410}, {"x": 500, "head": "Col D", "align": "r", "xr": 570}]
    rows = [["Black toner cartridge (TNR-BK)", "24", "3,450.00", "82,800.00"]]
    return build_invoice(
        vendor="Brightline Office Supplies Pvt Ltd", gstin="27AAFCB4821K1Z3", address="14 Dockyard Road, Mumbai 400010",
        meta=[("Invoice No", "BLS/26-27/0541"), ("Invoice Date", "14/11/2026"), ("PO", "PO-2026-0985")],
        columns=cols, rows=rows,
        totals=[("Sub Total", "82,800.00"), ("CGST 9%", "7,452.00"), ("SGST 9%", "7,452.00"),
                ("Invoice Total (INR)", "97,704.00")],
        bank_line="Remit to Harbor Union Bank, account 0123 4567 8901, IFSC HUBK0000214")
