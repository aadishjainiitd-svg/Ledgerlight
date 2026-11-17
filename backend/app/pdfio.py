"""Stage 1 helpers: open, hash and classify a PDF with PyMuPDF; read words and spans;
render pages to PNG."""
from __future__ import annotations

import hashlib
import re

import pymupdf

INVOICE_WORDS = re.compile(r"\b(tax\s+invoice|invoice|bill\s+of\s+supply|bill\s+no|inv\s*no)\b", re.I)


class PdfRejected(ValueError):
    """The file cannot be accepted (not a PDF, locked, too large, too many pages)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_upload(data: bytes, max_bytes: int, max_pages: int) -> int:
    """Validate an upload. Returns page count or raises PdfRejected with a plain-English message."""
    if len(data) > max_bytes:
        raise PdfRejected(f"File is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data[:1024].lstrip().startswith(b"%PDF"):
        raise PdfRejected("Only PDF files are supported.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise PdfRejected("This file could not be opened as a PDF. Ask the sender for a readable copy.")
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise PdfRejected("This PDF is password protected. Ask the sender for an unlocked copy.")
        if doc.page_count == 0:
            raise PdfRejected("This PDF has no pages.")
        if doc.page_count > max_pages:
            raise PdfRejected(f"This PDF has {doc.page_count} pages; the limit is {max_pages}.")
        return doc.page_count
    finally:
        doc.close()


def inspect(data: bytes) -> dict:
    """Classify the document. doc_type is 'scanned' when a page has fewer than 50 text characters
    or a single image covers most of it; text_source says where readable text comes from:
    'text_layer', 'ocr_layer' (scanned image with an embedded OCR layer) or 'none'."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        pages = []
        for page in doc:
            text = page.get_text("text") or ""
            chars = len(re.sub(r"\s", "", text))
            area = abs(page.rect.width * page.rect.height) or 1
            cover = 0.0
            try:
                for info in page.get_image_info():
                    bb = pymupdf.Rect(info["bbox"]) & page.rect
                    cover = max(cover, abs(bb.width * bb.height) / area)
            except Exception:
                pass
            pages.append({"chars": chars, "image_cover": round(cover, 3),
                          "width": page.rect.width, "height": page.rect.height})
        avg_chars = sum(p["chars"] for p in pages) / max(1, len(pages))
        image_dominant = all(p["image_cover"] >= 0.80 for p in pages)
        has_text = avg_chars >= 50
        if has_text and not image_dominant:
            doc_type, text_source = "text", "text_layer"
        elif has_text and image_dominant:
            doc_type, text_source = "scanned", "ocr_layer"
        else:
            doc_type, text_source = "scanned", "none"
        full = "\n".join(p.get_text("text") for p in doc) if has_text else ""
        return {
            "page_count": doc.page_count, "pages": pages, "avg_chars": round(avg_chars, 1),
            "doc_type": doc_type, "text_source": text_source, "text": full,
            "looks_like_invoice": bool(INVOICE_WORDS.search(full)) if has_text else None,
        }
    finally:
        doc.close()


def _hidden_boxes(page) -> list[tuple]:
    """Bounding boxes of text a reader cannot see (render mode 3 or fully transparent) on a page that also has
    visible text. A page whose text is ALL invisible is an OCR layer over a scanned image and is kept."""
    try:
        trace = page.get_texttrace()
    except Exception:
        return []
    hidden = [s for s in trace if s.get("type") == 3 or (s.get("opacity") is not None and s["opacity"] <= 0.01)]
    if not hidden or len(hidden) == len(trace):
        return []
    return [tuple(s["bbox"]) for s in hidden]


def _inside(w: tuple, boxes: list[tuple]) -> bool:
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    return any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b in boxes)


def words(data: bytes) -> list[list[tuple]]:
    """Per page list of (x0, y0, x1, y1, word), without text a reader cannot see (see _hidden_boxes)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        out = []
        for page in doc:
            boxes = _hidden_boxes(page)
            out.append([(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words") if not _inside(w, boxes)])
        return out
    finally:
        doc.close()


def hidden_text(data: bytes) -> list[str]:
    """The invisible lines dropped by words(), for the run log (first 120 characters of each)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        found = []
        for page in doc:
            boxes = _hidden_boxes(page)
            for b in boxes:
                t = page.get_textbox(pymupdf.Rect(b)).strip()
                if t:
                    found.append(re.sub(r"\s+", " ", t)[:120])
        return found
    finally:
        doc.close()


def spans(data: bytes, page_no: int = 0) -> list[dict]:
    """Text spans with font size for one page (used to find the letterhead)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if page_no >= doc.page_count:
            return []
        out = []
        d = doc[page_no].get_text("dict")
        for b in d.get("blocks", []):
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    t = sp.get("text", "").strip()
                    if t:
                        out.append({"text": t, "size": sp.get("size", 0), "bbox": sp.get("bbox"),
                                    "bold": "bold" in sp.get("font", "").lower()})
        return out
    finally:
        doc.close()


def find_bbox(data: bytes, needle: str) -> dict | None:
    """First page and bbox of a literal string (for highlighting fields on text PDFs)."""
    if not needle or len(needle) < 2:
        return None
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        for i, page in enumerate(doc):
            hits = page.search_for(needle)
            if hits:
                r = hits[0]
                return {"page": i + 1, "x0": round(r.x0, 1), "y0": round(r.y0, 1), "x1": round(r.x1, 1),
                        "y1": round(r.y1, 1), "page_width": page.rect.width, "page_height": page.rect.height}
        return None
    finally:
        doc.close()


def render_png(data: bytes, page_no: int = 0, dpi: int = 110) -> bytes:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[max(0, min(page_no, doc.page_count - 1))]
        return page.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()
