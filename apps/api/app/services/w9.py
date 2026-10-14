"""W-9 extraction: upload a W-9 (PDF or image), get back structured tax data for review.

Pipeline (first hit wins):
  1. Digital text — PyMuPDF extracts embedded text (most generated/printed W-9s).
  2. OCR — scanned PDFs are rasterized with PyMuPDF and read with Tesseract
     (pytesseract). Needs the `tesseract` binary on the machine; Vercel's
     serverless runtime doesn't ship it, so scans fall back to guided manual
     entry there. `ocr_available()` reports which path applies.
  3. Manual — the review form is always editable; nothing is trusted blindly.

Only parsed fields leave this module — never the raw document text.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil

log = logging.getLogger("mytrakin.w9")

MIN_TEXT_CHARS = 200       # below this, embedded text is useless (scanned PDF)
OCR_MAX_PAGES = 3
OCR_DPI = 300

TAX_CLASSIFICATIONS = [
    "Individual/sole proprietor",
    "C Corporation",
    "S Corporation",
    "Partnership",
    "Trust/estate",
    "Limited liability company",
    "Exempt payee",
]

_EIN_RE = re.compile(r"(?<!\d)(\d{2})-?(\d{7})(?!\d)")
_SSN_RE = re.compile(r"(?<!\d)(\d{3})-?(\d{2})-?(\d{4})(?!\d)")
_ZIP_RE = re.compile(r"(?<!\d)(\d{5})(?:-?\d{4})?(?!\d)")
_STATE_RE = re.compile(r"\b([A-Z]{2})\s+\d{5}")


def ocr_available() -> bool:
    """Is the Tesseract binary installed (scanned W-9s readable)?"""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _pdf_text(data: bytes) -> str:
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() or "" for page in doc)
    except Exception:
        log.warning("PyMuPDF text extraction failed", exc_info=True)
        return ""


def _ocr_image(data: bytes) -> str:
    """OCR one image (PNG/JPEG/WebP bytes). Empty string when unavailable."""
    if not ocr_available():
        return ""
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img) or ""


def _ocr_pdf(data: bytes) -> str:
    """Rasterize the first pages of a scanned PDF and OCR them."""
    if not ocr_available():
        return ""
    try:
        import pymupdf
        out: list[str] = []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc[:OCR_MAX_PAGES]:
                pix = page.get_pixmap(dpi=OCR_DPI)
                out.append(_ocr_image(pix.tobytes("png")))
        return "\n".join(out)
    except Exception:
        log.warning("PDF OCR failed", exc_info=True)
        return ""


def parse_w9_text(text: str) -> dict:
    """Heuristics for IRS Form W-9 (Rev. 2018/2024): names, classification, address, TIN."""
    lines = [ln.strip() for ln in text.splitlines()]
    content = [ln for ln in lines if ln and not re.fullmatch(r"[.\-_\s]+", ln)]

    def after(pattern: str) -> str | None:
        for i, ln in enumerate(content):
            if re.search(pattern, ln, re.IGNORECASE):
                # The value is usually on the same line, after the colon.
                if ":" in ln:
                    same = ln.split(":", 1)[1].strip()
                    if len(same) >= 2 and not re.match(
                            r"^(Step|Line|Part|Form|Cat\.|For |See |Go to|Give |Print|Check|Enter|List|Note\.?)", same):
                        return same
                for nxt in content[i + 1:i + 4]:
                    if len(nxt) >= 2 and not re.match(r"^(Step|Line|Part|Form|Cat\.|For |See |Go to|Give |Print|Check|Enter|List|Note\.?|Under)", nxt):
                        return nxt
        return None

    legal_name = after(r"^\s*1\s+Name|Name \(as shown")
    dba = after(r"^\s*2\s+Business name|Business name/disregarded")
    lowered = text.lower()
    classification = next((c for c in TAX_CLASSIFICATIONS if c.lower() in lowered), None)

    address = after(r"^\s*5\s+Address|Address \(number, street")
    city_state_zip = after(r"^\s*6\s+City|City,?\s*state.*ZIP|city, town, state")
    city = state = zip_code = None
    if city_state_zip:
        m = re.search(r"^(.*?),\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)", city_state_zip)
        if m:
            city, state, zip_code = m.group(1).strip(), m.group(2).upper(), m.group(3)
    if not zip_code:
        m = _ZIP_RE.search(text)
        zip_code = m.group(1) if m else None
    if not state:
        m = _STATE_RE.search(text)
        state = m.group(1) if m else None

    tin = tin_type = None
    ein_at = text.find("Employer identification")
    ssn_at = text.find("Social security")
    candidates_ein = [(m.start(), f"{m.group(1)}-{m.group(2)}", "ein") for m in _EIN_RE.finditer(text)]
    candidates_ssn = [(m.start(), f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "ssn") for m in _SSN_RE.finditer(text)]
    candidates = sorted(candidates_ein + candidates_ssn)
    if candidates:
        # Prefer the number printed nearest its label (Part I of the form).
        def distance(c):
            anchor = ein_at if c[2] == "ein" else ssn_at
            return abs(c[0] - anchor) if anchor >= 0 else 10**9
        best = min(candidates, key=distance)
        tin, tin_type = best[1], best[2]

    review = [k for k, v in {"legal_name": legal_name, "tax_classification": classification,
                             "address": address, "tin": tin}.items() if not v]
    return {"legal_name": legal_name, "dba": dba, "tax_classification": classification,
            "tin": tin, "tin_type": tin_type, "address": address, "city": city,
            "state": state, "zip": zip_code, "needs_review": review}


async def extract_w9(data: bytes, content_type: str) -> dict:
    """Extract W-9 fields from uploaded bytes. Blocking work runs in a thread."""
    kind = "pdf" if content_type == "application/pdf" else "image" if content_type in {
        "image/jpeg", "image/png", "image/webp"} else "other"
    if kind == "other":
        return {"engine": "none", "needs_manual": True, "needs_review": ["upload"],
                "note": "Upload the W-9 as a PDF, JPEG, PNG or WebP file."}

    def _work() -> tuple[str, str]:
        if kind == "image":
            text = _ocr_image(data)
            return text, ("ocr" if text.strip() else "none")
        text = _pdf_text(data)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return text, "pdf-text"
        ocr_text = _ocr_pdf(data)
        if len(ocr_text.strip()) >= 40:
            return ocr_text, "ocr"
        return text, "none"

    text, engine = await asyncio.to_thread(_work)
    if engine == "none":
        reason = ("no Tesseract on this machine" if not ocr_available()
                  else "no readable text found")
        return {"engine": "none", "needs_manual": True,
                "needs_review": ["legal_name", "tax_classification", "address", "tin"],
                "note": f"This looks like a scanned W-9 ({reason}). Type the details below — the document is still attached."}

    parsed = await asyncio.to_thread(parse_w9_text, text)
    return {"engine": engine, "needs_manual": False, **parsed,
            "note": "Check every field against the document before submitting." if parsed["needs_review"] else None}
