"""Deterministic invoice extraction from a PDF text layer (used when no ANTHROPIC_API_KEY is set,
and for the text-layer evidence check). It is layout-agnostic: it reads words with coordinates,
rebuilds visual rows and cells, finds labelled header fields (label left of, or above, the value),
detects the line-item table from its header row and maps cells to columns by alignment.

It never looks at the file name."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config, pdfio
from .textutil import GSTIN_RE, IFSC_RE, parse_money, parse_number, po_keys

CELL_GAP = 7.0      # points of horizontal gap that separate two cells on a row
ROW_TOL = 2.2       # points of vertical tolerance for words on the same row


@dataclass
class Cell:
    words: list
    x0: float = 0
    x1: float = 0
    y0: float = 0
    y1: float = 0
    text: str = ""

    def __post_init__(self):
        self.x0 = min(w[0] for w in self.words)
        self.y0 = min(w[1] for w in self.words)
        self.x1 = max(w[2] for w in self.words)
        self.y1 = max(w[3] for w in self.words)
        self.text = " ".join(w[4] for w in self.words)


@dataclass
class Row:
    page: int
    y: float
    words: list
    cells: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return "  ".join(c.text for c in self.cells)


def build_rows(pages_words: list[list[tuple]]) -> list[Row]:
    out: list[Row] = []
    for pno, ws in enumerate(pages_words):
        ws = sorted(ws, key=lambda w: (round(w[3], 1), w[0]))
        rows: list[Row] = []
        for w in ws:
            if rows and abs(rows[-1].y - w[3]) <= ROW_TOL:
                rows[-1].words.append(w)
            else:
                rows.append(Row(page=pno, y=w[3], words=[w]))
        for r in rows:
            r.words.sort(key=lambda w: w[0])
            cells, cur = [], [r.words[0]]
            for w in r.words[1:]:
                if w[0] - cur[-1][2] > CELL_GAP:
                    cells.append(Cell(cur))
                    cur = [w]
                else:
                    cur.append(w)
            cells.append(Cell(cur))
            r.cells = cells
        out.extend(rows)
    return out


# ------------------------------------------------------------------ value patterns
MONEY_RE = re.compile(
    r"(?<![\w.,/-])(?:(?:₹|Rs\.?|INR)\s?)?(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{2})(?![\d%])"
    r"|(?:₹|Rs\.?|INR)\s?(\d+)(?![\d.,%])", re.I)
DATE_RE = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?[\-/. ]+[A-Za-z]{3,9}\.?[\-/., ]+\d{2,4}|\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\.? \d{1,2},? \d{4}")
INVNO_RE = re.compile(r"(?=[A-Z0-9/\-.]*\d)[A-Z][A-Z0-9]*(?:[/\-.][A-Z0-9]+)+|[A-Z]{1,5}\d{3,}|\d{3,}(?:[/\-][A-Z0-9]+)*",
                      re.I)
PO_VAL_RE = re.compile(r"P\.?O\.?[\s\-#]?\d{4}[\s\-/]\d{3,5}|\d{3,5}/20\d{2}|20\d{2}[\-/]\d{3,5}", re.I)

LBL_INVNO = re.compile(r"\b(?:invoice|inv|bill)\.?\s*(?:no\b\.?|number\b|num\b|#)", re.I)
LBL_DATE = re.compile(r"^(?:invoice|inv|bill)\.?\s*date\b|^date\b(?! of (?:supply|delivery))|\bdated\b"
                      r"|\bdate of (?:invoice|issue)\b|\b(?:invoice|inv)\.?\s*date\b", re.I)
LBL_PO = re.compile(r"\b(?:p\.?\s?o\.?|purchase\s+order|order\s+ref(?:erence)?)(?=[\s:#.\-]|$)"
                    r"(?:\s*(?:no\.?|number|#|ref(?:erence)?)\b)?", re.I)
MONTH_WORD = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)


def _strip_lead(s: str) -> str:
    return s.lstrip(" :#.-–")


def find_labeled(rows: list[Row], label: re.Pattern, value: re.Pattern, *, below: bool = True,
                 skip: re.Pattern | None = None):
    """Return (value_text, row_index) for the first label whose value is to its right, in the next
    cell, or directly below it."""
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row.cells):
            m = label.search(cell.text)
            if not m or (skip and skip.search(cell.text)):
                continue
            rest = _strip_lead(cell.text[m.end():])
            if rest:
                v = value.search(rest)
                if v and v.start() <= 2:
                    return v.group(0).strip(), ri
                if v and label is LBL_PO:
                    return v.group(0).strip(), ri
            for nxt in row.cells[ci + 1:ci + 3]:
                t = _strip_lead(nxt.text)
                v = value.match(t)
                if v:
                    return v.group(0).strip(), ri
                break
            if below:
                for rj in range(ri + 1, min(ri + 3, len(rows))):
                    br = rows[rj]
                    if br.page != row.page or br.y - row.y > 28:
                        break
                    for c in br.cells:
                        if c.x1 >= cell.x0 - 4 and c.x0 <= cell.x1 + 4:
                            v = value.match(_strip_lead(c.text))
                            if v:
                                return v.group(0).strip(), rj
    return None, None


def money_in(text: str) -> list[str]:
    out = []
    for m in MONEY_RE.finditer(text):
        out.append(m.group(0).strip())
    return out


# ------------------------------------------------------------------ line-item table
# Column headings are matched on normalised text (lower case, punctuation dropped) against synonym
# lists, so "Taxable Amt.", "Net Value", "Line Total", "Unit Price (Rs.)", "HSN/SAC", "Particulars",
# "Sl. No." etc. all map to a column kind. Unknown headings are kept as sink columns ("other") so the
# cells under them are not mistaken for a neighbouring column. Tax-split columns (CGST/SGST/IGST amount,
# discount, cess) are sinks too: they must never be read as the line amount.
COL_KIND_ORDER = [
    ("hsn", re.compile(r"\b(hsn|sac)\b")),
    ("sno", re.compile(r"^(no|sl|sr|sn|s ?no|sl ?no|sr ?no|serial( ?no| number)?|line( ?no)?|item ?no)$")),
    ("taxpart", re.compile(r"\b(?:c|s|ut)gst\b")),
    ("taxrate", re.compile(r"\b(?:gst|igst|tax|vat)\s*(?:%|rate|percent|pct)|\brate of (?:gst|tax)\b|^%$")),
    ("taxpart", re.compile(r"\b(?:gst|igst|tax|vat|cess)\b")),
    ("other", re.compile(r"\b(?:disc|discount|rebate)\b")),
    ("rate", re.compile(r"\b(?:rate|price|mrp)\b")),
    ("qty", re.compile(r"\b(?:qty|quantity|qnty|trips|nos|hours|hrs|pcs|pieces)\b")),
    ("amount", re.compile(r"\b(?:taxable|amount|amt|value|total|net|extended|ext)\b")),
    ("uom", re.compile(r"^(?:unit|units|uom|per|unit of measure|u ?m)$")),
    ("code", re.compile(r"\b(?:code|sku|part ?no|part number)\b")),
    ("desc", re.compile(r"\b(?:description|desc|particulars|details|goods|services?|products?|item name|"
                        r"name of (?:the )?(?:item|goods|product|service)s?|narration)\b")),
    ("item", re.compile(r"^items?$")),
]
RIGHT_ALIGNED = {"qty", "rate", "amount", "taxrate", "taxpart"}
TABLE_END = re.compile(r"\b(sub\s*-?\s*total|taxable|total|cgst|sgst|igst|amount payable|amount in words|bank)\b", re.I)
_INCL_RE = re.compile(r"\bincl\w*|\bwith (?:(?:c|s|i|ut)?gst|tax)\b|\bgross\b|\binc\b")
_PRE_RE = re.compile(r"\bexcl\w*|\bex ?tax\b|\bbefore (?:gst|tax)|\bpre ?tax\b|\bnet\b|\btaxable\b")
_QUAL_RE = re.compile(r"\b(?:incl\w*|excl\w*|inc|ex|before|pre|net of|with)\s*(?:of\s+)?(?:(?:c|s|i|ut)?gst|tax|vat)\b")


def _norm_header(t: str) -> str:
    t = t.lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%/ ]+", " ", t)).strip()


def header_kind(text: str) -> tuple[str | None, int]:
    """(column kind, rank). Rank orders competing candidates for the same kind: 0 = clearly pre-tax
    (taxable/net/excl. tax), 1 = plain, 2 = tax-inclusive/gross."""
    raw = text.strip()
    if raw == "#":
        return "sno", 1
    n = _norm_header(raw)
    if not n:
        return None, 1
    rank = 2 if _INCL_RE.search(n) else (0 if _PRE_RE.search(n) else 1)
    n = re.sub(r"\s+", " ", _QUAL_RE.sub(" ", n)).strip()
    for name, rx in COL_KIND_ORDER:
        if rx.search(n):
            return name, rank
    return None, 1


def classify_header(cells: list[Cell]) -> list[tuple[str, Cell]] | None:
    cands = []
    for c in cells:
        k, rank = header_kind(c.text)
        cands.append([k, rank, c])
    names = [k for k, _, _ in cands if k]
    if "item" in names:
        for cd in cands:
            if cd[0] == "item":
                cd[0] = "code" if "desc" in names else "desc"
        names = [k for k, _, _ in cands if k]
    # "Units" with no quantity column is the quantity
    if "qty" not in names:
        for cd in cands:
            if cd[0] == "uom" and _norm_header(cd[2].text) == "units":
                cd[0] = "qty"
                break
    # one column per kind: prefer the pre-tax one, then the leftmost; the others become sinks
    for kind in ("amount", "rate", "qty", "desc", "hsn", "taxrate", "sno", "code", "uom"):
        group = [cd for cd in cands if cd[0] == kind]
        if len(group) > 1:
            keep = min(group, key=lambda cd: (cd[1], cd[2].x0))
            for cd in group:
                if cd is not keep:
                    cd[0] = "taxpart" if kind in ("amount", "rate", "taxrate") else "other"
    kinds = [(k or "other", c) for k, _, c in cands]
    have = {k for k, _ in kinds}
    if "amount" in have and "desc" in have and ("qty" in have or "rate" in have):
        return kinds
    return None


def _merge_header_rows(a: Row, b: Row) -> list[Cell]:
    """Combine a two-line heading ("Taxable" over "Value") into one set of cells by horizontal overlap."""
    groups: list[list] = [list(c.words) for c in a.cells]
    spans = [(c.x0, c.x1) for c in a.cells]
    extra: list[Cell] = []
    for c in b.cells:
        best, bo = None, 0.0
        for i, (x0, x1) in enumerate(spans):
            o = min(x1, c.x1) - max(x0, c.x0)
            if o > bo:
                best, bo = i, o
        if best is None:
            extra.append(c)
        else:
            groups[best] += c.words
            spans[best] = (min(spans[best][0], c.x0), max(spans[best][1], c.x1))
    out = [Cell(g) for g in groups] + extra
    return sorted(out, key=lambda c: c.x0)


def _header_candidates(rows: list[Row]):
    """Yield (index of the last heading row, columns, heading text) for each plausible heading."""
    for hi, row in enumerate(rows):
        cols = classify_header(row.cells)
        if cols:
            yield hi, cols, row.text
            continue
        if hi + 1 < len(rows):
            nxt = rows[hi + 1]
            if nxt.page == row.page and 0 < nxt.y - row.y <= 16 and not money_in(nxt.text):
                cols = classify_header(_merge_header_rows(row, nxt))
                if cols:
                    yield hi + 1, cols, row.text + " " + nxt.text


CONTINUED_RE = re.compile(r"\b(continued|contd\.?|carried\s+forward|c/f)\b", re.I)


def parse_table(rows: list[Row], low_conf: bool) -> tuple[list[dict], bool, int | None]:
    """Returns (line_items, header_says_tax_inclusive, header_row_index)."""
    for hi, cols, head_text in _header_candidates(rows):
        row = rows[hi]
        incl = bool(re.search(r"incl", head_text, re.I))
        items: list[dict] = []
        conf = 0.88 if low_conf else 0.95
        page, skipping, skipped = row.page, False, 0
        for r in rows[hi + 1:]:
            if r.page != page:
                # The table may continue on the next page: skip that page's letterhead, "continued" line and
                # repeated column header until the next item row (a table that does not continue ends here).
                if not items:
                    break
                page, skipping, skipped = r.page, True, 0
            if skipping:
                if _row_is_item(r, cols):
                    skipping = False
                else:
                    skipped += 1
                    if TABLE_END.search(r.text) and not _is_header_row(r, cols) or skipped > 12:
                        break
                    continue
            if items and CONTINUED_RE.search(r.text) and not _row_is_item(r, cols):
                skipping, skipped = True, 0      # "Continued on page 2": the table goes on after the page break
                continue
            if TABLE_END.search(r.text) and not _row_is_item(r, cols):
                break
            if items and items[-1]["_page"] == r.page and r.y - items[-1]["_y"] > 140:
                break
            cellmap = _assign(r.cells, cols)
            amount = cellmap.get("amount")
            q = cellmap.get("qty")
            if amount and money_in(amount) and (q or cellmap.get("rate")):
                qn = parse_number(q) if q else None
                # A credit line ("Less: returned chairs (2) ... (13,000.00)") reduces the bill: keep its sign.
                credit = bool(re.search(r"\(\s*[\d,]+(?:\.\d+)?\s*\)|^\s*-\s*\d", amount)) or \
                    bool(re.match(r"\s*(?:\d+\s+)?less\b", cellmap.get("desc") or "", re.I))
                if credit and qn:
                    qn = -abs(qn)
                uom = cellmap.get("uom")
                if q and not uom:
                    m = re.search(r"[A-Za-z]+\.?$", q.strip())
                    uom = m.group(0) if m else None
                items.append({
                    "description": cellmap.get("desc") or "",
                    "item_code": cellmap.get("code"),
                    "qty": qn,
                    "uom": uom,
                    "unit_price": (money_in(cellmap.get("rate") or "") or [cellmap.get("rate")])[0],
                    "amount": ("-" if credit else "") + money_in(amount)[-1],
                    "tax_rate_pct": parse_number(cellmap.get("taxrate")) if cellmap.get("taxrate") else None,
                    "confidence": conf,
                    "raw_text": r.text,
                    "_y": r.y,
                    "_page": r.page,
                })
            elif items and cellmap.get("desc") and not amount:
                items[-1]["description"] = (items[-1]["description"] + " " + cellmap["desc"]).strip()
                items[-1]["_y"] = r.y
        for it in items:
            it.pop("_y", None)
            it.pop("_page", None)
        if items:
            return items, incl, hi
    return [], False, None


def _is_header_row(r: Row, cols) -> bool:
    """A repeated column header (on a continuation page)."""
    return bool(classify_header(r.cells))


def _row_is_item(r: Row, cols) -> bool:
    cm = _assign(r.cells, cols)
    return bool(cm.get("amount") and money_in(cm["amount"]) and cm.get("desc") and (cm.get("qty") or cm.get("rate"))
                and not TABLE_END.search(cm.get("desc", "")))


def _assign(cells: list[Cell], cols: list[tuple[str, Cell]]) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for c in cells:
        numeric = bool(re.fullmatch(r"[₹Rs.INR\s]*[\d,]+(?:\.\d+)?\s*[A-Za-z.%]*", c.text.strip()))
        best, bestd = None, 1e9
        for kind, hc in cols:
            if kind in RIGHT_ALIGNED:
                d = abs(c.x1 - hc.x1)
                if not numeric:
                    d += 60
            elif kind == "other":
                d = min(abs(c.x0 - hc.x0), abs(c.x1 - hc.x1) if numeric else 1e9)
                if hc.x0 - 4 <= c.x0 <= hc.x0 + 6:
                    d = min(d, 1)
            else:
                d = abs(c.x0 - hc.x0)
                if numeric and kind == "desc":
                    d += 25
                # text that starts inside a left-aligned column's span belongs to it
                if hc.x0 - 4 <= c.x0 <= hc.x0 + 6:
                    d = min(d, 1)
            if d < bestd:
                best, bestd = kind, d
        if best:
            out.setdefault(best, []).append(c.text)
    return {k: " ".join(v) for k, v in out.items()}


# ------------------------------------------------------------------ totals and tax
SUBTOTAL_RE = re.compile(r"\b(sub\s*-?\s*total|total taxable value|taxable value|taxable amt|taxable amount|"
                         r"amount before tax|total before tax)\b", re.I)
TAX_RE = re.compile(r"\b(cgst|sgst|igst|utgst|gst)\b", re.I)
TAX_TOTAL_RE = re.compile(r"\b(total (?:gst|tax)|tax total|gst total)\b", re.I)
TOTAL_RES = [
    re.compile(r"\bgrand total\b", re.I), re.compile(r"\binvoice total\b", re.I),
    re.compile(r"\btotal (?:due|payable|amount)\b", re.I), re.compile(r"\bamount (?:payable|due)\b", re.I),
    re.compile(r"\b(?:balance due|net payable)\b", re.I),
    re.compile(r"(?<!sub )(?<!sub)\btotal\b(?!\s*taxable)(?!\s*\(?gst)", re.I),
]
INCLUSIVE_RE = re.compile(r"inclusive of (?:i|c|s)?gst|incl(?:usive|\.)? (?:of )?(?:i)?gst|gst included|"
                          r"prices include (?:i)?gst|tax inclusive", re.I)
RATE_RE = re.compile(r"@?\s*(\d{1,2}(?:\.\d+)?)\s*%")


CHARGE_RE = re.compile(r"\b(freight|carriage|packing|forwarding|insurance|handling|loading|delivery\s+charges?|"
                       r"courier|transport(?:ation)?\s+charges?|round(?:ing)?[\s\-]*off)\b", re.I)
DISCOUNT_RE = re.compile(r"\b(discount|rebate)\b", re.I)


def parse_totals(rows: list[Row], start: int) -> dict:
    res = {"subtotal": None, "tax_total": None, "total": None, "tax_lines": [], "inclusive": False,
           "inclusive_rate": None, "other_paise": 0, "discount_paise": 0, "other_labels": []}
    total_rank = 99
    for ri in range(start, len(rows)):
        t = rows[ri].text
        tl = t.lower()
        amounts = money_in(t)
        if INCLUSIVE_RE.search(t):
            res["inclusive"] = True
            m = RATE_RE.search(t)
            if m:
                res["inclusive_rate"] = float(m.group(1))
        if not amounts:
            # label above value (card layouts)
            continue
        if "gstin" in tl and not TAX_RE.search(tl.replace("gstin", "")):
            continue
        if SUBTOTAL_RE.search(t) and res["subtotal"] is None:
            res["subtotal"] = amounts[-1]
            continue
        if TAX_TOTAL_RE.search(t):
            res["tax_total"] = amounts[-1]
            continue
        if CHARGE_RE.search(t) and not re.search(r"\btotal\b", tl):
            # freight, packing, insurance, round off ... between the subtotal and the total
            sign = -1 if re.search(r"\(\s*[\d,.]+\s*\)|-\s*[\d,.]+\s*$", t) else 1
            res["other_paise"] += sign * (parse_money(amounts[-1]) or 0)
            res["other_labels"].append(t.strip())
            continue
        if DISCOUNT_RE.search(t) and not re.search(r"\btotal\b", tl):
            res["discount_paise"] += abs(parse_money(amounts[-1]) or 0)
            res["other_labels"].append(t.strip())
            continue
        if TAX_RE.search(tl.replace("gstin", "")) and not re.search(r"\btotal\b|payable", tl):
            m = RATE_RE.search(t)
            label = TAX_RE.search(tl.replace("gstin", "")).group(1).upper()
            res["tax_lines"].append({"label": label, "rate_pct": float(m.group(1)) if m else None,
                                     "amount": amounts[-1], "raw_text": t})
            continue
        for rank, rx in enumerate(TOTAL_RES):
            if rx.search(t) and not SUBTOTAL_RE.search(t):
                if rank < total_rank or (rank == total_rank and res["total"] is not None):
                    if rank <= total_rank:
                        res["total"] = amounts[-1]
                        total_rank = rank
                break
    return res


# ------------------------------------------------------------------ bank
BANK_NAME_RE = re.compile(r"([A-Z][A-Za-z&.\-]*(?:\s+[A-Z][A-Za-z&.\-]*){0,4}\s+Bank)\b")
ACCT_RE = re.compile(r"(?:a/c|account)\s*(?:no\.?|number|#)?\s*[:.\-]?\s*(\d[\d \-.]{6,28}\d)", re.I)
CHANGE_RE = re.compile(r"bank (?:account )?details (?:have|has) (?:been )?changed|new bank (?:account|details)|"
                       r"change (?:of|in) (?:our )?bank|bank details changed|updated bank details", re.I)


def parse_bank(lines: list[str]) -> dict:
    res = {"bank_name": None, "account": None, "ifsc": None, "notice": False, "notice_text": None, "raw": None}
    for ln in lines:
        if CHANGE_RE.search(ln):
            res["notice"] = True
            res["notice_text"] = ln.strip()
    bank_lines = [ln for ln in lines if re.search(r"\b(a/c|account|ifsc)\b", ln, re.I) and re.search(r"bank", ln, re.I)]
    # Prefer the payment block over the change-notice sentence when both exist.
    bank_lines.sort(key=lambda ln: 1 if CHANGE_RE.search(ln) else 0)
    # Every bank entry on the page is kept: an invoice can name a second "remit to" account further down, and
    # comparing only the first one would miss it (R05 checks them all).
    res["entries"] = []
    for ln in bank_lines:
        m = BANK_NAME_RE.search(ln)
        a = ACCT_RE.search(ln)
        i = IFSC_RE.search(ln)
        if m or a:
            entry = {"name": m.group(1).strip() if m else None, "account": a.group(1).strip() if a else None,
                     "ifsc": i.group(0) if i else None, "raw": ln.strip()}
            res["entries"].append(entry)
            res["bank_name"] = res["bank_name"] or entry["name"]
            res["account"] = res["account"] or entry["account"]
            res["ifsc"] = res["ifsc"] or entry["ifsc"]
            res["raw"] = res["raw"] or ln.strip()
    if res["ifsc"] is None:
        for ln in lines:
            i = IFSC_RE.search(ln)
            if i:
                res["ifsc"] = i.group(0)
                break
    return res


# ------------------------------------------------------------------ main entry
TITLE_WORDS = re.compile(r"^(tax\s+invoice|invoice|bill|original|duplicate|copy|cash memo)\b", re.I)

# Documents that look like invoices but must never be paid as one. Matched only against whole title lines near the
# top of the first page, so phrases such as "Against Invoice No" or "Credit Note No:" in the body do not count.
DOC_KINDS = [
    ("credit_note", re.compile(r"^(gst\s+)?credit\s*note\b", re.I)),
    ("debit_note", re.compile(r"^(gst\s+)?debit\s*note\b", re.I)),
    ("proforma", re.compile(r"^pro[\s\-]?forma(\s+invoice)?\b", re.I)),
    ("quotation", re.compile(r"^(quotation|estimate|price\s+quote)\b", re.I)),
    ("statement", re.compile(r"^statement(\s+of\s+accounts?)?\b", re.I)),
    ("delivery_challan", re.compile(r"^delivery\s+(challan|note)\b", re.I)),
]
INVOICE_TITLE = re.compile(r"^(tax\s+invoice|invoice|bill\s+of\s+supply|retail\s+invoice)\b(?!\s*(no|number|#|date))",
                           re.I)


DOC_KIND_LABEL = {"credit_note": "credit note", "debit_note": "debit note", "proforma": "proforma invoice",
                  "quotation": "quotation", "statement": "statement of account",
                  "delivery_challan": "delivery challan", "purchase_order": "purchase order"}
# What a vision model may answer for document_type (anything else, including "tax_invoice", means an invoice).
DOC_KIND_ALIASES = {"credit_note": "credit_note", "debit_note": "debit_note", "proforma": "proforma",
                    "proforma_invoice": "proforma", "pro_forma_invoice": "proforma", "quotation": "quotation",
                    "estimate": "quotation", "statement": "statement", "statement_of_account": "statement",
                    "delivery_challan": "delivery_challan", "purchase_order": "purchase_order"}


def classify_document(text: str, top_lines: int = 12) -> str | None:
    """'credit_note', 'proforma', ... when a title line near the top names a non-invoice document, else None."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()][:top_lines]
    for ln in lines:
        if len(ln) > 40:          # a title is short; long lines are addresses or sentences
            continue
        if INVOICE_TITLE.match(ln):
            return None           # the first title wins: an invoice title means it is an invoice
        for kind, rx in DOC_KINDS:
            if rx.match(ln):
                return kind
    return None


def _fld(value, raw=None, conf=0.0, **extra):
    d = {"value": value, "raw_text": raw if raw is not None else value, "confidence": conf if value is not None else 0.0}
    d.update(extra)
    return d


def extract(data: bytes, text_source: str = "text_layer") -> dict:
    low = text_source == "ocr_layer"
    hi_conf = 0.88 if low else 0.96
    pages_words = pdfio.words(data)
    rows = build_rows(pages_words)
    lines = [r.text for r in rows]
    full = "\n".join(lines)

    # vendor identity
    gstins = [g for g in GSTIN_RE.findall(full.upper()) if g != config.BUYER["gstin"]]
    gstin = gstins[0] if gstins else None
    vendor_name = None
    sps = pdfio.spans(data, 0)
    if sps:
        page_h = max((s["bbox"][3] for s in sps), default=842)
        top = [s for s in sps if s["bbox"][1] < max(170.0, page_h * 0.2) and s["size"] >= 10.5
               and not TITLE_WORDS.match(s["text"]) and config.BUYER["name"].lower() not in s["text"].lower()
               and not GSTIN_RE.search(s["text"]) and len(re.findall(r"[A-Za-z]", s["text"])) >= 4]
        if top:
            vendor_name = max(top, key=lambda s: s["size"])["text"].strip()

    inv_no, _ = find_labeled(rows, LBL_INVNO, INVNO_RE)
    date_raw, _ = find_labeled(rows, LBL_DATE, DATE_RE, skip=re.compile(r"\b(due|po|order|delivery|supply)\b", re.I))
    po_raw, _ = find_labeled(rows, LBL_PO, PO_VAL_RE)
    po_cands = []
    for k in po_keys(full, strict=True):
        po_cands.append(f"PO-{k[0]}-{k[1]:04d}")

    items, incl_hdr, hdr_idx = parse_table(rows, low)
    tot = parse_totals(rows, hdr_idx + 1 if hdr_idx is not None else 0)
    # label-above total (e.g. "AMOUNT DUE" card) when no total row found
    if tot["total"] is None:
        v, _ = find_labeled(rows, re.compile(r"\b(amount due|total due|grand total|total)\b", re.I), MONEY_RE)
        tot["total"] = v
    bank = parse_bank(lines)

    currency = None
    cur_raw = None
    cur_note = None
    # 1) an explicit label ("Currency: USD", "Grand Total (USD)") wins over symbols elsewhere on the page,
    #    e.g. "(INR account)" in the bank block of a USD invoice
    lab = (re.search(r"\bcurrency\s*[:\-]?\s*(INR|USD|EUR|GBP)\b", full, re.I)
           or re.search(r"\btotal\b[^\n]{0,25}?\(\s*(INR|USD|EUR|GBP)\s*\)", full, re.I))
    if lab:
        currency, cur_raw = lab.group(1).upper(), lab.group(0)
    else:
        m = re.search(r"₹|\bINR\b|\bRs\.?(?![A-Za-z])", full)
        if m:
            currency, cur_raw = "INR", m.group(0)
        elif re.search(r"\bUSD\b|\$", full):
            currency, cur_raw = "USD", "USD"
        elif re.search(r"\bEUR\b|€", full):
            currency, cur_raw = "EUR", "EUR"
        else:
            # 3) no currency printed at all: a GST invoice (CGST/SGST/IGST lines) is billed in rupees
            g = re.search(r"\b(?:CGST|SGST|IGST|UTGST)\b", full)
            if g:
                currency, cur_raw = "INR", g.group(0)
                cur_note = "No currency is printed; it is a GST invoice, so the amounts were read as rupees."

    incl = tot["inclusive"] or incl_hdr
    rate = tot["inclusive_rate"]
    if rate is None and tot["tax_lines"]:
        rates = [t["rate_pct"] for t in tot["tax_lines"] if t["rate_pct"] is not None]
        labels = {t["label"] for t in tot["tax_lines"]}
        if rates:
            rate = sum(rates) if ({"CGST", "SGST"} <= labels or {"CGST", "UTGST"} <= labels) else rates[0]
    tax_total = tot["tax_total"]
    if tax_total is None and tot["tax_lines"]:
        s = sum(parse_money(t["amount"]) or 0 for t in tot["tax_lines"])
        tax_total = f"{s / 100:.2f}"
        tax_raw = " + ".join(t["amount"] for t in tot["tax_lines"])
    else:
        tax_raw = tax_total

    for it in items:
        if it.get("tax_rate_pct") is None and rate is not None:
            it["tax_rate_pct"] = rate

    notes = []
    if not items:
        notes.append("The line-item table could not be read: no recognisable column headings "
                     "(a description, a quantity or rate, and an amount column are needed).")
    if incl:
        notes.append("Prices are printed inclusive of GST.")
    if bank["notice"]:
        notes.append("The invoice says the vendor's bank details have changed.")
    if cur_note:
        notes.append(cur_note)

    return {
        "extractor": "text-parser",
        "extractor_version": config.TEXT_PARSER_VERSION,
        "text_source": text_source,
        "fields": {
            "vendor_name": _fld(vendor_name, conf=0.93 if not low else 0.86),
            "vendor_gstin": _fld(gstin, conf=hi_conf),
            "invoice_no": _fld(inv_no, conf=hi_conf),
            "invoice_date": _fld(date_raw, conf=hi_conf),
            "po_reference": _fld(po_raw, conf=hi_conf),
            "currency": _fld(currency, cur_raw, conf=0.95 if not low else 0.9),
            "subtotal": _fld(tot["subtotal"], conf=hi_conf),
            "tax_total": _fld(tax_total, tax_raw, conf=hi_conf),
            "total": _fld(tot["total"], conf=hi_conf),
            "bank_name": _fld(bank["bank_name"], conf=hi_conf),
            "bank_account": _fld(bank["account"], conf=hi_conf),
            "bank_ifsc": _fld(bank["ifsc"], conf=hi_conf),
        },
        "line_items": items,
        "tax_lines": tot["tax_lines"],
        "tax_inclusive": bool(incl),
        "tax_rate_pct": rate,
        "bank_change_notice": bank["notice"],
        "bank_change_text": bank["notice_text"],
        "bank_entries": bank["entries"],
        "po_reference_candidates": po_cands,
        "other_charges": f"{tot['other_paise'] / 100:.2f}" if tot["other_paise"] else None,
        "discount": f"{tot['discount_paise'] / 100:.2f}" if tot["discount_paise"] else None,
        "other_charge_labels": tot["other_labels"],
        "document_notes": " ".join(notes),
    }
