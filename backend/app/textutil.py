"""Deterministic normalisation helpers: money, dates, invoice numbers, PO references,
descriptions and units. Everything here is pure and unit-tested."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------- money

MONEY_TOKEN_RE = re.compile(
    r"(?<![\w.])(?:₹|rs\.?|inr)?\s*-?\d{1,3}(?:[,  ]\d{2,3})*(?:\.\d{1,2})?(?![\w])|(?<![\w.])-?\d+(?:\.\d{1,2})?(?![\w%])",
    re.I)


def parse_money(text) -> int | None:
    """Parse a printed amount into integer paise. Handles ₹/Rs/INR, Indian grouping
    (1,18,000.00), western grouping and decimal commas (1.18.000,00). None if unparseable."""
    if text is None:
        return None
    if isinstance(text, (int, float, Decimal)):
        return int((Decimal(str(text)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    s = str(text).strip()
    s = re.sub(r"(?i)(₹|rs\.?|inr|/-)", "", s).strip()
    s = s.replace(" ", "").replace(" ", "").replace(" ", "")
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    # Decimal comma: "1.18.000,00" or "78750,00"
    if re.search(r",\d{1,2}$", s) and (s.count(",") == 1) and ("." in s or len(s.split(",")[0]) > 3):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    if s.count(".") > 1:
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    paise = int((val * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return -paise if neg else paise


def parse_number(text) -> float | None:
    """Parse a quantity like '3,000', '150 kg', '30 sets'."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def inr(paise: int | None, decimals: int = 2) -> str:
    """Format paise as Indian-grouped rupees: 11800000 -> '₹1,18,000.00'."""
    if paise is None:
        return "n/a"
    neg = paise < 0
    paise = abs(int(paise))
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        s = head + "," + tail
    out = "₹" + s + (f".{p:02d}" if decimals else "")
    return ("-" if neg else "") + out


def inr0(paise: int | None) -> str:
    if paise is None:
        return "n/a"
    return inr(int(round(paise / 100.0)) * 100, 0)


def fmt_qty(q: float | None) -> str:
    if q is None:
        return "n/a"
    if abs(q - round(q)) < 1e-9:
        n = int(round(q))
        s = str(abs(n))
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
            s = head + "," + tail
        return ("-" if n < 0 else "") + s
    return f"{q:,.2f}".rstrip("0").rstrip(".")


def fmt_date(d: date | str | None) -> str:
    if d is None:
        return "n/a"
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- dates

def _mk(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text, as_of: date | None = None, day_first: bool = True) -> dict:
    """Parse a printed date. Returns {value: date|None, ambiguous: bool, alternative: date|None,
    note: str}. Day-first by default (India). When both orders are valid the day-first reading
    is kept unless it is in the future and the other is not (spec 2.3)."""
    res = {"value": None, "ambiguous": False, "alternative": None, "note": ""}
    if not text:
        return res
    s = str(text).strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        res["value"] = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return res
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-./]+([A-Za-z]{3,9})\.?,?[\s\-./]+(\d{2,4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        res["value"] = _mk(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        return res
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{2,4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        res["value"] = _mk(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        return res
    m = re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        first = _mk(y, b, a) if day_first else _mk(y, a, b)
        second = _mk(y, a, b) if day_first else _mk(y, b, a)
        if first and second and first != second:
            res["ambiguous"] = True
            chosen, other = first, second
            if as_of and first > as_of and second <= as_of:
                chosen, other = second, first
            res["value"], res["alternative"] = chosen, other
            # The configured order (day first for India) giving a valid date that is not in the future is how
            # this team writes dates, not an ambiguity. Only a fallback to the other order stays ambiguous.
            if chosen == first:
                res["ambiguous"] = False
            order = "day first" if chosen == first else "month first"
            res["note"] = (f'"{m.group(0)}" could be {fmt_date(first)} or {fmt_date(second)}. '
                           f"Read as {fmt_date(chosen)} ({order})"
                           + (f"; {fmt_date(other)} would be in the future." if as_of and other > as_of else "."))
        else:
            res["value"] = first or second
        return res
    return res


def to_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------- invoice numbers

def canonical_invoice_no(raw: str | None) -> str | None:
    if not raw:
        return None
    c = re.sub(r"[^A-Z0-9]", "", str(raw).upper())
    return c or None


def invoice_prefix(raw: str | None) -> str:
    c = canonical_invoice_no(raw) or ""
    m = re.match(r"[A-Z]+", c)
    return m.group(0) if m else ""


def serial_token(raw: str | None, issue_year: int | None = None) -> str | None:
    """Longest digit run that is not the issue year (2 or 4 digits), leading zeros stripped.
    BL/2026/0377 -> '377'; BL-0377-26 -> '377'."""
    if not raw:
        return None
    runs = re.findall(r"\d+", str(raw))
    if not runs:
        return None
    years = set()
    if issue_year:
        years = {str(issue_year), str(issue_year)[-2:]}
    cand = [r for r in runs if r not in years] or runs
    best = max(cand, key=len)  # max keeps the first of equal length
    return best.lstrip("0") or "0"


# ---------------------------------------------------------------- PO references

PO_FULL_RE = re.compile(r"\bP\.?\s?O\.?[\s\-#:]*(?:no\.?|number)?[\s\-#:]*(\d{4})[\s\-/]+(\d{3,5})\b", re.I)
PO_REVERSED_RE = re.compile(r"\b(\d{3,5})\s*/\s*(20\d{2})\b")
PO_LOOSE_RE = re.compile(r"\b(20\d{2})[\s\-/]+(\d{3,5})\b")


PO_CONTEXT_REVERSED_RE = re.compile(r"\b(?:P\.?O\.?|purchase order|order)[^\n]{0,12}?\b(\d{3,5})\s*/\s*(20\d{2})\b", re.I)


def po_keys(text: str | None, strict: bool = False) -> list[tuple[int, int]]:
    """All (year, serial) pairs that a PO reference text could denote, most specific first.
    'PO-2026-1001' -> (2026, 1001); 'Ref your PO 1002/2026' -> (2026, 1002).
    strict=True (for free text) only accepts forms with a PO / order keyword."""
    if not text:
        return []
    out: list[tuple[int, int]] = []
    for m in PO_FULL_RE.finditer(text):
        out.append((int(m.group(1)), int(m.group(2))))
    for m in (PO_CONTEXT_REVERSED_RE if strict else PO_REVERSED_RE).finditer(text):
        out.append((int(m.group(2)), int(m.group(1))))
    if not strict:
        for m in PO_LOOSE_RE.finditer(text):
            out.append((int(m.group(1)), int(m.group(2))))
    seen, res = set(), []
    for k in out:
        if k not in seen and 2000 <= k[0] <= 2099:
            seen.add(k)
            res.append(k)
    return res


def po_key_of_id(po_id: str) -> tuple[int, int] | None:
    ks = po_keys(po_id)
    return ks[0] if ks else None


# ---------------------------------------------------------------- descriptions & units

UOM_ALIASES = {
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "nos": "nos", "no": "nos", "pcs": "nos", "pc": "nos", "piece": "nos", "pieces": "nos",
    "units": "nos", "unit": "nos", "ea": "nos", "each": "nos", "sets": "nos", "set": "nos",
    "reams": "reams", "ream": "reams", "trip": "trips", "trips": "trips", "lot": "lot", "lots": "lot",
    "boxes": "boxes", "box": "boxes", "ltr": "l", "litre": "l", "litres": "l", "l": "l",
}

STOPWORDS = {"and", "the", "for", "with", "of", "to", "a", "an", "in", "on", "per", "each", "lot",
             "supply", "supplied", "item", "items", "nos", "pcs", "qty", "set", "sets"}


def norm_uom(u: str | None) -> str | None:
    if not u:
        return None
    k = re.sub(r"[^a-z]", "", str(u).lower())
    return UOM_ALIASES.get(k, k or None)


def _stem(t: str) -> str:
    if len(t) > 4 and t.endswith("es") and not t.endswith("ses"):
        return t[:-2] if t[-3] in "hsx" else t[:-1]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def norm_desc(desc: str | None) -> str:
    """Lower-case, de-noise a description for matching: drop punctuation, numbers in brackets,
    'lot 3 of 3' markers and units."""
    if not desc:
        return ""
    s = str(desc).lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\blot \d+ of \d+\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [_stem(t) for t in s.split() if not t.isdigit()]
    return " ".join(toks)


def sig_tokens(desc: str | None) -> set[str]:
    return {t for t in norm_desc(desc).split() if len(t) >= 3 and t not in STOPWORDS}


def digits_only(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def mask_account(acct: str | None) -> str:
    d = digits_only(acct)
    return ("ending " + d[-4:]) if d else "none"
